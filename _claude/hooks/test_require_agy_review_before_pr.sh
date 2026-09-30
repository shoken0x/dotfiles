#!/bin/bash
#
# require_agy_review_before_pr.py のテスト。
#
# この hook の失敗形は 2 つある。止めるべき PR 作成を黙って通す（沈黙）と、
# 関係ないコマンドまで止める（誤検知）。どちらも起きないことを、陽性と陰性の両方で固定する。
#
#   bash ~/.claude/hooks/test_require_agy_review_before_pr.sh

set -uo pipefail

HOOK="$(cd "$(dirname "$0")" && pwd)/require_agy_review_before_pr.py"
PASS=0
FAIL=0
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# --- 記録（transcript）の 1 行を作る部品 ---
skill_line() { printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"s%s","name":"Skill","input":{"skill":"%s","args":"agy に見せる"}}]}}\n' "$1" "$2"; }
pr_use_line() { printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"%s","name":"Bash","input":{"command":"gh pr create --base develop"}}]}}\n' "$1"; }
pr_result_line() { printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"%s","is_error":%s,"content":"https://github.com/o/r/pull/1"}]}}\n' "$1" "$2"; }
slash_line() { printf '{"type":"user","message":{"content":"<command-message>agy-review</command-message> <command-name>/agy-review</command-name>"}}\n'; }

payload() {  # payload <コマンド> <記録のパス>
  python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]},"transcript_path":sys.argv[2]}))' "$1" "$2"
}

run() { printf '%s' "$(payload "$1" "$2")" | python3 "${HOOK}" 2>/dev/null; }

expect_deny() {
  local name="$1" out
  out="$(run "$2" "$3")"
  if printf '%s' "${out}" | grep -q '"permissionDecision": "deny"'; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1)); echo "FAIL(止まらなかった): ${name} → ${out:-<出力なし>}"
  fi
}

expect_silent() {
  local name="$1" out
  out="$(run "$2" "$3")"
  if [ -z "${out}" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1)); echo "FAIL(黙るはずが出力): ${name} → ${out}"
  fi
}

NONE="${WORK}/none.jsonl";      : > "${NONE}"
REVIEWED="${WORK}/reviewed.jsonl"; skill_line 1 agy-review > "${REVIEWED}"
AFTER_PR="${WORK}/after_pr.jsonl"; { skill_line 1 agy-review; pr_use_line p1; pr_result_line p1 false; } > "${AFTER_PR}"
PR_FAILED="${WORK}/pr_failed.jsonl"; { skill_line 1 agy-review; pr_use_line p1; pr_result_line p1 true; } > "${PR_FAILED}"
SLASH_AFTER="${WORK}/slash_after.jsonl"; { skill_line 1 agy-review; pr_use_line p1; pr_result_line p1 false; slash_line; } > "${SLASH_AFTER}"
OTHER_SKILL="${WORK}/other_skill.jsonl"; skill_line 1 update-config > "${OTHER_SKILL}"

# --- 止まるはず ---
expect_deny "レビュー無しで PR 作成"                 "gh pr create --base develop" "${NONE}"
expect_deny "cd && の後の PR 作成も対象"             "cd /tmp/x && gh pr create -R o/r" "${NONE}"
expect_deny "PR を作った後の 2 本目はレビューし直す" "gh pr create --base develop" "${AFTER_PR}"
expect_deny "別の skill の引数に agy があっても数えない" "gh pr create" "${OTHER_SKILL}"

# --- 通すはず（何も出さない） ---
expect_silent "レビュー済みなら通す"                 "gh pr create --base develop" "${REVIEWED}"
expect_silent "失敗した PR 作成は数えない"           "gh pr create --base develop" "${PR_FAILED}"
expect_silent "PR の後に /agy-review したら通す"     "gh pr create --base develop" "${SLASH_AFTER}"
expect_silent "ユーザーが不要と明示したら skip で通す" "AGY_REVIEW=skip gh pr create --base develop" "${NONE}"
expect_silent "PR 作成以外のコマンドは対象外"        "ls -la" "${NONE}"
expect_silent "文字列の中の gh pr create は対象外"   'echo "gh pr create"' "${NONE}"

# --- agy が入っていない環境では何もしない ---
out="$(printf '%s' "$(payload "gh pr create" "${NONE}")" | HOME="${WORK}" PATH=/usr/bin:/bin python3 "${HOOK}" 2>/dev/null)"
if [ -z "${out}" ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "FAIL(agy が無いのに出力): ${out}"; fi

# --- 記録を読めないときは止めず、読めなかったことを知らせる ---
out="$(run "gh pr create" "${WORK}/does-not-exist.jsonl")"
if printf '%s' "${out}" | grep -q '"systemMessage"' && ! printf '%s' "${out}" | grep -q '"deny"'; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1)); echo "FAIL(記録が無いときの扱い): ${out:-<出力なし>}"
fi

echo "PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ]
