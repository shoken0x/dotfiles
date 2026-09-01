#!/usr/bin/env python3
"""ツール使用状況のダッシュボード（/tool-usage の中身）。

    report.py                # 直近7日
    report.py month          # 直近30日
    report.py all            # 全期間
    report.py --days 90
    report.py --json         # 機械可読

## 数え方の約束

- **総呼び出し数は events の行数**。1 呼び出しは 1 行
- **カテゴリ件数は合計しても総数にならない**。`git diff | grep foo` は git と grep の
  両方に数えるため（意図的。「どの道具に触ったか」を知りたいので）
- 母数の「セッション」は **ツール呼び出しが 1 回以上あったセッション**
- `露出セッション` は MCP サーバー名が会話に載っていたセッション数。
  wiki（code-analysis-mcp-reality-check.md）の「使えたのに使わなかった母数」と同じ定義
- サブエージェントの呼び出しは `<session>/subagents/*.jsonl` から取り込み、
  親セッションに合算している（`main / sub` 列で内訳が見える）
"""

import argparse
import json
import os
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classify as C
import db as D

SPARK = "·▁▂▃▄▅▆▇█"   # 0 は「·」。空白にすると使わなかった日が軸ごと消えて読めない
W = 92


# --- 全角を数えた桁揃え ---------------------------------------------------

def dw(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(s))


def trunc(s, width):
    s = str(s)
    if dw(s) <= width:
        return s
    out = ""
    for ch in s:
        if dw(out) + dw(ch) > width - 1:
            return out + "…"
        out += ch
    return out


def pad(s, width, align="<"):
    s = str(s)
    fill = max(0, width - dw(s))
    return s + " " * fill if align == "<" else " " * fill + s


def num(n):
    return f"{n:,}"


def pct(a, b, digits=1):
    if not b:
        return "—"
    return f"{a / b * 100:.{digits}f}%"


def bar(frac, width=24):
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def spark(values):
    if not values:
        return ""
    hi = max(values)
    if hi <= 0:
        return SPARK[0] * len(values)
    return "".join(SPARK[min(8, max(1, int(round(v / hi * 8))))] if v else SPARK[0]
                   for v in values)


def h1(title):
    return f"\n■ {title}"


# --- 集計 -----------------------------------------------------------------

def _date_range(start, end):
    import datetime as _dt
    a = _dt.date.fromisoformat(start)
    b = _dt.date.fromisoformat(end)
    out = []
    while a <= b:
        out.append(a.isoformat())
        a += _dt.timedelta(days=1)
    return out


def bucketize(labels, values, max_buckets=60):
    """バケットが多すぎるときは週単位（7日）にまとめる。"""
    if len(values) <= max_buckets:
        return labels, values, "日"
    step = 7
    L, V = [], []
    for i in range(0, len(values), step):
        L.append(labels[i])
        V.append(sum(values[i:i + step]))
    return L, V, "週"


