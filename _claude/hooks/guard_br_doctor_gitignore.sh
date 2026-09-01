#!/bin/bash
#
# Claude Code PreToolUse hook: `br doctor --repair` が root .gitignore の `.beads/` を
# 消すのを構造的に止める。
#
# 🔴 なぜ hook が必要か（テキストの規約では守られなかった実績がある）
#
#   PR #2622 で CLAUDE.md に「必ず --skip fm-configs-gitignore-leaking-beads を付ける」と
#   書いた。その **同じセッションの中で**、サブエージェントのブリーフに 🔴 で
#   「--dry-run を外して実行しないこと」と明記していたにもかかわらずエージェントが実行し、
#   `.beads/` の行が再び削除された（run 20260831T071826Z__a5a535 /
#   fixer doctor.gitignore_repair / op write_file / ok true）。
#   CLAUDE.md 自身が「CLAUDE.md に書いただけでは守られなかった実績がある … 効いたのは
#   常に hook」と記録しているとおり、テキストは人にもエージェントにも守られない。
#
# 何を止めるか
#
#   `br doctor` に `--repair`（または別名 `--fix`）が付いていて、かつ
#   fixer `doctor.gitignore_repair` が実際に走る組み合わせのときだけブロックする。
#   走らない条件（= 通す条件）は次の3つ:
#     1. `--dry-run` がある（書き込まない）
#     2. `--skip` に `fm-configs-gitignore-leaking-beads` がある
#     3. `--only` があり、その中に `fm-configs-gitignore-leaking-beads` が **無い**
#        （`--only` は列挙外の fixer を全て無効化するため、この fixer も走らない）
#
# 🔴 `--skip` の id が実在することまで検証する
#
#   `--skip` は **未知の id を黙って無視する**（typo でもエラーにならず exit 0 で
#   書き込みが走る。br 0.5.3 実測）。そのため「--skip が付いている」だけでは通さず、
#   `br doctor capabilities --format json` の `fixers[].filter_ids` に id が実在することを
#   確認する。br 側で id が改名されたら**通さずに止める**（fail-closed）。
#
# 🔴 exit code は 2 でなければブロックにならない
#
#   公式ドキュメント: PreToolUse は exit 2 で「Blocks the tool call」。
#   一方 **exit 1 はブロックしない**（"Claude Code treats exit code 1 as a
#   non-blocking error and proceeds with the action"）。
#   ここを 1 にすると「止めているつもりで素通り」になり、直したい失敗そのものになる。
#
# 🔴 permissionDecision は出さない（exit 2 + stderr でブロックする）
#
#   公式ドキュメントは JSON の `hookSpecificOutput.permissionDecision: "deny"` も示すが、
#   このリポジトリの既知の落とし穴として **permissionDecision は出さない**ことになっている
#   （`"allow"` は権限フローを迂回し、`"defer"` は additionalContext を黙って無視させる。
#   playbook b-mt9ojgbo-ec5epw）。exit 2 は JSON の有無によらずブロックするので、
#   JSON が壊れたときに fail-open しない点でもこちらが安全。
#
# 無効化: export HRG_BR_DOCTOR_GUARD=false
#
# 置き場所: **user スコープ**（~/.claude/hooks/）。リポジトリには置いていない。
#   beads は shoken 個人しか使っておらずチーム共有が不要な一方、`.beads/` は main checkout に
#   一元化されていて **どの worktree のセッションからでも main checkout の .gitignore が
#   書き換えられる**（2026-09-01 実測）。worktree ごとにロードされる project スコープでは
#   塞げないため user スコープに置く。登録は ~/.claude/settings.json の PreToolUse / Bash。
#
# 判定ロジック: ~/.claude/hooks/lib/br_doctor_guard.py
#   ⚠️ シェルに埋め込んでいた版は、正規表現に含まれる引用符が `python3 -c '...'` の
#      単一引用符を閉じて **hook 全体が syntax error で壊れた**（実際に発生）。
#      bash は syntax error で exit 2 を返すため、壊れた hook は
#      「全ての Bash 呼び出しをブロックする」状態になる。ロジックは別ファイルに置く。
#
# テスト: ~/.claude/hooks/test_guard_br_doctor_gitignore.sh
#   ⚠️ user スコープなので **CI では回らない**。この hook は実装中に 2 回壊れた実績があるので、
#      触ったら手で `bash ~/.claude/hooks/test_guard_br_doctor_gitignore.sh` を回すこと。

set -uo pipefail

case "${HRG_BR_DOCTOR_GUARD:-true}" in
  false|0|off|no|disable|disabled) exit 0 ;;
esac

command -v python3 >/dev/null 2>&1 || exit 0

