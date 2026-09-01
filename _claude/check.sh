#!/bin/bash
#
# Claude Code 設定のリポジトリ管理を検査する。
#
#   1. ~/.claude 側が「このリポジトリを指す symlink」のままか
#      → Claude Code は plugin 追加や permission 承認で settings.json を書き換える。
#        書き換えが symlink の置き換えで行われると **黙って追跡から外れる**ため、
#        ここで検出する（これが唯一の関門）
#   2. コミット対象に秘密情報・社内固有名詞が混ざっていないか
#      → このリポジトリは PUBLIC
#
# 使い方: bash ~/git/dotfiles/_claude/check.sh
#
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DOT="$REPO/_claude"
C="$HOME/.claude"
fail=0

MANAGED=(
  CLAUDE.md settings.json statusline-command.sh
  hooks commands
  toolstats/classify.py toolstats/collect.py toolstats/db.py toolstats/hook.sh
  toolstats/report.py toolstats/selftest.sh toolstats/test_classify.py toolstats/README.md
  skills/diagram-craft skills/supacode-cli
)

echo "== 1. symlink が生きているか =="
for rel in "${MANAGED[@]}"; do
  src="$C/$rel"
  if [ ! -L "$src" ]; then
    if [ -e "$src" ]; then
      echo "  ❌ symlink ではなく実体になっている: ~/.claude/$rel"
      echo "     （Claude Code に置き換えられた可能性。差分を確認して repo 側へ取り込むこと:"
      echo "      diff \"$src\" \"$DOT/$rel\" ）"
    else
      echo "  ❌ 存在しない: ~/.claude/$rel"
    fi
    fail=1
    continue
  fi
  target="$(cd "$(dirname "$src")" && pwd -P)/$(basename "$src")"
  resolved="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$src")"
  case "$resolved" in
    "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$DOT")"/*) : ;;
    *) echo "  ❌ このリポジトリ外を指している: ~/.claude/$rel -> $resolved"; fail=1 ;;
  esac
done
[ "$fail" = 0 ] && echo "  ✅ ${#MANAGED[@]} 件すべて repo を指す symlink"

echo
echo "== 2. 秘密情報・社内固有名詞の混入 =="
# ⚠️ zsh で実行されても壊れないよう bash 固定 + 配列で渡す（引用符なし変数展開は
#    zsh で単語分割されず、grep が対象を1つも読まずに 0 件を返す）
# ⚠️ check.sh 自身は除外する。検査パターンとして社内固有名詞を literal で持つため、
#    含めると必ず自分自身にヒットして常に落ちる（実測）。
FILES=$(find "$DOT" -type f ! -name '*.pyc' ! -name '*.bak*' ! -name 'check.sh' 2>/dev/null)
n=$(printf '%s\n' "$FILES" | grep -c .)
echo "  走査対象: $n ファイル"
[ "$n" -eq 0 ] && { echo "  ❌ 走査対象が 0 件（検査が無意味）"; exit 1; }

hit=$(printf '%s\n' "$FILES" | xargs grep -lIoE \
  '(sk-ant-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' 2>/dev/null)
if [ -n "$hit" ]; then echo "  ❌ 秘密値らしき文字列: $hit"; fail=1; else echo "  ✅ 秘密値なし"; fi

hit=$(printf '%s\n' "$FILES" | xargs grep -lIiE 'kitchhike|hrg-reservation|hoikuen-ryugaku|preschool-exchange|@[a-z0-9.-]+\.co\.jp' 2>/dev/null)
if [ -n "$hit" ]; then echo "  ❌ 社内固有名詞: $hit"; fail=1; else echo "  ✅ 社内固有名詞なし"; fi

echo
[ "$fail" = 0 ] && echo "✅ すべて問題なし" || echo "❌ 上記を修正すること"
exit "$fail"
