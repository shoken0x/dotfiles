#!/bin/bash
#
# UserPromptSubmit hook: 直前に送信したプロンプトを 1 行にして保存する。
# statusline (~/.claude/statusline-command.sh) はこのファイルを cat するだけ。
#
# ⚠️ ここでは表示幅に合わせて切らない。ターミナル幅は描画時にしか分からず、
#    リサイズでも変わるため、切り詰めは statusline 側の責務。ここは暴走した
#    貼り付けを防ぐ上限 (MAX_CHARS) だけを掛ける。
#
# ⚠️ UserPromptSubmit hook の stdout はモデルのコンテキストに注入されるため、
#    このスクリプトは stdout に何も出さないこと。
#
set -u

MAX_CHARS=200   # 保存の上限。表示桁数ではない
DIR="$HOME/.claude/statusline/last-prompt"

input=$(cat)
[ -z "$input" ] && exit 0

# セッションの識別子は transcript のファイル名に揃える（statusline 側が
# transcript_path の basename で引くため）。無ければ session_id に落とす。
SID=$(printf '%s' "$input" | jq -r '
  (.transcript_path // "" | sub("^.*/"; "") | sub("\\.jsonl$"; ""))
  | if . == "" then "" else . end
' 2>/dev/null)
[ -z "$SID" ] && SID=$(printf '%s' "$input" | jq -r '.session_id // ""' 2>/dev/null)
[ -z "$SID" ] && exit 0

# 改行・タブは潰して 1 行にする。
TEXT=$(printf '%s' "$input" | jq -r --argjson n "$MAX_CHARS" '
  (.prompt // "")
  | gsub("[\\n\\r\\t]+"; " ")
  | gsub("^\\s+|\\s+$"; "")
  | if (length > $n) then (.[0:$n] + "…") else . end
' 2>/dev/null)
[ -z "$TEXT" ] && exit 0

mkdir -p "$DIR" 2>/dev/null || exit 0
printf '%s' "$TEXT" > "$DIR/$SID.txt" 2>/dev/null

# 古いセッションの残骸を掃除する（14 日）。
find "$DIR" -name '*.txt' -mtime +14 -delete 2>/dev/null

exit 0
