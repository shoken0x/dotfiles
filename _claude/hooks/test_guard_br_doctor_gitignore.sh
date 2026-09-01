#!/bin/bash
#
# guard_br_doctor_gitignore.sh のスモークテスト。
#
# 🔴 この hook は「通すときは無言」なので、ロジックが壊れても正常な沈黙と区別がつかない。
#    しかも守っている対象が「黙って .gitignore が書き換わる」事故なので、
#    hook が黙って死ぬと **対策したつもりで無防備** になる。
#    そのため陽性（止まるべきものが止まる）・陰性（通すべきものが通る）の両方を固定し、
#    最後に**変異テスト**（hook を壊したらこのテストが落ちること）まで確認する。
#
# `br` はスタブに差し替えるので、実際の br や .beads/ の状態には依存しない。

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="${HOOK_DIR}/guard_br_doctor_gitignore.sh"
FILTER_ID="fm-configs-gitignore-leaking-beads"

[ -f "${HOOK}" ] || { echo "❌ hook が見つかりません: ${HOOK}"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

fail=0
pass=0

# --- br のスタブ -------------------------------------------------------------
# GOOD: capabilities に FILTER_ID を含む（= id は実在する）
mkdir -p "${WORK}/bin_good"
cat > "${WORK}/bin_good/br" <<EOF
#!/bin/bash
if [ "\$1" = "doctor" ] && [ "\$2" = "capabilities" ]; then
  echo '{"fixers":[{"id":"doctor.gitignore_repair","filter_ids":["${FILTER_ID}"]}]}'
  exit 0
fi
exit 0
EOF
# RENAMED: capabilities に FILTER_ID が無い（= br 側で改名された状況）
mkdir -p "${WORK}/bin_renamed"
cat > "${WORK}/bin_renamed/br" <<'EOF'
#!/bin/bash
if [ "$1" = "doctor" ] && [ "$2" = "capabilities" ]; then
  echo '{"fixers":[{"id":"doctor.gitignore_repair","filter_ids":["fm-configs-gitignore-renamed-v2"]}]}'
  exit 0
fi
exit 0
EOF
# BROKEN: capabilities が何も返さない（判断できない状況）
mkdir -p "${WORK}/bin_broken"
cat > "${WORK}/bin_broken/br" <<'EOF'
#!/bin/bash
exit 1
EOF
chmod +x "${WORK}"/bin_*/br

# --- ヘルパー ---------------------------------------------------------------
# run <stub-dir> <command> -> exit code を返し、stderr を ${LAST_ERR} に入れる
LAST_ERR=""
run() {
  local stub="$1" cmd="$2" rc
  local errfile="${WORK}/err.$$"
  printf '%s' "$(python3 -c '
import json, sys
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}}))
' "${cmd}")" | PATH="${WORK}/${stub}:${PATH}" bash "${HOOK}" 2>"${errfile}"
  rc=$?
  LAST_ERR="$(cat "${errfile}")"
  rm -f "${errfile}"
  return ${rc}
}

assert_block() {
  local label="$1" stub="$2" cmd="$3"
  run "${stub}" "${cmd}"
  local rc=$?
  if [ "${rc}" -eq 2 ]; then
    pass=$((pass + 1))
  else
    echo "❌ ブロックされるべきなのに exit ${rc}: ${label}"
    echo "   cmd: ${cmd}"
    fail=1
  fi
}

assert_allow() {
  local label="$1" stub="$2" cmd="$3"
  run "${stub}" "${cmd}"
  local rc=$?
  if [ "${rc}" -eq 0 ]; then
    pass=$((pass + 1))
  else
    echo "❌ 通すべきなのに exit ${rc}: ${label}"
    echo "   cmd: ${cmd}"
    echo "   stderr: ${LAST_ERR}"
    fail=1
  fi
}

echo "=== 陽性: ブロックされるべきコマンド ==="

