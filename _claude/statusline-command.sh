#!/bin/bash
input=$(cat)
NOW=$(date +%s)

# --- ANSIカラー ---
CYAN='\033[36m' YELLOW='\033[33m' RED='\033[31m'
GREEN='\033[32m' MAGENTA='\033[35m' DIM='\033[2m' RESET='\033[0m'

# --- ユーティリティ関数 ---

color_for_pct() {
  if [ "$1" -ge 80 ] 2>/dev/null; then printf '%b' "$RED"
  elif [ "$1" -ge 50 ] 2>/dev/null; then printf '%b' "$YELLOW"
  else printf '%b' "$GREEN"; fi
}

progress_bar() {
  local f=$(( ($1 + 5) / 10 ))
  [ "$f" -gt 10 ] && f=10; [ "$f" -lt 0 ] && f=0
  local bar="▰▰▰▰▰▰▰▰▰▰"
  local empty="▱▱▱▱▱▱▱▱▱▱"
  printf '%s%s' "${bar:0:$f}" "${empty:0:$((10-f))}"
}

bar_line() {
  local label="$1" pct="$2" reset_str="${3:-}"
  if [ -n "$pct" ]; then
    printf '%b%s %s %3s%%%b%s' "$(color_for_pct "$pct")" "$label" "$(progress_bar "$pct")" "$pct" "$RESET" "$reset_str"
  else
    printf '%b%s ▱▱▱▱▱▱▱▱▱▱  --%% %b' "$DIM" "$label" "$RESET"
  fi
}

# 表示幅（半角=1 / 全角=2 の近似）で切り詰める。溢れたら末尾を … にする。
# ⚠️ サブプロセスを起こさない: これは毎描画で走る。
truncate_to_cols() {
  local s="$1" max="$2"
  # 🔴 n=${#s} を上の local 文に混ぜてはいけない: bash 3.2 は同一 local 文の中で
  #    直前に代入したローカル変数を見ず、n=0 になってループが回らない（実測）。
  local n=${#s} i c cw w=0 out=""
  [ "$max" -lt 4 ] && return
  for (( i=0; i<n; i++ )); do
    case "${s:i:1}" in [[:ascii:]]) w=$(( w + 1 )) ;; *) w=$(( w + 2 )) ;; esac
  done
  if [ "$w" -le "$max" ]; then printf '%s' "$s"; return; fi
  w=0
  for (( i=0; i<n; i++ )); do
    c="${s:i:1}"
    case "$c" in [[:ascii:]]) cw=1 ;; *) cw=2 ;; esac
    [ $(( w + cw )) -gt $(( max - 1 )) ] && break
    out="$out$c"; w=$(( w + cw ))
  done
  printf '%s…' "$out"
}

format_reset() {
  local epoch="$1"
  [ -z "$epoch" ] || [ "$epoch" = "0" ] || [ "$epoch" = "null" ] && return
  local rem=$(( epoch - NOW ))
  [ "$rem" -le 0 ] && return
  local d=$(( rem / 86400 )) h=$(( rem % 86400 / 3600 )) m=$(( rem % 3600 / 60 ))
  if [ "$d" -gt 0 ]; then   printf ' reset in %dd %2dh %2dm' "$d" "$h" "$m"
  elif [ "$h" -gt 0 ]; then printf ' reset in    %2dh %2dm' "$h" "$m"
  else                       printf ' reset in        %2dm' "$m"; fi
}

