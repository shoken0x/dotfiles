#!/bin/bash
#
# advise_context7.sh のスモークテスト。
#
# この hook の失敗形は「沈黙」であり、**壊れている状態と正常な状態は見た目が同じ**。
# したがって陽性（発火するはず）と陰性（黙るはず）の両方を固定する。
#
#   bash ~/.claude/hooks/test_advise_context7.sh

set -uo pipefail

HOOK="$(cd "$(dirname "$0")" && pwd)/advise_context7.sh"
PASS=0
FAIL=0
# プロジェクト側ガードが実リポジトリで誤発火しないよう、既定は空ディレクトリを指す
SANDBOX="$(mktemp -d)"
trap 'rm -rf "${SANDBOX}"' EXIT

# 期待: 発火する（stdout が非空）
expect_fire() {
  local name="$1" payload="$2"
  local out
  out="$(printf '%s' "${payload}" | CLAUDE_PROJECT_DIR="${SANDBOX}" bash "${HOOK}" 2>/dev/null)"
  if [ -n "${out}" ] && printf '%s' "${out}" | grep -q "Context7"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1)); echo "FAIL(発火せず): ${name}"
  fi
}

# 期待: 黙る（stdout が空）
expect_silent() {
  local name="$1" payload="$2" root="${3:-${SANDBOX}}"
  local out
  out="$(printf '%s' "${payload}" | CLAUDE_PROJECT_DIR="${root}" bash "${HOOK}" 2>/dev/null)"
  if [ -z "${out}" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1)); echo "FAIL(黙るはずが発火): ${name}"
  fi
}

wf() { printf '{"tool_name":"WebFetch","tool_input":{"url":"%s"}}' "$1"; }
ws() { printf '{"tool_name":"WebSearch","tool_input":{"query":"%s"}}' "$1"; }

# ---------------------------------------------------------------- 陽性
expect_fire "react.dev"            "$(wf https://react.dev/reference/react/useEffect)"
expect_fire "Rails ガイド"          "$(wf https://guides.rubyonrails.org/active_record_querying.html)"
expect_fire "rubydoc.info"         "$(wf https://rubydoc.info/gems/sidekiq)"
expect_fire "Tailwind"             "$(wf https://tailwindcss.com/docs/theme)"
expect_fire "Cloudflare Workers"   "$(wf https://developers.cloudflare.com/workers/runtime-apis/fetch/)"
expect_fire "Drizzle"              "$(wf https://orm.drizzle.team/docs/rqb)"
expect_fire "Bun (パス接頭辞)"      "$(wf https://bun.sh/docs/api/http)"
expect_fire "Node API"             "$(wf https://nodejs.org/api/fs.html)"
expect_fire "Node バージョン固定"   "$(wf https://nodejs.org/docs/latest-v20.x/api/fs.html)"
expect_fire "GitHub wiki"          "$(wf https://github.com/oraios/serena/wiki/Setup)"
expect_fire "GitHub README"        "$(wf https://github.com/foo/bar/blob/main/README.md)"
expect_fire "WebSearch site:"      "$(ws 'site:react.dev useEffect cleanup')"
expect_fire "スキーム無し URL"      "$(wf react.dev/reference/react/useEffect)"

# ---------------------------------------------------------------- 陰性
expect_silent "Heroku 運用ドキュメント" "$(wf https://devcenter.heroku.com/articles/getting-started)"
expect_silent "GitHub issue"          "$(wf https://github.com/foo/bar/issues/123)"
expect_silent "GitHub PR"             "$(wf https://github.com/foo/bar/pull/2574)"
expect_silent "Cloudflare の非 Workers" "$(wf https://developers.cloudflare.com/dns/manage-dns-records/)"
expect_silent "Supabase の非 docs"     "$(wf https://supabase.com/pricing)"
expect_silent "ブログ"                 "$(wf https://example.com/blog/rails-8-tips)"
expect_silent "一般語の WebSearch"     "$(ws 'rails validation error 原因')"
expect_silent "url なし"               '{"tool_name":"WebFetch","tool_input":{}}'
expect_silent "tool_input が配列"      '{"tool_name":"WebFetch","tool_input":[]}'
expect_silent "対象外ツール"           '{"tool_name":"Bash","tool_input":{"command":"grep -rn foo app/"}}'
expect_silent "壊れた JSON"            'not json at all'

# --------------------------------- プロジェクト側 hook が既に助言を持つ場合は黙る
PROJ="$(mktemp -d)"
mkdir -p "${PROJ}/.claude/hooks/lib"
printf 'CONTEXT7_LABEL = "Context7 を先に引く"\n' > "${PROJ}/.claude/hooks/lib/tool_selection_advice.py"
printf '{"hooks":{"PreToolUse":[{"matcher":"Bash|WebFetch|WebSearch","hooks":[{"command":"bash .claude/hooks/advise_tool_selection.sh"}]}]}}\n' \
  > "${PROJ}/.claude/settings.json"
expect_silent "プロジェクト側が担当" "$(wf https://react.dev/reference/react/useEffect)" "${PROJ}"

# 判定材料が片方だけなら黙ってはいけない（登録されていない hook は発火しないため）
printf '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"command":"bash .claude/hooks/pre_push_check.sh"}]}]}}\n' \
  > "${PROJ}/.claude/settings.json"
expect_fire_in_proj() {
  local out
  out="$(printf '%s' "$(wf https://react.dev/reference/react/useEffect)" \
    | CLAUDE_PROJECT_DIR="${PROJ}" bash "${HOOK}" 2>/dev/null)"
  if [ -n "${out}" ]; then PASS=$((PASS + 1));
  else FAIL=$((FAIL + 1)); echo "FAIL(発火せず): プロジェクト側は未登録なので user 側が担当"; fi
}
expect_fire_in_proj
rm -rf "${PROJ}"

echo "${PASS} pass / ${FAIL} fail"
[ "${FAIL}" -eq 0 ]
