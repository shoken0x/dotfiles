#!/bin/bash
#
# toolstats の取り込みトリガ（PostToolUse / Stop / SessionStart から呼ぶ）
#
# ## 設計の制約
#
# PostToolUse は**全ツール呼び出しで走る**ので、同期処理をほぼゼロにする必要がある。
#   - stdin（payload。tool_response を含み数百KB になりうる）は **ファイルに落とすだけ**。
#     パイプで子に渡すとバッファ 64KB を超えた時点で hook がブロックする
#   - 集計本体は切り離す。hook は待たない
#   - **常に exit 0・stdout は空**。喋るとモデルの文脈を汚し、
#     終了コード 2 を返すとツール呼び出しをブロックしてしまう
#
# ## detach に setsid を使わない理由
#
# 🔴 **macOS の base には `setsid` コマンドが無い**（`setsid not found`）。
# 最初の実装で `setsid nohup ...` と書いたところ、hook は exit 0 のまま
# 集計だけが一切走らないという**完全な silent failure** になった。
# 代わりに perl の POSIX::setsid を使う（macOS に標準で入っている）。
# 同じ結論はプロジェクト側の .claude/hooks/lib/detach.sh にも書かれている。
#
# ⚠️ detach.sh のような handshake（子が setsid するまで親が待つ）は**ここでは省く**。
# PostToolUse は毎ツール呼び出しで走るため 50ms の待ちが積み上がるうえ、
# 取り込みは冪等（tid が主キー・オフセットは成功時のみコミット）なので
# 子が PG kill で死んでも次の呼び出しが取り戻す。落としても壊れない処理には保険が不要。
#
# 無効化: export CLAUDE_TOOLSTATS_DISABLE=1
set -uo pipefail

case "${CLAUDE_TOOLSTATS_DISABLE:-}" in
  1|true|yes|on) exit 0 ;;
esac

DIR="$HOME/.claude/toolstats"
[ -f "$DIR/collect.py" ] || exit 0
PY_BIN="$(command -v python3 2>/dev/null)" || exit 0
[ -n "$PY_BIN" ] || exit 0

# --transcript <path> … stdin の payload を使わない呼び出し口（ステータスラインから使う）。
# mktemp / cat を省けるので同期コストが約半分になる。
DIRECT_TRANSCRIPT=""
if [ "${1:-}" = "--transcript" ] && [ -n "${2:-}" ]; then
  DIRECT_TRANSCRIPT="$2"
fi

detach() {
  if command -v perl >/dev/null 2>&1; then
    # shellcheck disable=SC2016
    nohup perl -e 'use POSIX qw(setsid); setsid(); exec @ARGV or exit 127;' \
      -- "$@" >/dev/null 2>&1 &
  else
    nohup "$@" >/dev/null 2>&1 &
  fi
}

if [ -n "$DIRECT_TRANSCRIPT" ]; then
  detach "$PY_BIN" "$DIR/collect.py" --session "$DIRECT_TRANSCRIPT" --quiet
  exit 0
fi

TMP_BASE="${TMPDIR:-/tmp}"
TMP="$(mktemp "${TMP_BASE%/}/toolstats-payload.XXXXXX" 2>/dev/null)" || exit 0
cat > "$TMP" 2>/dev/null || true

detach "$PY_BIN" "$DIR/collect.py" --hook-payload "$TMP"

# collect.py が消し忘れた payload の掃除。
# ⚠️ find は TMPDIR 全体を走るので毎回やると hook の同期コストが倍になる（実測 26ms→52ms）。
# 取りこぼしは稀なので 1/64 の確率でだけ掃除する。
if [ $(( RANDOM % 64 )) -eq 0 ]; then
  find "${TMP_BASE%/}" -maxdepth 1 -name 'toolstats-payload.*' -mtime +1 -delete 2>/dev/null || true
fi

exit 0
