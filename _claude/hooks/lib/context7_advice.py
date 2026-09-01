#!/usr/bin/env python3
"""user スコープ PreToolUse hook の助言ロジック（advise_context7.sh から呼ばれる）。

`WebFetch` / `WebSearch` が **ライブラリ／フレームワークの公式ドキュメント** を指したときだけ、
「先に Context7 を引け」と助言する。stdin にツール入力 JSON を受け取り、助言があれば
stdout に hookSpecificOutput の JSON を1つ出す。助言が無ければ**何も出さない**。

## なぜ user スコープなのか

判定材料は「公式ドキュメントのホスト名」だけで、**リポジトリに依存しない**。
一方で Context7 が登録されているのは 45 リポジトリ中 4 つだけ（2026-08-27 実測）だった。
置き場所として user スコープが正しい。

## なぜ hook なのか（露出だけでは呼ばれない）

ある業務リポジトリでの実測（2026-08-26）:
  - Context7 MCP は **122 セッションで露出して実呼び出し 0 回**
  - 同期間に WebFetch 159 回 / WebSearch 51 回 = ドキュメントを読む行為自体は 200 回以上あった
  - `CLAUDE.md` に「Context7 を使うこと」と1行書いてあった状態での 0 回である
道具が無かったのではなく**別の道具に流れていた**。同型の失敗が ast-grep MCP（露出したまま
実呼び出し 0 回で撤去）と codegraph-rust でも起きている。効いたのは常に hook だった。

## 出力契約（code.claude.com/docs/en/hooks.md・2026-08-25 時点）

  - 終了コードは常に 0。**2 を返すとツール呼び出しをブロックする**ので絶対に返さない
  - **モデルに渡るのは `additionalContext` だけ**（PreToolUse でも渡ることは確認済み）
  - `systemMessage` は**ユーザー向け**。この hook の失敗形は「沈黙」なので、生きていることを
    人間が見て取れる唯一の手段として出す
  - **permissionDecision は出さない**。"defer" を出すと `additionalContext` が無視される

## 黙るべき2つのケース

  1. 対象が公式ドキュメントでない（ブログ・記事・GitHub の issue / PR・SaaS の運用ドキュメント）。
     **Context7 が持っていない対象に助言すると空振りし、助言全体が無視されるようになる**
  2. **プロジェクト側の hook が既に同じ助言を持っている**
     （プロジェクトの `.claude/hooks/` に同種の助言がある場合）。二重に出すと読み飛ばされる

## この hook が保証しないこと

⚠️ 保証するのは「助言が届くこと」までで、「助言に従うこと」は保証しない。
**採用されていない状態は、正常に動いている状態と見た目が同じ**である。
したがって導入して終わりにせず、**2026-09-30 に採用率を測る**:
    python3 ~/.claude/toolstats/report.py month
の「ライブラリ調査: context7 vs Web」の選択比を見る（導入時点 = 25.0%）。
上がっていなければ文面か発火条件を直し、それでも動かなければ撤去する。

手で動かして確認する場合:
  echo '{"tool_name":"WebFetch","tool_input":{"url":"https://react.dev/reference/react/useEffect"}}' \
    | bash ~/.claude/hooks/advise_context7.sh
"""

import json
import os
import re
import sys
from urllib.parse import urlsplit

# Context7 を勧める対象 = ライブラリ／フレームワークの**公式ドキュメント**。
# (ホスト末尾, パスの接頭辞（None ならホスト全体が対象）) で持つ。
#
# ⚠️ ここに SaaS の運用ドキュメント（Heroku Dev Center・課金・ダッシュボードの使い方）や
#    ブログを足さないこと。Context7 が持っていない対象に助言すると空振りする。
# ⚠️ 足すときは `resolve-library-id` で**実際に Context7 にあることを確認してから**足す。
#    developers.cloudflare.com/workers と orm.drizzle.team は 2026-08-27 に確認済み。
DOC_SOURCES = (
    # Ruby / Rails
    ("guides.rubyonrails.org", None),
    ("api.rubyonrails.org", None),
    ("edgeguides.rubyonrails.org", None),
    ("edgeapi.rubyonrails.org", None),
    ("rubyonrails.org", "/docs"),
    ("rubydoc.info", None),
    ("ruby-doc.org", None),
    ("docs.ruby-lang.org", None),
    ("rspec.info", None),
    ("sidekiq.org", None),
    # JS / TS フレームワーク
    ("react.dev", None),
    ("reactjs.org", None),
    ("reactrouter.com", None),
    ("reactnative.dev", None),
    ("docs.expo.dev", None),
    ("hono.dev", None),
    ("nextjs.org", "/docs"),
    # ビルド・テスト
    ("vite.dev", None),
    ("vitejs.dev", None),
    ("vitest.dev", None),
    ("jestjs.io", None),
    ("playwright.dev", None),
    ("esbuild.github.io", None),
    ("tailwindcss.com", None),
    # データ・インフラ系ライブラリ
    ("orm.drizzle.team", None),
    ("supabase.com", "/docs"),
    ("zod.dev", None),
    ("redis.io", "/docs"),
    ("postgresql.org", "/docs"),
    ("docs.stripe.com", None),
    ("stripe.com", "/docs"),
    ("docs.sentry.io", None),
    ("modelcontextprotocol.io", None),
    # ランタイム
    ("nodejs.org", "/api"),
    # ⚠️ バージョン固定 URL は `/docs/latest-v20.x/api/...` の形なので `/api` では拾えない
    ("nodejs.org", "/docs"),
    ("bun.sh", "/docs"),
    ("bun.com", "/docs"),
    ("docs.npmjs.com", None),
    # ⚠️ developers.cloudflare.com はサービス運用ドキュメントも同居しているので
    #    Workers 配下だけに限定する
    ("developers.cloudflare.com", "/workers"),
)