def build(con, days):
    where, params = "", []
    if days:
        start = time.strftime("%Y-%m-%d", time.localtime(time.time() - (days - 1) * 86400))
        where, params = " WHERE day >= ?", [start]
    else:
        start = con.execute("SELECT MIN(day) FROM events").fetchone()[0]
    end = con.execute("SELECT MAX(day) FROM events").fetchone()[0]

    q = lambda sql, *a: con.execute(sql, a).fetchall()
    one = lambda sql, *a: (con.execute(sql, a).fetchone() or [0])[0]

    total = one(f"SELECT COUNT(*) FROM events{where}", *params)
    sub = one(f"SELECT COUNT(*) FROM events{where}{' AND' if where else ' WHERE'} origin='sub'", *params)
    sessions = one(f"SELECT COUNT(DISTINCT session) FROM events{where}", *params)

    cat_join = ("SELECT c.cat, COUNT(*) n, COUNT(DISTINCT e.session) s, "
                "SUM(e.origin='main') m, SUM(e.origin='sub') b "
                "FROM event_cats c JOIN events e ON e.tid=c.tid"
                + (where.replace("day", "e.day") if where else "")
                + " GROUP BY c.cat")
    cats = {r[0]: {"calls": r[1], "sessions": r[2], "main": r[3], "sub": r[4]}
            for r in q(cat_join, *params)}

    exposure = dict(q(
        "SELECT cat, COUNT(*) FROM exposure WHERE session IN "
        f"(SELECT DISTINCT session FROM events{where}) GROUP BY cat", *params))

    # 表示する日付は「データがあった日」ではなく **期間の全日**。
    # 抜けを詰めると「使わなかった日」が消えて推移が読めなくなる。
    all_days = _date_range(start, end)
    counts_by_day = dict(q(f"SELECT day, COUNT(*) FROM events{where} GROUP BY day", *params))
    days_rows = [(dd, counts_by_day.get(dd, 0)) for dd in all_days]

    def series(cat):
        rows = dict(q(
            "SELECT e.day, COUNT(*) FROM event_cats c JOIN events e ON e.tid=c.tid "
            "WHERE c.cat=?" + (" AND e.day >= ?" if where else "") + " GROUP BY e.day",
            cat, *params))
        return [rows.get(dd, 0) for dd in all_days]

    repos = q(f"SELECT COALESCE(repo,'?'), COUNT(*) FROM events{where} "
              "GROUP BY 1 ORDER BY 2 DESC LIMIT 8", *params)
    # 分類外（CLI ルールに当たらなかった）Bash コマンドを全件。追跡漏れの発見に使う。
    heads = q("SELECT e.head, COUNT(*) n, COUNT(DISTINCT e.session) FROM events e "
              "JOIN event_cats c ON c.tid=e.tid "
              "WHERE e.tool='Bash' AND c.cat='builtin:Bash' AND e.head IS NOT NULL"
              + (" AND e.day >= ?" if where else "")
              + " GROUP BY e.head ORDER BY n DESC", *params)

    hw, hp = ("", []) if not days else (" WHERE day >= ?", [start])
    hooks = q(f"SELECT command, atype, COUNT(*) FROM hook_fires{hw} "
              "GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10", *hp)
    advice = q(f"SELECT ts, session, label FROM hook_fires{hw}"
               f"{' AND' if hw else ' WHERE'} command LIKE '%advise_tool_selection%' "
               "AND label <> '' ORDER BY ts", *hp)

    return dict(start=start, end=end, days=days, total=total, sub=sub, sessions=sessions,
                cats=cats, exposure=exposure, day_rows=days_rows, series=series,
                repos=repos, heads=heads, hooks=hooks, advice=advice)


def advice_adoption(con, advice, window_sec=1800):
    """助言が届いたあと、その道具に持ち替えたか（30分以内・同一セッション）。

    ⚠️ 相関でしかない。助言が原因だと断定できないし、助言と無関係に使った分も入る。
    それでも「助言が完全に無視されている」状態は検出できる（ast-grep MCP と
    codegraph-rust で 2 度見逃した形）。
    """
    out = []
    for ts, sess, label in advice:
        target = "cli:ast-grep" if "ast-grep" in label or "引数の形" in label or "grep" in label else None
        if target is None:
            continue
        n = con.execute(
            "SELECT COUNT(*) FROM event_cats c JOIN events e ON e.tid=c.tid "
            "WHERE c.cat=? AND e.session=? AND e.ts BETWEEN ? AND ?",
            (target, sess, ts, ts + window_sec)).fetchone()[0]
        out.append((ts, label, target, n))
    return out


# --- 描画 -----------------------------------------------------------------

