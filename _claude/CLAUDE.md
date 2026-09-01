Before you go on your task, check the current git branch name. If it's something generic like an animal name, rename the git branch to match the task context appropriately. Do not do this for the main branch. If a specific issue or PR number is provided in the initial prompt, rename the branch so that the number is clearly included (e.g., `fix/issue-2183-top-list-count-published`).

## 文字使用のルール

- **丸数字（①②③、❶❷、⓵⓶ 等）は使用禁止**。代わりに半角数字（`1`, `2`, `3`）を使うこと
  - 対象: ユーザーへの回答、コード・コメント、コミットメッセージ、PR タイトル/本文、issue コメント、ドキュメント（CLAUDE.md / docs/ / wiki）、メモリファイル — 自分が書く全てのテキスト
  - 理由: 環境によって表示が崩れる・grep しにくい・機械処理しづらい
  - 例: `①ARD全NG ②締切の再フラグ` → `1. ARD全NG 2. 締切の再フラグ`（列挙は `1.` / `1)` / `(1)` などで表す）