# --- stdin JSON パース ---
eval "$(echo "$input" | jq -r '
  "MODEL=" + (.model.display_name // "Unknown" | @sh),
  "EFFORT=" + (.effort.level // "" | @sh),
  "CTX_SIZE=" + (.context_window.context_window_size // 200000 | tostring),
  "CTX_USED_PCT=" + (.context_window.used_percentage // 0 | tostring),
  "CTX_INPUT=" + ((.context_window.current_usage.input_tokens // 0) | tostring),
  "CTX_CACHE_CREATE=" + ((.context_window.current_usage.cache_creation_input_tokens // 0) | tostring),
  "CTX_CACHE_READ=" + ((.context_window.current_usage.cache_read_input_tokens // 0) | tostring),
  "CTX_HAS_USAGE=" + (if .context_window.current_usage then "1" else "0" end),
  "CWD=" + (.workspace.current_dir // "." | @sh),
  "LINES_ADD=" + (.cost.total_lines_added // 0 | tostring),
  "LINES_DEL=" + (.cost.total_lines_removed // 0 | tostring),
  "FIVE_PCT=" + (.rate_limits.five_hour.used_percentage // empty | floor | tostring),
  "FIVE_RESET_EPOCH=" + (.rate_limits.five_hour.resets_at // 0 | tostring),
  "SEVEN_PCT=" + (.rate_limits.seven_day.used_percentage // empty | floor | tostring),
  "SEVEN_RESET_EPOCH=" + (.rate_limits.seven_day.resets_at // 0 | tostring),
  "TRANSCRIPT=" + (.transcript_path // "" | @sh)
' 2>/dev/null)"

if [ "$CTX_HAS_USAGE" = "1" ]; then
  CTX_PCT=$(( (CTX_INPUT + CTX_CACHE_CREATE + CTX_CACHE_READ) * 100 / CTX_SIZE ))
else
  CTX_PCT=${CTX_USED_PCT%%.*}
fi

# --- Gitブランチ & Worktree ---
GIT_BRANCH=""
if git -C "$CWD" rev-parse --git-dir > /dev/null 2>&1; then
  BRANCH=$(git -C "$CWD" --no-optional-locks branch --show-current 2>/dev/null)
  WORKTREE_NAME=$(basename "$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null)")
  if [ -n "$BRANCH" ]; then
    GIT_BRANCH=" | ${MAGENTA}${BRANCH}${RESET} ${DIM}(${WORKTREE_NAME})${RESET}"
  fi
fi

# --- セッション経過時間 ---
ELAPSED_STR=""
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  START_TS=$(stat -f "%B" "$TRANSCRIPT" 2>/dev/null || stat -c "%W" "$TRANSCRIPT" 2>/dev/null)
  if [ -n "$START_TS" ] && [ "$START_TS" != "0" ]; then
    ELAPSED=$(( NOW - START_TS ))
    MINUTES=$(( ELAPSED / 60 ))
    SECONDS=$(( ELAPSED % 60 ))
    ELAPSED_STR=" | $(printf '%dm %02ds' "$MINUTES" "$SECONDS")"
  fi
fi

# --- Effort レベル ---
EFFORT_STR=""
if [ -n "$EFFORT" ]; then
  case "$EFFORT" in
    max|xhigh) EFFORT_COLOR="$RED" ;;
    high)      EFFORT_COLOR="$YELLOW" ;;
    *)         EFFORT_COLOR="$GREEN" ;;
  esac
  EFFORT_STR=" | ${EFFORT_COLOR}⚡${EFFORT}${RESET}"
fi

# --- レートリミット ---
FIVE_RESET=$(format_reset "$FIVE_RESET_EPOCH")
SEVEN_RESET=$(format_reset "$SEVEN_RESET_EPOCH")

# --- ツール使用状況（toolstats） ---
#
# 集計は ~/.claude/toolstats/collect.py が **PostToolUse hook で事前に済ませ**、
# 1 行に整形して state/<session>.line へ書いてある。ここは cat するだけ。
# ステータスラインは毎描画で走るので、ここで jq や python を起動してはいけない。
#
# `.last` は「直近に使った道具」の epoch とラベル。経過秒だけは描画時に出す（=リアルタイム表示）。
TOOLS_LINE=""
if [ -n "$TRANSCRIPT" ]; then
  TS_SID=$(basename "$TRANSCRIPT" .jsonl)
  TS_DIR="$HOME/.claude/toolstats/state"
  TS_LINE_FILE="$TS_DIR/$TS_SID.line"

  # transcript が state より新しければ取り込みを促す。
  # ⚠️ 3秒のクールダウンを入れる: ストリーミング中は transcript が常に新しく、
  #    毎描画で python を起動すると描画そのものが重くなる。
  TS_KICK=0
  if [ ! -f "$TS_LINE_FILE" ]; then
    TS_KICK=1
  elif [ "$TRANSCRIPT" -nt "$TS_LINE_FILE" ]; then
    TS_LF_M=$(stat -f %m "$TS_LINE_FILE" 2>/dev/null || echo 0)
    [ $(( NOW - TS_LF_M )) -ge 3 ] && TS_KICK=1
  fi
  if [ "$TS_KICK" = "1" ] && [ -x "$HOME/.claude/toolstats/hook.sh" ]; then
    bash "$HOME/.claude/toolstats/hook.sh" --transcript "$TRANSCRIPT" >/dev/null 2>&1
  fi

  if [ -f "$TS_LINE_FILE" ]; then
    TOOLS_LINE=$(cat "$TS_LINE_FILE" 2>/dev/null)
    if [ -f "$TS_DIR/$TS_SID.last" ]; then
      IFS=$'\t' read -r LAST_TS LAST_TOOL < "$TS_DIR/$TS_SID.last" 2>/dev/null || true
      if [ -n "${LAST_TS:-}" ] && [ -n "${LAST_TOOL:-}" ]; then
        AGE=$(( NOW - LAST_TS ))
        [ "$AGE" -lt 0 ] && AGE=0
        if   [ "$AGE" -lt 60 ];   then AGE_STR="${AGE}s"
        elif [ "$AGE" -lt 3600 ]; then AGE_STR="$(( AGE / 60 ))m"
        else                           AGE_STR="$(( AGE / 3600 ))h"; fi
        TOOLS_LINE="${TOOLS_LINE} ${DIM}┃${RESET} ${YELLOW}◂ ${LAST_TOOL}${RESET} ${DIM}${AGE_STR}${RESET}"
      fi
    fi
  fi
fi

# --- 直前のプロンプト ---
#
# 保存は ~/.claude/hooks/save_last_prompt.sh が **UserPromptSubmit hook で済ませ**、
# 1 行にして last-prompt/<session>.txt へ書いてある。ここは cat して幅で切るだけ。
#
# 表示桁数はターミナル幅に連動させる。幅は stdin の JSON には入っていないので
# 環境変数 COLUMNS を使う（Claude Code が渡してくる。tput cols も同じ値を返すが
# stdout/stderr が tty ではないため tput は COLUMNS を読んでいるだけ = 起こすだけ無駄）。
LAST_PROMPT=""
if [ -n "$TRANSCRIPT" ]; then
  LP_SID="${TRANSCRIPT##*/}"
  LP_FILE="$HOME/.claude/statusline/last-prompt/${LP_SID%.jsonl}.txt"
  if [ -f "$LP_FILE" ]; then
    LAST_PROMPT=$(cat "$LP_FILE" 2>/dev/null)

    # 5h 行のうちプロンプト以外が占める桁数:
    #   bar_line = ラベル2 + 空白1 + バー10 + 空白1 + 率3 + %1 = 18（率が無い場合は 19）
    #   " |" = 2 / FIVE_RESET は ASCII なので ${#FIVE_RESET} / 区切り " | " = 3
    if [ -n "$FIVE_PCT" ]; then LP_USED=18; else LP_USED=19; fi
    LP_USED=$(( LP_USED + 2 + ${#FIVE_RESET} + 3 ))
    LP_COLS=$(( ${COLUMNS:-100} - LP_USED - 1 ))

    # 狭すぎるときは無理に出さない（他の情報を潰してまで見せる価値が無い）
    if [ "$LP_COLS" -ge 8 ]; then
      LAST_PROMPT=$(truncate_to_cols "$LAST_PROMPT" "$LP_COLS")
    else
      LAST_PROMPT=""
    fi
  fi
fi

# --- 出力 ---
LINE_STATS=""
if [ "$LINES_ADD" -gt 0 ] 2>/dev/null || [ "$LINES_DEL" -gt 0 ] 2>/dev/null; then
  LINE_STATS=" | ${GREEN}+${LINES_ADD}${RESET}/${RED}-${LINES_DEL}${RESET}"
fi

printf '%b\n' "$(bar_line "cx" "$CTX_PCT") | ${CYAN}${MODEL}${RESET}${EFFORT_STR}${GIT_BRANCH}${LINE_STATS}${ELAPSED_STR}"
printf '%b' "$(bar_line "5h" "$FIVE_PCT") |$FIVE_RESET"
# ⚠️ プロンプト本文はユーザー入力なので %b に通さない（\n などが展開されて行が崩れる）
[ -n "$LAST_PROMPT" ] && printf ' | %s' "$LAST_PROMPT"
printf '\n'
printf '%b'   "$(bar_line "7d" "$SEVEN_PCT") |$SEVEN_RESET"
[ -n "$TOOLS_LINE" ] && printf '\n%b' "$TOOLS_LINE"
