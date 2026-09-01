#!/usr/bin/env python3
"""`br doctor --repair` が root .gitignore の `.beads/` を消す実行を判定する。

guard_br_doctor_gitignore.sh から呼ばれる。stdin に Claude Code の PreToolUse の
tool 入力 JSON を受け取り、判定結果を1行で stdout に出す:

    ALLOW           … 通してよい
    NO_SKIP         … --repair だが --skip が無い
    WRONG_SKIP:a,b  … --skip はあるが当該 id が含まれていない
    VERIFY_ID       … 当該 id つきの --skip がある（呼び出し側で id の実在を検証する）
    PARSE_ERROR     … br の起動に見えるが解析できなかった（fail-closed）

⚠️ シェルに埋め込まず独立したファイルにしてあるのは、正規表現に含まれる引用符が
   `python3 -c '...'` の単一引用符を閉じてしまい hook 全体が syntax error で
   壊れたため（実際に発生）。判定ロジックはここに置く。
"""

import json
import re
import shlex
import sys

FILTER_ID = "fm-configs-gitignore-leaking-beads"

# 変長の値を取るフラグ。clap の `--skip <SKIP>...` は次のフラグまで全てを値として取る。
VALUE_FLAGS = {"--skip", "--only"}

# heredoc の開始。`<<EOF` / `<<-EOF` / `<<'EOF'` / `<<"EOF"` を拾う。
# 引用符はエスケープで書く（このファイルは独立しているが、意図を明示するため）。
HEREDOC_START = re.compile(r"<<-?\s*([\"\x27]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# 解析不能時に fail-closed するかの判定。**セグメントが br の起動で始まっている**ことを要求する。
# 「文字列として br doctor --repair を含む」だけでは止めない
# （止めると、規約を書いた PR 本文や grep のパターンを誤ってブロックする）。
BR_INVOCATION = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"    # 環境変数代入
    r"(?:(?:command|exec|sudo|time|nohup)\s+)*"   # 前置きコマンド
    r"(?:\S*/)?br(?:\s|$)"                        # br 本体（絶対パス可）
)

PREFIX_WORDS = ("command", "exec", "sudo", "time", "nohup")


def read_command(stream):
    try:
        d = json.load(stream)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    ti = d.get("tool_input") or {}
    cmd = ti.get("command")
    return cmd if isinstance(cmd, str) else None


def strip_heredocs(text):
    """heredoc の本体を落とす。

    🔴 heredoc の中身は**データであってコマンドではない**。落とさないと、PR 本文や
    ドキュメントに `br doctor --repair` と書いただけの
    `gh pr create --body-file` / `cat > f <<EOF` が誤ってブロックされる
    （実際にこの hook の PR を作ろうとして自分にブロックされた）。
    `<<` を含む行そのものは本物のコマンドなので残す。
    """
    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = [m.group(2) for m in HEREDOC_START.finditer(line)]
        i += 1
        for d in delims:
            while i < len(lines) and lines[i].strip() != d:
                i += 1
            i += 1  # 終端行自体も落とす
    return "\n".join(out)


def _collect(tokens, i):
    """変長フラグの値を次のフラグに当たるまで集める。カンマ区切りも展開する。"""
    vals = []
    j = i + 1
    while j < len(tokens) and not tokens[j].startswith("-"):
        vals.extend(v for v in tokens[j].split(",") if v)
        j += 1
    return vals, j


def _find_br(tokens):
    """br 実行ファイルの位置。見つからなければ None。"""
    for k, t in enumerate(tokens):
        if t.rsplit("/", 1)[-1] == "br":
            return k
        if "=" in t and not t.startswith("-"):
            continue          # FOO=bar の環境変数代入
        if t in PREFIX_WORDS:
            continue
        return None
    return None


def _is_doctor(rest):
    """フラグを飛ばして最初の非フラグ語が `doctor` か。"""
    m = 0
    while m < len(rest):
        t = rest[m]
        if t in VALUE_FLAGS:
            _, m = _collect(rest, m)
            continue
        if t.startswith("-"):
            m += 1
            continue
        return t == "doctor"
    return False


def analyze(seg):
    """セグメントが gitignore fixer を走らせるなら理由文字列、そうでなければ None。"""
    try:
        tokens = shlex.split(seg)
    except ValueError:
        if (BR_INVOCATION.match(seg) and "doctor" in seg
                and re.search(r"--repair|--fix", seg)):
            return "PARSE_ERROR"
        return None

    if not tokens:
        return None
    idx = _find_br(tokens)
    if idx is None:
        return None

    rest = tokens[idx + 1:]
    if not _is_doctor(rest):
        return None

    dry_run = False
    repair = False
    skip_vals = []
    only_vals = []
    i = 0
    while i < len(rest):
        t = rest[i]
        if t in ("--repair", "--fix"):
            repair = True
        elif t == "--dry-run":
            dry_run = True
        elif t in VALUE_FLAGS:
            vals, i = _collect(rest, i)
            (skip_vals if t == "--skip" else only_vals).extend(vals)
            continue
        elif t.startswith("--skip=") or t.startswith("--only="):
            flag, _, raw = t.partition("=")
            vals = [v for v in raw.split(",") if v]
            (skip_vals if flag == "--skip" else only_vals).extend(vals)
        i += 1

    if not repair:
        return None
    if dry_run:
        return None
    # `--only` が指定され、この fixer が列挙されていなければ走らない
    if only_vals and FILTER_ID not in only_vals:
        return None
    if FILTER_ID in skip_vals:
        return "VERIFY_ID"
    if skip_vals:
        return "WRONG_SKIP:" + ",".join(skip_vals)
    return "NO_SKIP"


def verdict_for(cmd):
    if not cmd:
        return "ALLOW"
    for seg in re.split(r"&&|\|\||;|\||\n", strip_heredocs(cmd)):
        r = analyze(seg)
        if r:
            return r
    return "ALLOW"


def main():
    print(verdict_for(read_command(sys.stdin)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
