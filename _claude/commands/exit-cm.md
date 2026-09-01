---
description: 本日の学びを cm に記録する（必要ならチーム playbook へ昇格して PR まで作成）
allowed-tools: Bash(cm add:*), Bash(cm context:*), Bash(cm similar:*), Bash(cm ls:*), Bash(cm playbook:*), Bash(cm stats:*), Bash(cm doctor:*), Bash(jq:*), Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(git branch:*), Bash(git checkout:*), Bash(gh pr create:*), Bash(gh pr view:*)
---

これまでの対話内容を振り返り、本日新しく得た tip / 学び（バグ回避策・ツール選定・環境依存・ハマりどころ・再利用可能な手順など）を抽出して `cm`（cass memory system）に記録してください。

## 手順

1. 今回のセッションで得た「再利用可能な学び」を洗い出す。コードから自明なこと・そのセッション限りの事情は除外する。

2. 重複を避けるため、記録候補ごとに既存 tip を確認する。

   ```bash
   cm similar "<要点を1文で>" --threshold 0.5 --json
   ```

   🔴 **`--threshold 0.5` を必ず付けること。** 既定値は 0.7 で、日本語では同義の tip でも 0.53〜0.59 程度にしかならず**取りこぼす**（2026-08-25 実測）。
   `--json` を付けると件数と `similarity` が確実に読める。

   既存に近いものがあれば新規追加せず、必要なら内容を補足する。

3. 新しい学びを追加する。

   ```bash
   cm add "<ルール文>" --category <カテゴリ>
   ```

   - カテゴリ例: `stg3`, `gog`, `hrg-auth`, `google-workspace`, `tooling`, `meta`, `mcp`, `testing`, `rails`, `heroku`, `github`
   - 1件ずつ、簡潔で行動可能な文にする
   - 出力に表示される bullet ID を控える（手順4で使う）

4. チーム共有すべき tip があれば、**ユーザーに伝えたうえで** `.cass/playbook.yaml` へ昇格する。

   ⚠️ **一括昇格は禁止。** `cm playbook export` は個人層とチーム層を全て `scope: global` にフラット化して出力するため、
   丸ごと import すると無関係な個人下書きが流入し、他メンバーが編集した既存 bullet を自分のローカル版で上書きする。
   **必ず ID で絞ること。**

   ```bash
   cm playbook export --json \
     | jq '.data | .bullets |= map(select(.id=="<id1>" or .id=="<id2>"))' > /tmp/cm_promote.json
   cm playbook import --repo --replace /tmp/cm_promote.json
   git diff .cass/playbook.yaml   # 意図した追加のみ・deletions 0 を確認
   ```

   確認できたら通常の PR フローでコミットする。

   - ブランチは最新の `develop` から切る
   - コミットメッセージ例: `chore(cm): <学び> を team playbook に昇格`
   - **`.cass/playbook.yaml` のみの差分なら `@claude` レビュー依頼は不要**（CLAUDE.md のドキュメント例外）。
     PR 作成と CI パスは必要

5. 記録した内容を箇条書きで要約して報告する。学びが無ければ「記録すべき新しい学びはありませんでした」と明示する。

6. 報告したら、**ユーザーに `/exit` の実行を促して終了する**。

   ⚠️ `/exit` は Claude Code の組み込みコマンドで、**モデル側からは実行できない**。
   自分で `/exit` を呼ぼうとしないこと。

## 前提（動かないときの確認先）

`cm` の日本語検索は 2026-08-25 に修正済み。もし `PLAYBOOK RULES (0)` しか返らない場合はここを疑う。

| 設定 | あるべき値 | 備考 |
| --- | --- | --- |
| `~/.cass-memory/config.json` の `semanticSearchEnabled` | `true` | `false` だとキーワード検索になり、日本語のカタカナ複合語に当たらない |
| 同 `embeddingModel` | `Xenova/paraphrase-multilingual-MiniLM-L12-v2` | `Xenova/all-MiniLM-L6-v2` は**英語専用**。フラグだけ立てても日本語では機能しない |

モデルを変更した直後の初回実行は、モデル DL + 全 bullet の再埋め込みで **13分程度**かかる（440件で実測）。
2回目以降は約 2秒。埋め込みキャッシュ `~/.cass-memory/embeddings/bullets.json` は使用モデル名を記録しており、
モデルを変えると自動で再計算される。

`cm context` の `HISTORY` が `cass: INDEX_MISSING` になる場合は `cass index --full` が未実行。
PLAYBOOK RULES 側だけでも手順2の重複チェックは成立するので、必須ではない。
