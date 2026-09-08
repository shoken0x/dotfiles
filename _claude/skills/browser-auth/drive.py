#!/usr/bin/env python3
"""ユーザーが資格情報を入力するためのブラウザを立て、常駐して状態を書き出す。

設計上の制約（どれも実際に踏んだもの。崩す改造をしない）:

1. **フォーカスを奪わない。** 既定で、起動直後・`goto` の完了を待たずに元のアプリへ
   フォーカスを返す。ユーザーが入力する場面だけ `--focus` を付ける。
2. **ウィンドウ位置を固定する。** 永続プロファイルは前回のウィンドウ位置を復元するため
   `--window-position` フラグだけでは効かない。CDP の `Browser.setWindowBounds` で
   上書きする。ただし setWindowBounds はウィンドウを前面に出すので、
   **フォーカスを返すより先に**実行する。
3. **スクリーンショットは URL 変化時と明示要求時だけ。** headed Chrome への
   `page.screenshot()` は再描画を起こし、定期的に撮ると画面がチラつく。
   DOM 由来の状態は再描画を伴わないので、こちらは2秒ごとに更新して良い。
4. **既定の Chrome プロファイルは使わない。** 通常 Chrome が起動しているとロックされている。
   `--profile` でサイトごとに分け、セッションをそこに残す。
5. **SIGTERM で即死させない。** Chrome は Cookie を非同期で書くため、`ctx.close()` を
   通さずに殺すとログインセッションが保存前に失われる。

使い方:
    python3 drive.py --url <URL> --profile <name> --runtime DIR [--focus]
                     [--window 60,60,1280,900] [--minutes 45]

出力（すべて `<runtime>/<profile>/` 配下）:
    state.json  ページの状態（URL / タイトル / 見出し / 入力欄 / ボタン）
    screen.png  スクリーンショット（URL 変化時と要求時のみ）
    cmd.jsonl   エージェントが1行1 JSON で追記するコマンド
    driver.log  標準出力
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

POLL_SECONDS = 2


class Terminated(Exception):
    """SIGTERM / SIGINT を受けた。ブラウザを正しく閉じてから終わる。"""


class BrowserClosed(Exception):
    """ユーザーがウィンドウを閉じた。以降どの操作も TargetClosedError になる。"""


def _on_signal(signum, frame):
    raise Terminated()


def frontmost_app() -> str | None:
    """いま前面にあるアプリ名。ここへフォーカスを戻す。"""
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first application process '
             'whose frontmost is true'],
            capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None


def activate(app: str) -> None:
    try:
        subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'],
                       capture_output=True, timeout=5)
    except Exception:
        pass



def read_state(page) -> dict:
    """DOM から読めるものだけを集める。再描画を起こさないので定期実行して良い。"""
    if page.is_closed():
        raise BrowserClosed()
    state = {"url": page.url, "title": "", "headings": [], "inputs": [], "buttons": []}
    try:
        state["title"] = page.title()
        state["headings"] = [t.strip() for t in
                             page.locator("h1, h2, [role=heading]").all_inner_texts()
                             if t.strip()][:6]
        for el in page.locator("input:visible").all()[:10]:
            state["inputs"].append({
                "type": el.get_attribute("type") or "text",
                "name": el.get_attribute("name") or "",
                "label": (el.get_attribute("aria-label")
                          or el.get_attribute("placeholder") or ""),
            })
        state["buttons"] = [t.strip() for t in
                            page.locator("button:visible, [role=button]:visible,"
                                         " a[role=button]:visible").all_inner_texts()
                            if t.strip()][:10]
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}: {exc}"
    return state


def run_command(page, cmd: dict, out: Path, shoot) -> None:
    """コマンド1件を実行する。例外は呼び出し側で拾う。"""
    op = cmd.get("op")
    if op == "shot":
        shoot("requested")
    elif op == "goto":
        page.goto(cmd["url"], wait_until="domcontentloaded", timeout=60000)
        shoot("after goto")
    elif op == "click":
        page.click(cmd["selector"], timeout=15000)
        page.wait_for_timeout(1500)
        shoot("after click")
    elif op == "fill":
        page.fill(cmd["selector"], cmd["value"], timeout=15000)
        shoot("after fill")
    elif op == "type":
        # fill は value を代入するだけなので、keyup / input を待って動く JS の
        # フィルタや検索ボックスには効かない。type は1文字ずつ打つ。
        page.click(cmd["selector"], timeout=15000)
        page.fill(cmd["selector"], "", timeout=15000)
        page.type(cmd["selector"], cmd["value"], delay=40)
        page.wait_for_timeout(1200)
        shoot("after type")
    elif op == "press":
        page.keyboard.press(cmd["key"])
        page.wait_for_timeout(1200)
        shoot("after press")
    elif op == "insert":
        # コードエディタ（CodeMirror / Monaco）には fill も type も向かない。
        # fill は代入なのでエディタが気付かず、type は自動インデントと括弧の
        # 自動補完で JSON が壊れる。insert_text は1回のテキスト挿入として入る。
        if cmd.get("selector"):
            page.click(cmd["selector"], timeout=15000)
        if cmd.get("clear"):
            page.keyboard.press("Meta+a")
            page.keyboard.press("Delete")
        page.keyboard.insert_text(cmd["text"])
        page.wait_for_timeout(1200)
        shoot("after insert")
    elif op == "select":
        page.select_option(cmd["selector"], label=cmd.get("label"),
                           value=cmd.get("value"), timeout=15000)
        page.wait_for_timeout(1200)
        shoot("after select")
    elif op == "upload":
        page.set_input_files(cmd.get("selector", "input[type=file]"),
                             cmd["path"], timeout=15000)
        page.wait_for_timeout(1500)
        shoot("after upload")
    elif op == "value":
        # input の value をファイルに書く。トークンやシークレットを
        # 「エージェントの文脈に載せずに」次のコマンドへ渡すための経路。
        target = out / cmd.get("file", "value.txt")
        target.write_text(page.input_value(cmd["selector"], timeout=15000))
        print(f"value written: {target.name} ({len(target.read_text())} chars)", flush=True)
    elif op == "html":
        # セレクタが当たらないときに構造を見る。value 属性に秘密が入ることがあるので、
        # 出力は cat せず、属性名だけを grep して使う。
        target = out / cmd.get("file", "dom.html")
        target.write_text(page.inner_html(cmd.get("selector", "body")))
        print(f"html written: {target.name} ({len(target.read_text())} chars)", flush=True)
    elif op == "text":
        target = cmd.get("selector", "body")
        (out / "text.txt").write_text(page.inner_text(target))
        print(f"text written: {target}", flush=True)
    else:
        raise ValueError(f"unknown op: {op}")
    print(f"ok: {op}", flush=True)


def main() -> int:
    # kill されたときに ctx.close() を通す。SIGTERM で即死させると Chrome が
    # Cookie を書き出す前に死に、ログインセッションが失われる（実際に失った）。
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--profile", default="default",
                    help="プロファイル名。サイトごとに分けるとセッションが残る")
    ap.add_argument("--runtime", required=True, help="出力先の親ディレクトリ")
    ap.add_argument("--focus", action="store_true",
                    help="ブラウザにフォーカスを渡したままにする。既定では元のアプリへ戻す")
    ap.add_argument("--background", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--window", default="60,60,1280,900",
                    help="ウィンドウの left,top,width,height（既定 60,60,1280,900）")
    args = ap.parse_args()

    try:
        left, top, width, height = (int(v) for v in args.window.split(","))
    except ValueError:
        print("--window は left,top,width,height の形式で指定してください", flush=True)
        return 2

    out = Path(args.runtime) / args.profile
    out.mkdir(parents=True, exist_ok=True)
    for name in ("state.json", "screen.png", "cmd.jsonl"):
        (out / name).unlink(missing_ok=True)
    (out / "cmd.jsonl").touch()

    previous_app = None if args.focus else frontmost_app()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(out / "profile"),
            channel="chrome",
            headless=False,
            viewport=None,          # OS ウィンドウのサイズをそのまま使う
            args=[f"--window-position={left},{top}",
                  f"--window-size={width},{height}"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # setWindowBounds はウィンドウを前面に出すので、フォーカスを返す前に済ませる。
        try:
            cdp = ctx.new_cdp_session(page)
            window_id = cdp.send("Browser.getWindowForTarget")["windowId"]
            cdp.send("Browser.setWindowBounds", {
                "windowId": window_id,
                "bounds": {"left": left, "top": top, "width": width,
                           "height": height, "windowState": "normal"},
            })
            print(f"window fixed at {left},{top} {width}x{height}", flush=True)
        except Exception as exc:
            print(f"window bounds not applied: {type(exc).__name__}: {exc}", flush=True)

        # goto の完了を待たずに返す。読み込みの数秒間ずっと奪われているのが一番うるさい。
        if previous_app:
            activate(previous_app)

        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)

        # ⚠️ フォーカスの奪い返しに osascript で張り付いて対抗する実装を試したが、
        # osascript 1回あたり最大5秒のタイムアウトが積み上がり、起動が3分以上かかった。
        # フォーカスは「起動直後に1回返す」だけにする。取り返されることはあるが、
        # 起動を壊すよりましである。ユーザーが入力する場面は --focus を使う。
        if previous_app:
            print(f"focus returned to {previous_app}", flush=True)
        print("browser launched", flush=True)

        last_url = page.url

        def shoot(reason: str) -> None:
            try:
                page.screenshot(path=str(out / "screen.png"))
                print(f"screenshot: {reason}", flush=True)
            except Exception as exc:
                print(f"screenshot failed: {exc}", flush=True)

        def write_state() -> dict:
            state = read_state(page)
            state["screenshot_url"] = last_url
            (out / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1))
            return state

        shoot("initial")
        cursor = 0
        deadline = time.time() + args.minutes * 60
        stopped = False

        try:
            while time.time() < deadline and not stopped:
                try:
                    state = write_state()
                except BrowserClosed:
                    print("browser closed by user", flush=True)
                    break

                if state["url"] != last_url:
                    last_url = state["url"]
                    shoot("url changed")

                for line in (out / "cmd.jsonl").read_text().splitlines()[cursor:]:
                    cursor += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd = json.loads(line)
                    except json.JSONDecodeError:
                        print(f"bad command: {line[:60]}", flush=True)
                        continue
                    if cmd.get("op") == "stop":
                        print("stop requested", flush=True)
                        stopped = True
                        break
                    try:
                        run_command(page, cmd, out, shoot)
                    except Exception as exc:
                        print(f"failed {cmd.get('op')}: {type(exc).__name__}: {exc}",
                              flush=True)
                        if page.is_closed():
                            print("browser closed by user", flush=True)
                            stopped = True
                            break
                    # 直後に state.json を読んだとき古い URL を返さないよう、即反映する。
                    try:
                        last_url = page.url
                        write_state()
                    except BrowserClosed:
                        print("browser closed by user", flush=True)
                        stopped = True
                        break

                if not stopped:
                    time.sleep(POLL_SECONDS)
            else:
                if not stopped:
                    print("deadline reached", flush=True)
        except Terminated:
            print("terminated: closing browser cleanly", flush=True)

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
