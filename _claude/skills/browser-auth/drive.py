#!/usr/bin/env python3
"""ユーザーが資格情報を入力するためのブラウザを立て、常駐して状態を書き出す。

設計上の制約が2つある。

1. **フォーカスを繰り返し奪わない。** headed Chrome への `page.screenshot()` は
   再描画を起こし、毎回撮ると画面がチラつく。よってスクリーンショットは
   「URL が変わったとき」と「明示的に要求されたとき」だけ撮る。
   DOM の状態だけなら再描画を伴わないので、こちらは定期的に取れる。
2. **既定プロファイルは使えない。** 通常 Chrome が起動していると
   既定プロファイルはロックされている。プロファイルは `--profile` ごとに分けて
   `<runtime>/<profile>/profile` に置く。サイトごとにセッションが残る。

使い方:
    python3 drive.py --url <URL> [--profile gcloud] [--runtime DIR] [--background]

出力（すべて `<runtime>/<profile>/` 配下）:
    state.json  ページの状態（URL / タイトル / 見出し / 入力欄 / ボタン）
    screen.png  スクリーンショット（URL 変化時と要求時のみ更新）
    cmd.jsonl   エージェントが追記するコマンド
    driver.log  標準出力

コマンド（`cmd.jsonl` に1行1 JSON で追記する）:
    {"op": "shot"}                                  今の画面を撮り直す
    {"op": "goto",  "url": "..."}                   遷移する
    {"op": "click", "selector": "text=Allow"}       クリックする
    {"op": "fill",  "selector": "...", "value": ""} 入力する（資格情報には使わない）
    {"op": "stop"}                                  ブラウザを閉じて終了する
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

POLL_SECONDS = 2


def frontmost_app() -> str | None:
    """いま前面にあるアプリ名。--background でここへフォーカスを戻す。"""
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--profile", default="default",
                    help="プロファイル名。サイトごとに分けるとセッションが残る")
    ap.add_argument("--runtime", required=True, help="出力先の親ディレクトリ")
    ap.add_argument("--background", action="store_true",
                    help="起動後にフォーカスを元のアプリへ戻す（エージェントが操作する場合）")
    ap.add_argument("--minutes", type=int, default=30)
    args = ap.parse_args()

    out = Path(args.runtime) / args.profile
    out.mkdir(parents=True, exist_ok=True)
    for name in ("state.json", "screen.png", "cmd.jsonl"):
        (out / name).unlink(missing_ok=True)
    (out / "cmd.jsonl").touch()

    previous_app = frontmost_app() if args.background else None

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(out / "profile"),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--window-position=60,60"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        if previous_app:
            activate(previous_app)
            print(f"focus returned to {previous_app}", flush=True)
        print("browser launched", flush=True)

        def shoot(reason: str) -> None:
            try:
                page.screenshot(path=str(out / "screen.png"))
                print(f"screenshot: {reason}", flush=True)
            except Exception as exc:
                print(f"screenshot failed: {exc}", flush=True)

        shoot("initial")
        last_url = page.url
        cursor = 0
        deadline = time.time() + args.minutes * 60

        while time.time() < deadline:
            state = read_state(page)
            state["screenshot_url"] = last_url
            (out / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1))

            # URL が変わったときだけ撮り直す（チラつきを最小にする）
            if state["url"] != last_url:
                last_url = state["url"]
                shoot("url changed")

            lines = (out / "cmd.jsonl").read_text().splitlines()
            for line in lines[cursor:]:
                cursor += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line)
                except json.JSONDecodeError:
                    print(f"bad command: {line[:60]}", flush=True)
                    continue
                op = cmd.get("op")
                try:
                    if op == "stop":
                        print("stop requested", flush=True)
                        ctx.close()
                        return 0
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
                    else:
                        print(f"unknown op: {op}", flush=True)
                        continue
                    print(f"ok: {op}", flush=True)
                except Exception as exc:
                    print(f"failed {op}: {type(exc).__name__}: {exc}", flush=True)

            time.sleep(POLL_SECONDS)

        print("deadline reached", flush=True)
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
