#!/usr/bin/env python3
"""PR を作る前に agy レビューを済ませたかを確かめる PreToolUse(Bash) hook（個人用）。

既定では、PR を作る前に agy（Antigravity CLI）にレビューさせる。
`gh pr create` を実行しようとしたとき、同じセッションの記録（transcript）に
**直前の PR 作成より後で** agy-review skill を読み込んだ跡が無ければ止める。

- 読み込みの跡: Skill ツールで agy-review を呼んだ / ユーザーが /agy-review と打った
- 「直前の PR 作成より後」で見るのは、1 つのセッションで PR を 2 本作るときに、
  1 本目のレビューで 2 本目まで通ってしまわないようにするため
- ユーザーが「agy レビューは不要」と明示したときだけ、コマンドの先頭に
  `AGY_REVIEW=skip` を付けて通す
- agy が入っていない環境では何もしない（このファイルは個人の ~/.claude にだけ置く。
  チームのリポジトリの hook には入れない）

止めるときは permissionDecision=deny で理由を返す（Claude に見える）。
記録を読めずに確認できなかったときは止めず、そのことを systemMessage で知らせる。

  テスト: bash ~/.claude/hooks/test_require_agy_review_before_pr.sh
"""

import json
import os
import re
import shutil
import sys

# `gh pr create` を「コマンドとして」実行しているときだけ拾う。
# 行頭か区切り（; & | ( then do）の直後に、環境変数の代入を挟んで現れる形。
# `echo "gh pr create"` のような文字列は拾わない（ヒアドキュメントの行頭は拾ってしまう）
PR_CREATE_RE = re.compile(
    r"(?:^|[;&|(]|\bthen\b|\bdo\b)\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*gh\s+pr\s+create\b",
    re.M,
)
SKIP_RE = re.compile(r"(?:^|[\s;&|(])AGY_REVIEW=skip\b")
SLASH_MARK = "<command-name>/agy-review</command-name>"

REASON = (
    "🔴 PR を作る前に agy レビューを行う決まりです（個人設定の hook: "
    "~/.claude/hooks/require_agy_review_before_pr.py）。このセッションでは、直前の PR 作成より後に "
    "agy-review skill を読み込んだ跡がありません。Skill ツールで agy-review を読み込み、その手順で"
    "差分をレビューしてから、もう一度 gh pr create を実行してください。"
    "ユーザーが「agy レビューは不要」と明示した場合に限り、コマンドの先頭に AGY_REVIEW=skip を付けて実行してください。"
)


def agy_installed():
    # hook は Claude Code の環境で動くので、PATH に ~/.local/bin が無いことがある
    return shutil.which("agy") is not None or os.path.exists(os.path.expanduser("~/.local/bin/agy"))


def scan(path):
    """記録の行番号で (最後に agy-review を読み込んだ行, 最後に PR 作成が成功した行) を返す。"""
    last_review = None
    last_pr = None
    pr_ids = {}
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            # 5MB を超える記録もあるので、関係する行だけを JSON として読む
            if "agy-review" not in line and "gh" not in line and "tool_result" not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            content = (d.get("message") or {}).get("content")
            if isinstance(content, str):
                if d.get("type") == "user" and SLASH_MARK in content:
                    last_review = i
                continue
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                kind = b.get("type")
                if kind == "tool_use":
                    inp = b.get("input") or {}
                    if b.get("name") == "Skill" and inp.get("skill") == "agy-review":
                        last_review = i
                    elif b.get("name") == "Bash" and PR_CREATE_RE.search(str(inp.get("command") or "")):
                        pr_ids[b.get("id")] = i
                elif kind == "tool_result":
                    # 失敗した PR 作成は数えない（まだ PR はできていない）
                    if b.get("tool_use_id") in pr_ids and not b.get("is_error"):
                        last_pr = i
                elif kind == "text" and d.get("type") == "user" and SLASH_MARK in (b.get("text") or ""):
                    last_review = i
    return last_review, last_pr


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not isinstance(cmd, str) or not PR_CREATE_RE.search(cmd):
        return 0
    if SKIP_RE.search(cmd) or not agy_installed():
        return 0

    path = data.get("transcript_path") or ""
    try:
        last_review, last_pr = scan(path)
    except (OSError, UnicodeDecodeError) as e:
        print(json.dumps({
            "systemMessage": "⚠️ agy レビューの有無を確認できなかった（記録を読めない: {}）。PR 作成は止めていない".format(e),
        }, ensure_ascii=False))
        return 0

    if last_review is not None and (last_pr is None or last_review > last_pr):
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
