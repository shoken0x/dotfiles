Before you go on your task, check the current git branch name. If it's something generic like an animal name, rename the git branch to match the task context appropriately. Do not do this for the main branch. If a specific issue or PR number is provided in the initial prompt, rename the branch so that the number is clearly included (e.g., `fix/issue-2183-top-list-count-published`).

## 文字使用のルール

- **丸数字（①②③、❶❷、⓵⓶ 等）は使用禁止**。代わりに半角数字（`1`, `2`, `3`）を使うこと
  - 対象: ユーザーへの回答、コード・コメント、コミットメッセージ、PR タイトル/本文、issue コメント、ドキュメント（CLAUDE.md / docs/ / wiki）、メモリファイル — 自分が書く全てのテキスト
  - 理由: 環境によって表示が崩れる・grep しにくい・機械処理しづらい
  - 例: `①ARD全NG ②締切の再フラグ` → `1. ARD全NG 2. 締切の再フラグ`（列挙は `1.` / `1)` / `(1)` などで表す）

## Notion の操作

- **Notion のページ取得・作成・編集には `ntn` コマンドを使う**。Notion API（`https://api.notion.com/...`）を curl で直接叩かない
  - 理由: `ntn` は Markdown で読み書きできるため、block オブジェクトを手組みする必要がなく確実
  - `ntn pages get <page-id>` — ページを Markdown（先頭に frontmatter）で取得
  - `ntn pages create --parent page:<id> < page.md` — 子ページを作成
  - `ntn pages edit <page-id> < page.md` — ページ本文を Markdown で置き換え
  - page-id は Notion URL 末尾の 32 桁 hex（ハイフン有無どちらでも可）
  - 認証は `NOTION_API_TOKEN` 環境変数。確認は `ntn whoami`

## Google Document の更新

- **既存の Doc は作り直さない。同じURLのまま中身を差し替える。** URLが変わると共有済みリンク・
  スプレッドシートの索引・Slackに貼った参照がまとめて切れる。
  - 本文ごと: `gog docs write <docId> --file report.md --markdown --replace`
    （`--markdown` は `--replace` か `--append` が必須。**インライン画像は消えるので入れ直す**）
  - 図の入れ直し: `gog docs insert-image <docId> --file pie.png --before "<本文にある見出し>" --width 468 --force`
  - 一部だけ: `gog docs find-replace <docId> "旧" "新"`（出力の `replacements` が0なら当たっていない）
  - 旧版を見比べたい／コメントを残したいときはタブを入れ替える:
    `docs add-tab --title` → `docs write --tab ... --replace` → `docs delete-tab --tab <旧> --force`
- 詳細は `gdoc-update` skill（`/gdoc-update`）。
