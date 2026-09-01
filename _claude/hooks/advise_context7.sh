#!/bin/bash
#
# Claude Code PreToolUse hook（user スコープ・全リポジトリで発火）:
# ライブラリ公式ドキュメントへの WebFetch / WebSearch に「先に Context7 を引け」と助言する。
# **非ブロッキング**（終了コードは常に 0。2 を返すとツール呼び出しをブロックしてしまう）。
#
# 判定ロジックは lib/context7_advice.py にある。シェルに埋め込むと `2>/dev/null` の裏で
# SyntaxError が「助言なし」と区別できなくなるため、独立ファイルに置いて
# test_advise_context7.sh で「発火するはずの入力で必ず発火すること」を検証する。
#
# 無効化: export CLAUDE_CONTEXT7_ADVICE=false

set -uo pipefail

case "${CLAUDE_CONTEXT7_ADVICE:-true}" in
  false|0|off|no|disable|disabled) exit 0 ;;
esac

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
ADVISOR="${HOOK_DIR}/lib/context7_advice.py"

[ -f "${ADVISOR}" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# python 側が異常終了しても stdout には何も出ていない（助言は最後に一括で書く）ので、
# JSON チャンネルを壊さずに黙って通せる。ブロックは絶対にしない
python3 "${ADVISOR}" || true

exit 0