def kind_tables(d, focus):
    """種別ごとに **全件** 並べる。上位 N で切らない。

    切ると「呼び出し 0 の道具」が消えるが、このダッシュボードで一番見たいのは
    まさにそこ（入れたのに使っていない道具）なので、省略しない。
    """
    L = []
    cats = d["cats"]
    total = d["total"] or 1
    min_exp = int(os.environ.get("CLAUDE_TOOLSTATS_MIN_EXPOSURE", "5"))

    def rows_for(prefix):
        return sorted(((v["calls"], k) for k, v in cats.items() if k.startswith(prefix)),
                      key=lambda t: (-t[0], t[1]))

    def table(title, rows, name_w=30, show_exposure=False, note=None):
        L.append(h1(f"{title}（{len(rows)} 件）"))
        head = ("  " + pad("道具", name_w) + pad("呼び出し", 10, ">") + pad("main/sub", 12, ">")
                + pad("使ったｾｯｼｮﾝ", 14, ">") + pad("到達率", 8, ">"))
        if show_exposure:
            head += pad("露出", 7, ">") + pad("露出比", 8, ">")
        L.append(head)
        if not rows:
            L.append("  （なし）")
            return
        for n, k in rows:
            c = cats.get(k, {})
            mark = "★" if k in focus else " "
            line = ("  " + pad(mark + trunc(C.display_name(k), name_w - 1), name_w)
                    + pad(num(n), 10, ">")
                    + pad(f"{c.get('main', 0)}/{c.get('sub', 0)}", 12, ">")
                    + pad(f"{c.get('sessions', 0)} / {d['sessions']}", 14, ">")
                    + pad(pct(c.get("sessions", 0), d["sessions"]), 8, ">"))
            if show_exposure:
                exp = d["exposure"].get(k, 0)
                line += pad(num(exp) if exp else "—", 7, ">") + pad(pct(c.get("sessions", 0), exp), 8, ">")
            L.append(line)
        if note:
            L.append("  " + note)

    # MCP は「呼び出しがあったもの」＋「載っていただけのもの」を合わせて全件
    mcp_rows = rows_for("mcp:")
    exposed_only = sorted(((0, k) for k, n in d["exposure"].items()
                           if k not in cats and k.startswith("mcp:") and n >= min_exp),
                          key=lambda t: t[1])
    dropped = sorted(k[4:] for k, n in d["exposure"].items()
                     if k not in cats and k.startswith("mcp:") and n < min_exp)
    note = None
    if dropped:
        note = (f"露出 {min_exp} ｾｯｼｮﾝ未満かつ呼び出し 0 のため除外: "
                + ", ".join(dropped)
                + "（解説文中の文字列を拾ったもの。CLAUDE_TOOLSTATS_MIN_EXPOSURE で調整）")
    table("MCP サーバー", mcp_rows + exposed_only, show_exposure=True, note=note)

    table("CLI（Bash の中身を分解して判定）", rows_for("cli:"))
    table("組み込みツール", rows_for("builtin:"))
    table("サブエージェント委譲先", rows_for("agent:"), name_w=34)
    table("Skill", rows_for("skill:"), name_w=42)

    # 分類外の Bash コマンド（追跡漏れの候補）
    if d["heads"]:
        multi = [(h, n, ss) for h, n, ss in d["heads"] if n >= 2]
        singles = [h for h, n, _ in d["heads"] if n < 2]
        L.append(h1(f"分類外の Bash コマンド（{len(d['heads'])} 種・CLI ルール未登録）"))
        cur = "  "
        for h, n, ss in multi:
            piece = f"{h}·{num(n)}({ss}s)"
            if dw(cur) + dw(piece) + 2 > W:
                L.append(cur); cur = "  "
            cur += piece + "  "
        if cur.strip():
            L.append(cur)
        if singles:
            L.append(f"  ＋1回のみ {len(singles)} 種: " + trunc(", ".join(singles), W - 20))
        L.append("  ここに常用しているものがあれば classify.py の CLI_RULES に足す")

    # 呼び出し量の帯（種別横断・上位のみ。全件は上の表で見る）
    top = sorted(((v["calls"], k) for k, v in cats.items()
                  if not k.startswith(("skill:", "agent:"))), reverse=True)[:10]
    if top:
        L.append(h1("呼び出し量の帯（種別横断・上位10）"))
        hi = top[0][0] or 1
        for n, k in top:
            L.append("  " + pad(trunc(C.display_name(k), 22), 22) + pad(num(n), 9, ">")
                     + "  " + bar(n / hi) + pad(pct(n, total), 8, ">"))
    return L