assert_block "素の --repair"                bin_good "br doctor --repair"
assert_block "別名 --fix"                   bin_good "br doctor --fix"
assert_block "--skip が別の id"             bin_good "br doctor --repair --skip fm-caches_indexes-db-bloat"
assert_block "--skip が typo（1文字欠け）"  bin_good "br doctor --repair --skip fm-configs-gitignore-leaking-bead"
assert_block "&& で連結"                    bin_good "cd /tmp && br doctor --repair"
assert_block "; で連結"                      bin_good "echo hi ; br doctor --repair"
assert_block "パイプの後段"                 bin_good "true | br doctor --repair"
assert_block "絶対パス起動"                 bin_good "/opt/homebrew/bin/br doctor --repair"
assert_block "env 代入つき"                 bin_good "RUST_LOG=debug br doctor --repair"
assert_block "--only が当該 fixer を含む"   bin_good "br doctor --repair --only ${FILTER_ID}"
assert_block "フラグ順が逆"                 bin_good "br doctor --skip other-id --repair"
assert_block "クォート未閉（解析不能）"     bin_good "br doctor --repair --skip 'unclosed"
# heredoc を落としたあとに残る本物の起動を見落とさないこと
heredoc_then_real="$(printf '%s\n' \
  "cat > /tmp/note.md <<'EOF'" \
  "メモ: 素の実行は危険" \
  "EOF" \
  "br doctor --repair")"
assert_block "heredoc の後に本物の起動"     bin_good "${heredoc_then_real}"
# 🔴 これがこの hook の核心: --skip は付いているが br 側に id が無い（改名された）
assert_block "id が改名されている"          bin_renamed "br doctor --repair --skip ${FILTER_ID}"

echo "=== 陰性: 通すべきコマンド ==="

assert_allow "--dry-run つき"               bin_good "br doctor --repair --dry-run"
assert_allow "正しい --skip"                bin_good "br doctor --repair --skip ${FILTER_ID}"
assert_allow "正しい --skip（= 形式）"      bin_good "br doctor --repair --skip=${FILTER_ID}"
assert_allow "--skip がカンマ区切りに含む"  bin_good "br doctor --repair --skip other-id,${FILTER_ID}"
assert_allow "--repair なし"                bin_good "br doctor"
assert_allow "--quick（読み取り専用）"      bin_good "br doctor --quick"
assert_allow "robot-docs"                   bin_good "br doctor robot-docs"
assert_allow "doctor を含まない"            bin_good "br list --status open"
assert_allow "br 以外のコマンド"            bin_good "echo doctor --repair"
assert_allow "--only が当該 fixer を含まない" bin_good "br doctor --repair --only fm-caches_indexes-db-bloat"
# コミットメッセージ等に文字列として現れるだけのケースを止めてはいけない
assert_allow "commit メッセージ内の文字列"  bin_good "git commit -m 'br doctor --repair の規約を追加'"
# capabilities が取れない環境で作業を詰まらせない（判断材料が無い）
assert_allow "capabilities が取れない"      bin_broken "br doctor --repair --skip ${FILTER_ID}"

# 🔴 実際に踏んだ誤爆の回帰テスト。
#    この hook の PR を作ろうとして `gh pr create --body-file` の heredoc に
#    `br doctor --repair` と書いたところ、heredoc で shlex の解析が落ちて
#    fail-closed パスが発火し **自分の PR 作成がブロックされた**。
#    heredoc の中身はデータであってコマンドではないので、解析前に落とす。
heredoc_quoted="$(printf '%s\n' \
  "cat > /tmp/body.md <<'MDEOF'" \
  "## 規約" \
  "  br doctor --repair --skip ${FILTER_ID}" \
  "  br doctor --repair" \
  "MDEOF" \
  "gh pr create --body-file /tmp/body.md")"
assert_allow "heredoc 内の文字列（誤爆の回帰）" bin_good "${heredoc_quoted}"

heredoc_plain="$(printf '%s\n' \
  "cat <<EOF > /tmp/x" \
  "br doctor --repair" \
  "EOF")"
assert_allow "heredoc <<EOF 内の文字列"     bin_good "${heredoc_plain}"