# GitHub は wiki と README / docs だけを「ドキュメント」と見なす。
# リポジトリ全体を対象にすると issue / PR / コード閲覧で誤爆する
GITHUB_DOC_PATH_RE = re.compile(
    r"^/[^/]+/[^/]+/(?:wiki|blob/[^/]+/(?:README|docs?/))", re.IGNORECASE
)

LABEL = "Context7 を先に引く"


def _doc_source(url):
    """URL がライブラリ公式ドキュメントを指していれば、その表示名を返す（違えば None）。"""
    url = str(url or "").strip()
    if not url:
        return None
    try:
        parts = urlsplit(url if "//" in url else "https://" + url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    if not host:
        return None
    if host == "github.com" or host.endswith(".github.com"):
        return "GitHub の wiki / README" if GITHUB_DOC_PATH_RE.match(path) else None
    for suffix, prefix in DOC_SOURCES:
        if host == suffix or host.endswith("." + suffix):
            if prefix is None or path.startswith(prefix):
                return host
    return None


def project_hook_covers_context7(root=None):
    """プロジェクト側の hook が既に同じ助言を持っているか。

    持っているなら user 側は黙る（二重の助言は読み飛ばされる）。
    判定は2条件の AND —
      1. `.claude/hooks/lib/tool_selection_advice.py` に Context7 判定がある
      2. その hook が WebFetch / WebSearch で**登録されている**
    2 を見ないと、ファイルはあるが matcher に載っていないリポジトリで黙ってしまう。

    ⚠️ 誤判定の代償は非対称である。黙る方向に誤れば、プロジェクト hook が助言する
    リポジトリで助言が1つ減るだけ。発火する方向に誤れば助言が2つ出る。どちらも壊れない。
    """
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    advisor = os.path.join(root, ".claude", "hooks", "lib", "tool_selection_advice.py")
    try:
        with open(advisor, encoding="utf-8") as fh:
            if "context7" not in fh.read().lower():
                return False
    except OSError:
        return False

    for name in ("settings.json", "settings.local.json"):
        path = os.path.join(root, ".claude", name)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if "advise_tool_selection" in text and ("WebFetch" in text or "WebSearch" in text):
            return True
    return False


def _body(name):
    return (
        "**ライブラリの公式ドキュメント（" + name + "）を直接取りに行こうとしています。**\n"
        "  ライブラリ / フレームワーク / SDK の仕様確認は、`WebFetch` / `WebSearch` より先に "
        "**Context7** を引くのが規約です（学習データより新しいバージョンが出ていると、"
        "記憶で書いた API は黙って古くなります）:\n"
        '    ToolSearch("select:mcp__context7__resolve-library-id,mcp__context7__query-docs")\n'
        "    → resolve-library-id → query-docs\n"
        "  **Context7 に当該ライブラリが無かった場合のみ `WebFetch` に戻り、その事実を1行報告してください。**"
        "黙って戻ると「規約が守られていない」と「Context7 に無かった」が区別できず、採用率を測れません。\n"
        "  ⚠️ 実測（2026-08-26）: Context7 は 122 セッションで露出して"
        "**実呼び出し 0 回**、同期間の WebFetch は 159 回でした。"
    )


def advise(payload):
    """`(ラベル, 本文)` のリストを返す（空なら黙る）。"""
    tool = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {})
    # 外部入力なので型を信用しない
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool == "WebFetch":
        name = _doc_source(tool_input.get("url"))
        if name:
            return [(LABEL, _body(name))]
    elif tool == "WebSearch":
        # 検索クエリは自由文なので、**公式ドキュメントのホスト名をクエリに書いている**
        # ときだけ拾う（`site:react.dev` 等）。「react」のような一般語で発火させると、
        # 障害調査や記事検索まで巻き込む
        query = str(tool_input.get("query", "") or "")
        for token in re.findall(r"[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?:/[A-Za-z0-9._\-/]*)?", query):
            name = _doc_source(token)
            if name:
                return [(LABEL, _body(name))]
    return []


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    advice = advise(payload)
    if not advice:
        return 0
    if project_hook_covers_context7():
        return 0

    text = "ツール選定の助言（~/.claude/hooks/advise_context7.sh・ブロックはしません）:\n\n" + \
        "\n\n".join("- " + body for _label, body in advice)
    labels = "／".join(dict.fromkeys(label for label, _body in advice))
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": text,
                "systemMessage": "ツール選定の助言: " + labels + "（非ブロッキング）",
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