def session_report(con, sid, focus):
    """1 セッションの判定。道具選定のテストを走らせた直後に見るためのもの。

    ✔/✘ は「使ったか」だけを言う。使わなかった理由（選ばなかった / 使えなかった）は
    区別できないので、対照試行（名指しで同じことをやらせる）と併せて読む。
    """
    if sid in ("latest", "last"):
        row = con.execute("SELECT session FROM events ORDER BY ts DESC, rowid DESC LIMIT 1").fetchone()
        if not row:
            return "イベントがありません"
        sid = row[0]

    meta = con.execute(
        "SELECT MIN(ts), MAX(ts), COUNT(*), COALESCE(SUM(origin='sub'),0) "
        "FROM events WHERE session=?", (sid,)).fetchone()
    if not meta or not meta[2]:
        return f"セッション {sid} のイベントが見つかりません"
    first, last, total, sub = meta
    repo = con.execute("SELECT repo, branch FROM events WHERE session=? AND repo IS NOT NULL "
                       "ORDER BY ts DESC LIMIT 1", (sid,)).fetchone() or ("?", "?")
    counts = dict(con.execute(
        "SELECT c.cat, COUNT(*) FROM event_cats c JOIN events e ON e.tid=c.tid "
        "WHERE e.session=? GROUP BY c.cat", (sid,)).fetchall())
    splits = {k: (m, b) for k, m, b in con.execute(
        "SELECT c.cat, SUM(e.origin='main'), SUM(e.origin='sub') FROM event_cats c "
        "JOIN events e ON e.tid=c.tid WHERE e.session=? GROUP BY c.cat", (sid,)).fetchall()}

    L = []
    L.append("━" * W)
    L.append(f" セッション {sid}")
    L.append(f" {time.strftime('%Y-%m-%d %H:%M', time.localtime(first))} 〜 "
             f"{time.strftime('%H:%M', time.localtime(last))}"
             f"   {repo[0]} ({repo[1]})"
             f"   呼び出し {num(total)}（うちサブエージェント {num(sub)}）")
    L.append("━" * W)

    L.append(h1("注目ツール"))
    for k in focus:
        n = counts.get(k, 0)
        m, b = splits.get(k, (0, 0))
        L.append("  " + ("✔ " if n else "✘ ") + pad(trunc(C.display_name(k), 28), 28)
                 + pad(num(n), 8, ">") + pad(f"{m}/{b}", 10, ">"))

    L.append(h1("競合相手（同じ用途で選ばれた道具）"))
    rivals = []
    for key, rs, desc in C.RIVALS:
        a = counts.get(key, 0)
        b = sum(counts.get(r, 0) for r in rs)
        if a or b:
            rivals.append((desc, a, b))
    if rivals:
        for desc, a, b in rivals:
            L.append("  " + pad(desc, 40) + pad(num(a), 8, ">") + " : "
                     + pad(num(b), 8, "<") + pad(pct(a, a + b), 8, ">"))
    else:
        L.append("  （該当なし）")

    L.append(h1("このセッションで使った道具（全件）"))
    rows = sorted(((v, k) for k, v in counts.items()), reverse=True)
    cur = "  "
    for n, k in rows:
        piece = f"{C.label(k)}·{n}"
        if dw(cur) + dw(piece) + 2 > W:
            L.append(cur); cur = "  "
        cur += piece + "  "
    if cur.strip():
        L.append(cur)

    fires = con.execute(
        "SELECT COUNT(*) FROM hook_fires WHERE session=? AND command LIKE '%advise_tool_selection%' "
        "AND label <> ''", (sid,)).fetchone()[0]
    L.append("")
    L.append(f"  ツール選定助言が届いた回数: {fires}")
    L.append("━" * W)
    return "\n".join(L)


