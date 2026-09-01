#!/usr/bin/env python3
"""トランスクリプトからツール使用イベントを増分で取り込む。

## 取り込み対象

    ~/.claude/projects/<proj>/<session>.jsonl                   … メインセッション
    ~/.claude/projects/<proj>/<session>/subagents/agent-*.jsonl … サブエージェント

**サブエージェントは別ファイル**なので、これを読まないと「エージェントが何を使ったか」が
丸ごと落ちる（実測 2026-08-26: サブエージェント側だけで Bash 16,642 / WebFetch 1,233）。
親セッション ID はパスから決めるので、main と sub が 1 セッションに集約される。

## 使い方

    collect.py --session <transcript_path>   # PostToolUse hook から。当該セッションのみ
    collect.py --all                         # ダッシュボード用。全 transcript を増分走査
    collect.py --all --reset                 # 再構築（分類ロジックを変えたとき）

## 冪等性

`events.tid` は tool_use の id（`toolu_...`）。`INSERT OR IGNORE` なので
オフセットが巻き戻っても二重計上しない。
"""

import argparse
import fcntl
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classify as C
import db as D

PROJECTS = os.path.expanduser("~/.claude/projects")
_MCP_MENTION = re.compile(rb"mcp__([A-Za-z0-9_.-]+)__")
_ISO = re.compile(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)")

CHUNK_WARN_BYTES = 64 * 1024 * 1024


# ---------------------------------------------------------------------------
# パス → セッション
# ---------------------------------------------------------------------------

def session_of(path: str):
    """(session_id, origin) を返す。origin は 'main' | 'sub'。"""
    parts = path.split(os.sep)
    if "subagents" in parts:
        i = parts.index("subagents")
        if i >= 1:
            return parts[i - 1], "sub"
    return os.path.basename(path)[:-6] if path.endswith(".jsonl") else os.path.basename(path), "main"


def session_files(transcript_path: str):
    """あるセッションに属する全ファイル（メイン + サブエージェント）を返す。"""
    sid, _ = session_of(transcript_path)
    parts = transcript_path.split(os.sep)
    if "subagents" in parts:
        proj_dir = os.sep.join(parts[: parts.index("subagents") - 1])
    else:
        proj_dir = os.path.dirname(transcript_path)
    files = []
    main = os.path.join(proj_dir, sid + ".jsonl")
    if os.path.exists(main):
        files.append(main)
    files.extend(sorted(glob.glob(os.path.join(proj_dir, sid, "subagents", "*.jsonl"))))
    return sid, files


def all_files():
    return sorted(
        glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
        + glob.glob(os.path.join(PROJECTS, "*", "*", "subagents", "*.jsonl"))
    )


# ---------------------------------------------------------------------------
# 増分読み込み
# ---------------------------------------------------------------------------