input=$(cat)

# 安価な事前フィルタ: `doctor` を含まないコマンドは即通す（大多数がここで抜ける）。
# `br` だけで弾かないのは `bundle exec ...` 等に含まれうるため。
case "$input" in
  *doctor*) : ;;
  *) exit 0 ;;
esac

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
GUARD_PY="${HOOK_DIR}/lib/br_doctor_guard.py"

# 判定ロジックが読めない場合は通す（hook が原因で作業が詰まらないようにする）。
# ⚠️ ただし「読めなかった」ことは黙らせない — 沈黙が失敗形なので stderr に出す。
if [ ! -f "${GUARD_PY}" ]; then
  echo "⚠️ guard_br_doctor_gitignore: ${GUARD_PY} が見つからないため判定をスキップしました" >&2
  exit 0
fi

verdict=$(printf '%s' "${input}" | python3 "${GUARD_PY}" 2>/dev/null) || verdict="ALLOW"

[ -z "${verdict}" ] && verdict="ALLOW"
[ "${verdict}" = "ALLOW" ] && exit 0

FILTER_ID="fm-configs-gitignore-leaking-beads"
CORRECT="br doctor --repair --skip ${FILTER_ID}"

# --skip に正しい id が付いている場合だけ、id が今も実在するかを確認して通す。
# ⚠️ ここを「付いていれば通す」にすると、id が改名された瞬間に黙って無防備になる。
if [ "${verdict}" = "VERIFY_ID" ]; then
  if ! command -v br >/dev/null 2>&1; then
    exit 0  # br が無い環境では判断材料が無いので通す（このコマンドはどうせ失敗する）
  fi
  caps=$(br doctor capabilities --format json 2>/dev/null) || caps=""
  if [ -z "${caps}" ]; then
    exit 0  # capabilities が取れない = 判断できない。ここで止めると作業が詰まる
  fi
  if printf '%s' "${caps}" | grep -q -- "${FILTER_ID}"; then
    exit 0  # id は実在する。想定どおりの実行なので通す
  fi
  cat >&2 <<'GUARD_MSG_RENAMED'
🔴 ブロック: --skip に指定した fixer id が br に存在しません。

  指定: fm-configs-gitignore-leaking-beads

この id は br 側で改名・分割された可能性があります。**--skip は未知の id を黙って無視する**
（typo でもエラーにならず exit 0 で書き込みが走る）ため、このまま実行すると root .gitignore の
`.beads/` の行が消えます。

現在の id を確認してから実行してください:

  br doctor capabilities --format json | grep -o 'fm-configs-[a-z0-9-]*'

id が変わっていた場合は、CLAUDE.md「タスク・進捗管理のルール」/ この hook の FILTER_ID /
.cass/playbook.yaml の該当 bullet を同じ PR で直してください。
GUARD_MSG_RENAMED
  exit 2
fi

case "${verdict}" in
  PARSE_ERROR)
    reason="コマンドを解釈できませんでした（クォートが閉じていない可能性）。安全側に倒して止めます。"
    ;;
  WRONG_SKIP:*)
    reason="--skip は指定されていますが ${FILTER_ID} が含まれていません（指定: ${verdict#WRONG_SKIP:}）。"
    ;;
  *)
    reason="--skip ${FILTER_ID} が付いていません。"
    ;;
esac

cat >&2 <<GUARD_MSG
🔴 ブロック: この \`br doctor --repair\` は root .gitignore から \`.beads/\` の行を消します。

  ${reason}

fixer \`doctor.gitignore_repair\` は既定で有効で、root で \`.beads/\` を ignore していることを
finding \`gitignore.beads_inner\` と見なして**リポジトリ直下の .gitignore を書き換えます**。
このプロジェクトは \`.beads/\` をチーム共有しない方針なので、これは方針の巻き戻しです。

次のいずれかで実行してください:

  # 抑止して修復する（通常はこれ）
  ${CORRECT}

  # 何をするか見るだけ
  br doctor --repair --dry-run

⚠️ 確認するときは \`2>&1\` が必須です。計画は stdout ではなく **stderr** に出るため、
   パイプだけでは常に 0 件になり「守られている」と誤答します:

  ${CORRECT} --dry-run 2>&1 | grep 'would mutate'

⚠️ \`--repair\` は \`--skip\` の有無によらず exit 0 なので、exit code では検出できません。
   実行後は必ず \`git status\` を見てください。

背景と実測は \`cm context "br doctor gitignore"\`（playbook）。
この hook を意図的に外すときは HRG_BR_DOCTOR_GUARD=false（理由を PR に書くこと）。
GUARD_MSG
exit 2