def render(con, d, focus):
    L = []
    label_period = ("全期間" if not d["days"] else
                    f"直近{d['days']}日")
    L.append("━" * W)
    L.append(f" Claude Code ツール使用状況 — {label_period}  ({d['start']} 〜 {d['end']})")
    L.append("━" * W)
    L.append(f" セッション {num(d['sessions'])}   ツール呼び出し {num(d['total'])}"
             f"   うちサブエージェント {num(d['sub'])} ({pct(d['sub'], d['total'])})")

    # 注目ツール
    L.append(h1("注目ツール — 使ったか？"))
    L.append("  " + pad("道具", 26) + pad("呼び出し", 11, ">") + pad("main/sub", 13, ">")
             + pad("使ったｾｯｼｮﾝ", 15, ">") + pad("到達率", 9, ">")
             + pad("露出ｾｯｼｮﾝ", 12, ">") + pad("露出比", 9, ">"))
    L.append("  " + "─" * (W - 4))
    for k in focus:
        c = d["cats"].get(k, {})
        calls = c.get("calls", 0)
        s = c.get("sessions", 0)
        exp = d["exposure"].get(k) if k.startswith("mcp:") else None
        L.append("  " + pad(trunc(C.display_name(k), 26), 26)
                 + pad(num(calls), 11, ">")
                 + pad(f"{c.get('main',0)}/{c.get('sub',0)}", 13, ">")
                 + pad(f"{s} / {d['sessions']}", 15, ">")
                 + pad(pct(s, d["sessions"]), 9, ">")
                 + pad(num(exp) if exp is not None else "—", 12, ">")
                 + pad(pct(s, exp) if exp else "—", 9, ">"))
    L.append("  " + "─" * (W - 4))
    L.append("  到達率 = 使ったセッション / 全セッション。露出比 = 使ったセッション / その MCP が載っていたセッション")

    # 選択比
    L.append(h1("選択比 — どちらを選んだか（優劣の採点ではない。用途で正解は変わる）"))
    for key, rivals, desc in C.RIVALS:
        a = d["cats"].get(key, {}).get("calls", 0)
        b = sum(d["cats"].get(r, {}).get("calls", 0) for r in rivals)
        L.append("  " + pad(desc, 40) + pad(num(a), 9, ">") + " : "
                 + pad(num(b), 9, "<") + pad(pct(a, a + b), 8, ">"))

    # 内訳（種別ごとに全件）
    L.extend(kind_tables(d, focus))

    # 推移
    L.append(h1("推移"))
    raw_labels = [x[0] for x in d["day_rows"]]
    raw_totals = [x[1] for x in d["day_rows"]]
    blabels, totals, unit = bucketize(raw_labels, raw_totals)
    day_labels = [b[5:] for b in blabels]
    if len(totals) <= 10 and totals:
        head = "  " + pad("日付", 8) + pad("合計", 9, ">") + "".join(
            pad(C.label(k), 9, ">") for k in focus)
        L.append(head)
        series = {k: bucketize(raw_labels, d["series"](k))[1] for k in focus}
        for i, dl in enumerate(day_labels):
            L.append("  " + pad(dl, 8) + pad(num(totals[i]), 9, ">")
                     + "".join(pad(num(series[k][i]), 9, ">") for k in focus))
    elif totals:
        L.append("  " + pad("合計", 22) + spark(totals)
                 + f"   max {num(max(totals))}/{unit}")
        for k in focus:
            sv = bucketize(raw_labels, d["series"](k))[1]
            L.append("  " + pad(trunc(C.display_name(k), 22), 22) + spark(sv)
                     + f"   計 {num(sum(sv))}")
        axis = day_labels[0] + " " * max(1, len(totals) - 10) + day_labels[-1]
        L.append("  " + " " * 22 + axis + f"  ({unit}単位)")
    else:
        L.append("  （データなし）")

    # リポジトリ
    L.append(h1("作業ディレクトリ別（上位8）"))
    for r, n in d["repos"]:
        L.append("  " + pad(r, 34) + pad(num(n), 9, ">") + pad(pct(n, d["total"]), 8, ">"))

    # hook
    L.append(h1("hook の発火（出力があったものだけ記録される）"))
    if d["hooks"]:
        for cmd, atype, n in d["hooks"]:
            L.append("  " + pad(num(n), 6, ">") + "  " + pad(atype or "?", 26)
                     + (cmd or "(なし)")[:52])
    else:
        L.append("  （なし）")

    ad = advice_adoption(con, d["advice"])
    if ad:
        adopted = sum(1 for _, _, _, n in ad if n > 0)
        L.append("")
        L.append(f"  ツール選定助言 (advise_tool_selection.sh): 助言が届いた {len(ad)} 回"
                 f" → 30分以内に持ち替え {adopted} 回 ({pct(adopted, len(ad))})")
        L.append("  ⚠️ 相関のみ。助言が原因とは言えないが、完全に無視されている状態は検出できる")
    L.append("")
    L.append("  他の期間: /tool-usage week | /tool-usage month | /tool-usage all | /tool-usage 90d")
    L.append("━" * W)
    return "\n".join(L)


