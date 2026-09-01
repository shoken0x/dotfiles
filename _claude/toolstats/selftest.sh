#!/bin/bash
#
# toolstats の全経路スモークテスト。
#
# この仕組みの失敗形は **沈黙**（hook は exit 0 のまま集計が走らない・
# ステータスラインは 3 行のまま）なので、経路ごとに「動いた証拠」を突き合わせる。
set -uo pipefail

DIR="$HOME/.claude/toolstats"
PASS=0
FAIL=0

ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
ng()   { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
check(){ if [ "$1" = "0" ]; then ok "$2"; else ng "$2 ${3:-}"; fi }

echo "=== 1. 分類ロジックの回帰テスト ==="
if python3 "$DIR/test_classify.py" >/dev/null 2>&1; then ok "test_classify.py"; else
  ng "test_classify.py"; python3 "$DIR/test_classify.py" 2>&1 | sed 's/^/      /'; fi

echo "=== 2. 取り込み（増分） ==="
python3 "$DIR/collect.py" --all --quiet >/dev/null 2>&1
check $? "collect.py --all"
N=$(python3 -c "
import sys; sys.path.insert(0,'$DIR'); import db
print(db.connect().execute('select count(*) from events').fetchone()[0])" 2>/dev/null || echo 0)
if [ "${N:-0}" -gt 0 ]; then ok "events が $N 件ある"; else ng "events が空（取り込みが動いていない）"; fi

echo "=== 3. サブエージェントを取り込めているか ==="
SUBN=$(python3 -c "
import sys; sys.path.insert(0,'$DIR'); import db
print(db.connect().execute(\"select count(*) from events where origin='sub'\").fetchone()[0])" 2>/dev/null || echo 0)
if [ "${SUBN:-0}" -gt 0 ]; then ok "サブエージェント由来 $SUBN 件"; else
  ng "サブエージェント由来 0 件（<session>/subagents/*.jsonl を読めていない可能性）"; fi

echo "=== 4. hook（payload 経路・detach が本当に走るか） ==="
# 直近に更新された transcript を使う
TP=$(ls -t "$HOME"/.claude/projects/*/*.jsonl 2>/dev/null | head -1)
if [ -z "$TP" ]; then ng "transcript が見つからない"; else
  SID=$(basename "$TP" .jsonl)
  rm -f "$DIR/state/$SID.line" "$DIR/state/$SID.last"
  printf '{"session_id":"%s","transcript_path":"%s"}' "$SID" "$TP" | bash "$DIR/hook.sh"
  check $? "hook.sh が exit 0 で返る"
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    [ -f "$DIR/state/$SID.line" ] && break
    python3 -c "import time;time.sleep(0.2)"
  done
  if [ -f "$DIR/state/$SID.line" ]; then ok "state/<session>.line が生成された"; else
    ng "state が生成されない（detach が死んでいる。macOS に setsid が無い件を確認）"; fi
  if [ -f "$DIR/state/$SID.last" ]; then ok "state/<session>.last が生成された"; else
    ng "state/<session>.last が無い"; fi
fi

echo "=== 5. hook（--transcript 経路・ステータスラインが使う） ==="
if [ -n "${TP:-}" ]; then
  bash "$DIR/hook.sh" --transcript "$TP"
  check $? "hook.sh --transcript が exit 0 で返る"
fi

echo "=== 6. hook が stdout を汚さないか（汚すとモデルの文脈に混ざる） ==="
OUT=$(printf '{"transcript_path":"%s"}' "${TP:-/nonexistent}" | bash "$DIR/hook.sh" 2>/dev/null)
if [ -z "$OUT" ]; then ok "stdout は空"; else ng "stdout に出力がある: $OUT"; fi

echo "=== 7. hook の同期コスト ==="
MS=$(python3 - <<PY
import subprocess, time, os
p = os.path.expanduser("$DIR/hook.sh")
tp = "${TP:-}"
ts = []
for _ in range(7):
    t = time.time()
    subprocess.run(["bash", p, "--transcript", tp], capture_output=True)
    ts.append((time.time()-t)*1000)
ts.sort(); print(int(ts[len(ts)//2]))
PY
)
if [ "${MS:-999}" -lt 120 ]; then ok "中央値 ${MS}ms（<120ms）"; else ng "中央値 ${MS}ms は遅すぎる"; fi

echo "=== 8. ダッシュボード（3期間 + JSON） ==="
for P in week month all; do
  if python3 "$DIR/report.py" "$P" --no-collect >/dev/null 2>&1; then ok "report.py $P"; else ng "report.py $P"; fi
done
if python3 "$DIR/report.py" week --no-collect --json 2>/dev/null | python3 -c "import json,sys;json.load(sys.stdin)" 2>/dev/null; then
  ok "report.py --json が妥当な JSON"; else ng "report.py --json が壊れている"; fi
if python3 "$DIR/report.py" bogus --no-collect >/dev/null 2>&1; then
  ng "不正な期間を受け入れてしまう"; else ok "不正な期間は非 0 で落ちる"; fi

echo "=== 9. ステータスラインが 4 行になるか ==="
SL="$HOME/.claude/statusline-command.sh"
if [ -f "$SL" ] && [ -n "${TP:-}" ]; then
  NLINES=$(printf '{"model":{"display_name":"T"},"context_window":{"context_window_size":200000,"used_percentage":1},"workspace":{"current_dir":"%s"},"transcript_path":"%s"}' "$PWD" "$TP" \
    | bash "$SL" 2>/dev/null | wc -l | tr -d ' ')
  # 最終行に改行が無いので wc -l は 3 を返す（= 4 行出ている）
  if [ "${NLINES:-0}" -ge 3 ]; then ok "ツール使用行が出力されている（wc -l = ${NLINES}）"; else
    ng "ツール使用行が出ていない（wc -l = ${NLINES}）"; fi
  if printf '{"model":{"display_name":"T"},"context_window":{"context_window_size":200000,"used_percentage":1},"workspace":{"current_dir":"%s"},"transcript_path":"%s"}' "$PWD" "$TP" \
      | bash "$SL" 2>/dev/null | tail -1 | grep -q '🧰'; then
    ok "最終行が 🧰 で始まるツール使用行"; else ng "最終行がツール使用行になっていない"; fi
fi

echo "=== 10. hook が settings.json に登録されているか ==="
if python3 -c "
import json,os
d=json.load(open(os.path.expanduser('~/.claude/settings.json')))
cmd='bash ~/.claude/toolstats/hook.sh'
ev=('PostToolUse','Stop','SessionStart')
import sys
sys.exit(0 if all(any(h.get('command')==cmd for g in d.get('hooks',{}).get(e,[]) for h in g.get('hooks',[])) for e in ev) else 1)"; then
  ok "PostToolUse / Stop / SessionStart に登録済み"; else ng "settings.json への登録が欠けている"; fi

echo
printf 'PASS %d / FAIL %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