def epoch_and_day(ts_iso: str, fallback: int):
    if not ts_iso or not _ISO.match(ts_iso):
        return fallback, time.strftime("%Y-%m-%d", time.localtime(fallback))
    try:
        dt = datetime.strptime(ts_iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        ep = int(dt.timestamp())
        return ep, time.strftime("%Y-%m-%d", time.localtime(ep))
    except ValueError:
        return fallback, time.strftime("%Y-%m-%d", time.localtime(fallback))


def read_new_bytes(con, path):
    """前回の続きから読む。返り値は (bytes, new_offset) で、行の途中では切らない。"""
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    row = con.execute("SELECT size, offset, mtime FROM files WHERE path=?", (path,)).fetchone()
    offset = 0
    if row:
        prev_size, prev_offset, prev_mtime = row
        if st.st_size == prev_size and st.st_mtime == prev_mtime:
            return b"", prev_offset          # 変化なし
        offset = prev_offset if st.st_size >= prev_offset else 0   # 縮んだら読み直し
    with open(path, "rb") as fh:
        fh.seek(offset)
        buf = fh.read()
    cut = buf.rfind(b"\n")
    if cut < 0:
        return b"", offset                    # 完全な行がまだ無い
    return buf[: cut + 1], offset + cut + 1


def mark_scanned(con, path, new_offset):
    try:
        st = os.stat(path)
    except OSError:
        return
    con.execute(
        "INSERT INTO files(path,size,offset,mtime,scanned_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET size=excluded.size, offset=excluded.offset, "
        "mtime=excluded.mtime, scanned_at=excluded.scanned_at",
        (path, st.st_size, new_offset, st.st_mtime, int(time.time())),
    )


# ---------------------------------------------------------------------------
# 1 ファイルの取り込み
# ---------------------------------------------------------------------------

def ingest_file(con, path):
    """戻り値: 追加したイベント数。"""
    raw, new_offset = read_new_bytes(con, path)
    if raw is None:
        return 0
    sid, origin = session_of(path)
    now = int(time.time())
    added = 0
    ev_rows, cat_rows, hook_rows, exp_rows = [], [], [], []
    sess_first = sess_last = None
    sess_repo = sess_branch = None

    for line in raw.split(b"\n"):
        if not line.strip():
            continue

        # 露出（そのサーバー名が会話に載っていたか）は生バイト列で拾う。
        # tool_use に出ていなくても allowedTools 等に並ぶため、これが採用率の母数になる。
        for m in _MCP_MENTION.finditer(line):
            exp_rows.append((sid, "mcp:" + m.group(1).decode("utf-8", "replace")))

        try:
            d = json.loads(line)
        except Exception:
            continue

        rtype = d.get("type")
        ts_iso = d.get("timestamp") or ""

        if rtype == "attachment":
            att = d.get("attachment") or {}
            if not att.get("hookEvent"):
                continue
            ep, day = epoch_and_day(ts_iso, now)
            label = ""
            try:
                out = json.loads(att.get("stdout") or "{}")
                label = ((out.get("hookSpecificOutput") or {}).get("systemMessage") or "")[:300]
            except Exception:
                pass
            hook_rows.append((
                d.get("uuid") or f"{path}:{ep}:{att.get('hookName')}",
                ep, day, sid, origin, att.get("type") or "",
                att.get("hookEvent") or "", att.get("hookName") or "",
                (att.get("command") or "")[:200], att.get("toolUseID") or "", label,
            ))
            continue

        if rtype != "assistant":
            continue

        msg = d.get("message") or {}
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue

        ep, day = epoch_and_day(ts_iso, now)
        repo = os.path.basename(d.get("cwd") or "") or None
        branch = d.get("gitBranch") or None
        if sess_first is None or ep < sess_first:
            sess_first = ep
        if sess_last is None or ep > sess_last:
            sess_last = ep
        if repo:
            sess_repo, sess_branch = repo, branch

        for idx, blk in enumerate(content):
            if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                continue
            tid = blk.get("id") or f"{d.get('uuid')}#{idx}"
            name = blk.get("name") or "?"
            cats, detail = C.classify(name, blk.get("input"))
            head = detail if name == "Bash" else None
            ev_rows.append((tid, ep, day, sid, origin, repo, branch, name, (detail or "")[:120], head))
            for cat in cats:
                cat_rows.append((tid, cat))
            added += 1

    if ev_rows:
        con.executemany(
            "INSERT OR IGNORE INTO events(tid,ts,day,session,origin,repo,branch,tool,detail,head) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)", ev_rows)
        con.executemany("INSERT OR IGNORE INTO event_cats(tid,cat) VALUES(?,?)", cat_rows)
    if hook_rows:
        con.executemany(
            "INSERT OR IGNORE INTO hook_fires"
            "(uid,ts,day,session,origin,atype,event,hook_name,command,tool_use_id,label) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)", hook_rows)
    if exp_rows:
        con.executemany("INSERT OR IGNORE INTO exposure(session,cat) VALUES(?,?)",
                        sorted(set(exp_rows)))
    if sess_first is not None:
        con.execute(
            "INSERT INTO sessions(session,first_ts,last_ts,repo,branch) VALUES(?,?,?,?,?) "
            "ON CONFLICT(session) DO UPDATE SET "
            "first_ts=MIN(first_ts,excluded.first_ts), last_ts=MAX(last_ts,excluded.last_ts), "
            "repo=COALESCE(excluded.repo,repo), branch=COALESCE(excluded.branch,branch)",
            (sid, sess_first, sess_last, sess_repo, sess_branch))

    mark_scanned(con, path, new_offset)
    return added


# ---------------------------------------------------------------------------
# ステータスライン用の事前レンダリング
#   ステータスラインは毎描画で走るので、**集計も整形もここで済ませて 1 行を書き出す**。
#   ステータスライン側は cat するだけ（jq も python も起動しない）。
# ---------------------------------------------------------------------------

GREEN, DIM, CYAN, YELLOW, RESET, BOLD = (
    "\033[32m", "\033[2m", "\033[36m", "\033[33m", "\033[0m", "\033[1m")


def _keys(env_name, default):
    env = os.environ.get(env_name, "").strip()
    if env:
        return [k.strip() for k in env.split(",") if k.strip()]
    return list(default)


def focus_keys():
    return _keys("CLAUDE_TOOLSTATS_FOCUS", C.DEFAULT_FOCUS)


def watch_keys():
    return _keys("CLAUDE_TOOLSTATS_WATCH", C.DEFAULT_WATCH)


def render_session(con, sid):
    counts = dict(con.execute(
        "SELECT c.cat, COUNT(*) FROM event_cats c JOIN events e ON e.tid=c.tid "
        "WHERE e.session=? GROUP BY c.cat", (sid,)).fetchall())
    total, subs = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(origin='sub'),0) FROM events WHERE session=?",
        (sid,)).fetchone()
    last = con.execute(
        "SELECT ts, tool, detail FROM events WHERE session=? ORDER BY ts DESC, rowid DESC LIMIT 1",
        (sid,)).fetchone()

    focus = focus_keys()
    watch = watch_keys()
    # 既定 0。「python·44 grep·8」のような雑多な内訳はステータスラインでは読まれないため出さない
    # （知りたくなったら /tool-usage で全件見る）。1 以上にすると使用量上位が付く。
    max_others = int(os.environ.get("CLAUDE_TOOLSTATS_MAX_OTHERS", "0"))

    # FOCUS: 0 でも出す（使わなかったことが情報なので）
    parts = []
    for k in focus:
        n = counts.get(k, 0)
        col = GREEN + BOLD if n else DIM
        parts.append(f"{col}{C.label(k)}·{n}{RESET}")

    # WATCH: 非 0 のときだけ出す（作業領域で決まる道具）
    wparts = [f"{CYAN}{C.label(k)}{RESET}{DIM}·{counts[k]}{RESET}"
              for k in watch if counts.get(k)]

    oparts = []
    if max_others > 0:
        skip = set(focus) | set(watch)
        others = [(k, v) for k, v in counts.items()
                  if k not in skip and not k.startswith(("skill:", "agent:"))]
        others.sort(key=lambda kv: (-kv[1], kv[0]))
        oparts = [f"{DIM}{C.label(k)}·{v}{RESET}" for k, v in others[:max_others]]

    tail = f"{DIM}Σ{RESET}{total}"
    if subs:
        tail += f"{DIM}+sub{subs}{RESET}"

    seg = "🧰 " + " ".join(parts)
    for group in (wparts, oparts):
        if group:
            seg += f" {DIM}┃{RESET} " + " ".join(group)
    seg += f" {DIM}┃{RESET} " + tail

    os.makedirs(D.STATE_DIR, exist_ok=True)
    _atomic_write(os.path.join(D.STATE_DIR, sid + ".line"), seg)

    if last:
        ts, tool, detail = last
        if tool == "Bash":
            disp = f"Bash▸{detail}" if detail else "Bash"
        elif tool.startswith("mcp__"):
            m = re.match(r"^mcp__([^_]+(?:[-_.][^_]+)*)__(.+)$", tool)
            disp = f"{m.group(1)}▸{m.group(2)}" if m else tool
        else:
            disp = f"{tool}▸{detail}" if detail and len(detail) <= 24 else tool
        _atomic_write(os.path.join(D.STATE_DIR, sid + ".last"), f"{ts}\t{disp}")


