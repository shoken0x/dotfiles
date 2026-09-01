# Claude Code の設定

`~/.claude` のうち **設定として手で書いたものだけ** をここで管理し、`~/.claude` 側から
symlink で参照する。配置コマンドは [`../ln_commands.sh`](../ln_commands.sh) の
「Claude Code」節にある。

## なぜディレクトリごと symlink しないのか

`~/.claude` は設定ディレクトリではなく**実行時ディレクトリ**で、会話ログ・認証状態・
DB・キャッシュが同居している。`~/.claude` 自体を symlink にすると、それらが全部この
PUBLIC リポジトリに入る。そのため個別に symlink する。

## 管理しているもの

| パス | 内容 |
| --- | --- |
| `CLAUDE.md` | 全プロジェクト共通のグローバル指示 |
| `settings.json` | hook 登録・permissions・plugin・statusLine |
| `statusline-command.sh` | ステータスライン（cx / 5h / 7d / 直前のプロンプト） |
| `hooks/` | `save_last_prompt.sh` / `guard_br_doctor_gitignore.sh` / `advise_context7.sh` とテスト |
| `commands/` | `/exit-cm` / `/tool-usage` |
| `toolstats/` | ツール使用状況の集計コードのみ（DB と state は `~/.claude` 側に残す） |
| `skills/` | 汎用スキルのみ（`diagram-craft` / `supacode-cli`） |

## 管理しないもの（絶対にコミットしない）

実測で危険を確認したものを含む:

- `~/.claude.json` … アカウント・MCP・OAuth の状態（180K）
- `history.jsonl` … 全プロンプト履歴。**実際にトークン形式の文字列を含むことを確認済み**
- `projects/`（会話ログ 694M）/ `security/`（361M）/ `plugins/`（315M・再取得可能）
- `sessions/*.key` / `file-history/` / `hook-approvals.log` / `shell-snapshots/`
- `toolstats/toolstats.db`（24M）/ `toolstats/state/`
- `statusline/last-prompt/` … 直前のプロンプト本文
- `cache/` `debug/` `telemetry/` `paste-cache/` `image-cache/` `session-env/` `tasks/` `ide/` `backups/`

`.gitignore` に安全網を置いてあるが、**一次防御は「個別に symlink する」という構造そのもの**。

## 社内固有の情報は入れない

このリポジトリは **PUBLIC**。社内リソース ID・業務メールアドレス・社内リポジトリ名を含む
スキルは、別に用意したローカル専用リポジトリ（remote 無し）に置き、`~/.claude/skills/` からは
symlink で参照する。判定は `check.sh` が機械的に行う。

## 検査

```bash
bash ~/git/dotfiles/_claude/check.sh
```

1. `~/.claude` 側が「このリポジトリを指す symlink」のままか
2. コミット対象に秘密値・社内固有名詞が混ざっていないか

🔴 **1 が要る理由**: Claude Code は plugin の追加や permission の承認で `settings.json` を
自分で書き換える。その書き込みが symlink の置き換えで行われると、**エラーも警告も出ないまま
リポジトリの追跡から外れる**（以後どれだけ設定を変えても diff に出ない）。
置き換えが実際に起きるかは**未確認**なので、起きた場合に気づけるようにこの検査を置いてある。
`❌ symlink ではなく実体になっている` が出たら、`diff` で差分を取り込んでから symlink に戻す。

## 既知の制約

`settings.json` の hook 定義に `/Users/shoken` が 9 箇所ある（inline python の引数など）。
**別のユーザー名のマシンではそのままでは動かない。** 実害はこのマシンでは無いので現状維持。
移植するときは `$HOME` に置き換える（inline python の引数は単一引用符の中なのでシェルが
展開しない。`"$HOME/..."` と二重引用符にする必要がある）。