PERIOD_ALIASES = {
    "week": 7, "w": 7, "weekly": 7, "7": 7, "7d": 7, "週": 7, "週次": 7, "今週": 7,
    "month": 30, "m": 30, "monthly": 30, "30": 30, "30d": 30, "月": 30, "月次": 30, "今月": 30,
    "all": None, "a": None, "total": None, "全": None, "全期間": None, "すべて": None,
    "today": 1, "day": 1, "日次": 1, "本日": 1,
}


def parse_period(text):
    """'week' / '月次' / '90d' などを日数に直す。未知なら (None, エラー文)。"""
    t = (text or "week").strip().lower()
    if t in PERIOD_ALIASES:
        return PERIOD_ALIASES[t], None
    if t.endswith("d") and t[:-1].isdigit():
        return int(t[:-1]), None
    if t.isdigit():
        return int(t), None
    return "ERR", (f"期間 '{text}' を解釈できません。"
                   "week / month / all / 90d のいずれかを指定してください。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("period", nargs="?", default="week",
                    help="集計期間: week | month | all | 90d（既定: week）")
    ap.add_argument("--days", type=int, help="日数を直接指定（period を上書き）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-collect", action="store_true", help="取り込みを省略して DB のまま集計")
    ap.add_argument("--session", metavar="ID|latest",
                    help="1 セッションだけ判定する（道具選定テストの直後に使う）")
    args = ap.parse_args()

    if not args.no_collect:
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([sys.executable, os.path.join(here, "collect.py"), "--all", "--quiet"],
                       check=False)

    con0 = D.connect()
    focus0 = ([k.strip() for k in os.environ["CLAUDE_TOOLSTATS_FOCUS"].split(",") if k.strip()]
              if os.environ.get("CLAUDE_TOOLSTATS_FOCUS") else list(C.DEFAULT_FOCUS))
    if args.session:
        print(session_report(con0, args.session, focus0))
        return 0

    if args.days:
        days = args.days
    else:
        days, err = parse_period(args.period)
        if days == "ERR":
            print(err, file=sys.stderr)
            return 2
    con = D.connect()
    d = build(con, days)
    focus = ([k.strip() for k in os.environ["CLAUDE_TOOLSTATS_FOCUS"].split(",") if k.strip()]
             if os.environ.get("CLAUDE_TOOLSTATS_FOCUS") else list(C.DEFAULT_FOCUS))

    if args.json:
        payload = {k: v for k, v in d.items() if k != "series"}
        payload["focus"] = {k: {**d["cats"].get(k, {}), "exposure": d["exposure"].get(k)}
                            for k in focus}
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    print(render(con, d, focus))
    return 0


if __name__ == "__main__":
    sys.exit(main())