def _atomic_write(path, text):
    tmp = path + f".tmp{os.getpid()}"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------

def _lock(name, blocking):
    os.makedirs(D.STATE_DIR, exist_ok=True)
    fh = open(os.path.join(D.STATE_DIR, name), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB))
    except OSError:
        return None
    return fh


def _prune_state(days=30):
    """古いセッションの事前レンダリング結果を捨てる。

    1 セッションあたり数百バイトだが、消さないと際限なく増える
    （ロックファイルは残す。使い回されるので消す意味がない）。
    """
    cutoff = time.time() - days * 86400
    try:
        entries = os.listdir(D.STATE_DIR)
    except OSError:
        return
    for name in entries:
        if not (name.endswith(".line") or name.endswith(".last")):
            continue
        path = os.path.join(D.STATE_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="transcript path（このセッションだけ取り込む）")
    ap.add_argument("--hook-payload", help="hook の stdin JSON を書いたファイル（読んだら消す）")
    ap.add_argument("--all", action="store_true", help="全 transcript を増分走査")
    ap.add_argument("--reset", action="store_true", help="DB を捨てて作り直す")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if os.environ.get("CLAUDE_TOOLSTATS_DISABLE", "").lower() in ("1", "true", "yes"):
        return 0

    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(D.DB_PATH + suffix)
            except OSError:
                pass

    if args.hook_payload:
        # hook 側は stdin をファイルに落として即 return する（同期処理を最小化するため）。
        # ここで transcript_path を取り出し、読み終わったらファイルを消す。
        try:
            with open(args.hook_payload) as fh:
                payload = json.load(fh)
            args.session = payload.get("transcript_path") or ""
        except Exception:
            args.session = ""
        finally:
            try:
                os.remove(args.hook_payload)
            except OSError:
                pass
        if not args.session:
            return 0
        args.quiet = True

    con = D.connect()
    added = 0

    if args.session:
        sid, files = session_files(os.path.expanduser(args.session))
        lk = _lock(f"{sid}.lock", blocking=False)
        if lk is None:
            return 0          # 別プロセスが同じセッションを処理中。次の PostToolUse で追いつく
        for f in files:
            added += ingest_file(con, f)
        con.commit()
        render_session(con, sid)
        if not args.quiet:
            print(f"session {sid}: +{added} events ({len(files)} files)")
        return 0

    if args.all:
        lk = _lock(".all.lock", blocking=True)
        _prune_state(days=30)
        files = all_files()
        t0 = time.time()
        for i, f in enumerate(files, 1):
            added += ingest_file(con, f)
            if i % 200 == 0:
                con.commit()
        con.commit()
        if not args.quiet:
            print(f"scanned {len(files)} files: +{added} events in {time.time()-t0:.1f}s")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