# 文字列として現れるだけの他の形
assert_allow "echo で文字列として出力"      bin_good "echo 'run: br doctor --repair'"
assert_allow "grep のパターン"              bin_good "grep -rn 'br doctor --repair' CLAUDE.md"

echo "=== 無効化スイッチ ==="
if printf '%s' '{"tool_name":"Bash","tool_input":{"command":"br doctor --repair"}}' \
  | HRG_BR_DOCTOR_GUARD=false PATH="${WORK}/bin_good:${PATH}" bash "${HOOK}" >/dev/null 2>&1; then
  pass=$((pass + 1))
else
  echo "❌ HRG_BR_DOCTOR_GUARD=false で無効化できていない"
  fail=1
fi

echo "=== メッセージの内容 ==="
run bin_good "br doctor --repair"
for needle in "${FILTER_ID}" "2>&1" "git status"; do
  case "${LAST_ERR}" in
    *"${needle}"*) pass=$((pass + 1)) ;;
    *) echo "❌ ブロックメッセージに '${needle}' が含まれていない"; fail=1 ;;
  esac
done

echo "=== ~/.claude/settings.json の matcher に載っているか ==="
# 🔴 matcher から漏れると、このテストが全て green のまま hook が一度も呼ばれない。
#    project スコープではなく **user スコープ**に登録する（どの worktree からでも効かせるため）。
SETTINGS="${HOME}/.claude/settings.json"
if [ -f "${SETTINGS}" ]; then
  if python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
name = "guard_br_doctor_gitignore.sh"
for m in d.get("hooks", {}).get("PreToolUse", []):
    if any(name in (h.get("command") or "") for h in m.get("hooks", [])):
        sys.exit(0 if "Bash" in (m.get("matcher") or "").split("|") else 1)
sys.exit(1)
' "${SETTINGS}"; then
    pass=$((pass + 1))
  else
    echo "❌ ~/.claude/settings.json の PreToolUse / matcher に Bash として登録されていない"
    fail=1
  fi
else
  echo "❌ ${SETTINGS} が見つかりません"
  fail=1
fi

echo "=== 判定ロジックの所在と構文 ==="
GUARD_PY="${HOOK_DIR}/lib/br_doctor_guard.py"
if [ -f "${GUARD_PY}" ] && python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "${GUARD_PY}"; then
  pass=$((pass + 1))
else
  echo "❌ ${GUARD_PY} が無い、または Python として壊れている"
  fail=1
fi
# 🔴 hook 本体が bash として壊れると、bash は syntax error で exit 2 を返す
#    = **全ての Bash 呼び出しがブロックされる**（実際に発生した）。構文を固定する。
if bash -n "${HOOK}"; then
  pass=$((pass + 1))
else
  echo "❌ hook 本体が bash として壊れている（壊れると全 Bash 呼び出しがブロックされる）"
  fail=1
fi

echo "=== 変異テスト: hook を壊したらこのテストが落ちること ==="
# exit 2 を exit 0 に変えた（= ブロックしなくなった）コピーで、陽性が検出できることを確認する。
# これが無いと「テストが通っている」ことが「hook が効いている」ことの証拠にならない。
MUT="${WORK}/mutated.sh"
sed 's/^exit 2$/exit 0/; s/^  exit 2$/  exit 0/' "${HOOK}" > "${MUT}"
if ! grep -qE '^\s*exit 0$' "${MUT}"; then
  echo "❌ 変異テストの sed が効いていない（hook の exit 2 の書き方が変わった可能性）"
  fail=1
else
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"br doctor --repair"}}' \
    | PATH="${WORK}/bin_good:${PATH}" bash "${MUT}" >/dev/null 2>&1
  if [ $? -eq 2 ]; then
    echo "❌ 変異させた hook がまだ exit 2 を返している（変異が当たっていない）"
    fail=1
  else
    pass=$((pass + 1))
  fi
fi

echo ""
if [ "${fail}" -eq 0 ]; then
  echo "✅ guard_br_doctor_gitignore: ${pass} 件すべて通過"
  exit 0
fi
echo "❌ guard_br_doctor_gitignore: 失敗あり（通過 ${pass} 件）"
exit 1
