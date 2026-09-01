# toolstats — Claude Code のツール使用状況の可視化

「エージェントが Serena / ast-grep / context7 を**実際に使ったか**」を、リアルタイム・
セッション累計・期間集計の3面で見るための仕組み。全プロジェクト横断（`~/.claude` 配下に置く）。

## なぜ作ったか

道具を導入しても使われないことが繰り返し起きている（実測・2026-08-26 時点の全履歴 368 セッション）:

| 道具 | 呼び出し | 使ったセッション |
|---|---|---|
| Bash | 31,907 | 157 |
| ast-grep (CLI) | 88 | 4 |
| Serena MCP | 17 | 2 |
| context7 MCP | 3 | 1 |
| codebase-memory MCP | 0 | 0（露出 131 セッション） |
| code-investigator（サブエージェント） | 0 | 0（general-purpose は 237 回） |

🔴 **採用されていない状態は、正常に動いている状態と見た目が同じ**である。
`.claude/hooks/advise_tool_selection.sh` のヘッダも同じことを書いており、
「2026-09-30 に採用率を測る」と宣言している。これはその計測基盤。

## 構成

| ファイル | 役割 |
|---|---|
| `classify.py` | ツール呼び出し → カテゴリ。**Bash の中身も分解する**（ast-grep / cm / gog / kt は CLI なので） |
| `test_classify.py` | 分類の回帰テスト。ここが壊れると「使っていない」と「分類器が壊れた」が区別できなくなる |
| `collect.py` | transcript を増分で SQLite に取り込む。ステータスライン用の1行も事前レンダリング |
| `report.py` | ダッシュボード（`/tool-usage` の中身）。週次・月次・全期間 |
| `hook.sh` | PostToolUse / Stop / SessionStart から取り込みを起動。**同期コスト 20ms・常に exit 0** |
| `db.py` | SQLite スキーマ |
| `selftest.sh` | 全経路のスモークテスト |
| `toolstats.db` | データ本体（SQLite） |
| `state/<session>.line` / `.last` | ステータスラインが cat するだけの事前レンダリング結果 |

## データの出どころ

```
~/.claude/projects/<proj>/<session>.jsonl                    … メインセッション
~/.claude/projects/<proj>/<session>/subagents/agent-*.jsonl  … サブエージェント
```

🔴 **サブエージェントは別ファイル**。実測でツール呼び出しの **48%** がこちら側にある。
親セッション ID はパスから決めるので、main と sub は 1 セッションに集約される
（`main/sub` 列で内訳が見える。例: ast-grep は main 31 / sub 57 — 実際に使っているのは主にサブエージェント）。

⚠️ `tool_use.caller` は**サブエージェントでも常に `{"type":"direct"}`** なので、
このフィールドでは main/sub を判別できない。パスで判別すること。

## 数え方の約束

- **総呼び出し数 = events の行数**。1 呼び出し 1 行、主キーは `tool_use.id`（`toolu_...`）なので冪等
- **カテゴリ件数は合計しても総数にならない**。`git diff | grep foo` は git と grep の両方に数える（意図的）
- **`Bash の代表コマンド` は 1 呼び出しにつき 1 つ**。カテゴリ件数とは一致しない
- `露出セッション` = その MCP サーバー名が会話に載っていたセッション数
  （wiki `code-analysis-mcp-reality-check.md` の「使えたのに使わなかった母数」と同じ定義）

## 既知の限界（読み間違えないために）

1. **露出は生の文字列一致なので、解説文に書かれただけのサーバー名を拾う。**
   実測で `brand-new` / `servername` / `jira` / `plugin_my-plugin_*` が混入した
   （前2つはこのツール自身のテストコード由来）。既定では「呼び出し 0 かつ露出 5 セッション未満」を
   除外している（`CLAUDE_TOOLSTATS_MIN_EXPOSURE`）
2. **hook の発火は、出力があったものだけ transcript に残る。**
   `attachment.type` が `hook_success` / `hook_non_blocking_error` 等で記録されるが、
   何も出力せず成功した hook はレコードを残さない。よって「hook 発火数」は
   **「出力した回数」**であって発火回数ではない
3. **助言→採用の率は相関にすぎない。** 助言が原因とは言えず、無関係に使った分も入る。
   それでも「完全に無視されている」状態は検出できる
4. **文字列一致の過大計上を避けてある。** `grep -rn 'ast-grep' docs/` は ast-grep の使用ではない。
   コマンド位置でのみ判定するため、素朴な `\bast-grep\b` に比べ実測で 103 → 88 に下がった
   （15 件は誤検出だった）

## ステータスラインの2段構え（FOCUS と WATCH）

同じ「0 件」でも意味が違うので、表示を分けてある。

| 段 | 表示 | 入れる道具 | 0 の意味 |
|---|---|---|---|
| **FOCUS** | 0 でも常に出す | **代替手段がある**道具 | 「別の道を選んだ」＝情報 |
| **WATCH** | 非 0 のときだけ出す | **作業領域で決まる**道具 | 「その作業が無かった」＝情報なし |

既定の FOCUS（`classify.py` の `DEFAULT_FOCUS`）:

| 道具 | 代替 |
|---|---|
| `cli:ast-grep` | shell grep / Grep ツール |
| `mcp:serena` | Edit / Write |
| `mcp:context7` | WebFetch / WebSearch |
| `cli:cm`（cass memory system） | 記録しない |
| `cli:agent-browser` | Chrome MCP（skill 側が agent-browser を優先せよと明記している） |
| `agent:code-investigator` | general-purpose（CLAUDE.md は調査を code-investigator に投げよと書いている） |
| `lsp` | grep + Read（**合成カテゴリ**。下記参照） |

### `lsp` は合成カテゴリ（`ruby-lsp` をコマンド名で数えない理由）

🔴 **`ruby-lsp` バイナリの直接起動は全期間で 1 回しかない。**
ruby-lsp を起動するのは Serena と SessionStart hook（`setup_ruby_lsp_bundle.sh`）であって
こちらから叩くものではないため、コマンド名で数えると永久に 0 で何も分からない。
組み込みの `LSP` ツールも全期間 0 回。

実際に言語サーバを動かしているのは **Serena のシンボル系操作**なので、`lsp` は次の合計を数える:

- `LSP` ツール（組み込み）
- Serena の LSP 必須操作 — `find_symbol` / `find_referencing_symbols` / `find_declaration` /
  `find_implementations` / `get_diagnostics_for_file` / `get_symbols_overview` /
  `replace_symbol_body` / `insert_before_symbol` / `insert_after_symbol` /
  `rename_symbol` / `safe_delete_symbol`（`classify.py` の `_LSP_BACKED_SERENA`）
- `ruby-lsp` / `solargraph` / `sorbet` の直接起動

⚠️ `activate_project` / `get_current_config` / `*_memory` / `search_for_pattern` / `list_dir` は
**除外**している。LSP が死んでいても成功するので、含めると「LSP が生きている」証拠にならない
（このリポジトリは `LanguageServerTerminatedException` を繰り返し踏んでいる）。

⚠️ `lsp` は `mcp:serena` と**重複して数える**。カテゴリ件数の合計が総数と一致しないのは仕様。

`ruby-lsp` の直接起動回数そのものは WATCH の `rlsp`（`cli:ruby-lsp`）で見える。

既定の WATCH（`DEFAULT_WATCH`）: `gog` / `kt` / `ntn` / `br` / `ee` / `cass` / `bq` / `gcloud` /
`heroku` / `supacode` / `obsidian` / Figma・Chrome・supabase・GitHub・Kintone MCP /
`glossary-reviewer` / `migration-reviewer` / `Explore` / `general-purpose`。

⚠️ **`gog` / `kt` / `ntn` を FOCUS に入れないのは意図的。**
Sheets / Kintone / Notion の作業が無いセッションでは 0 が当然で、
常時 `gog·0` を出しても「選択を誤った」とは読めない。使ったときだけ出れば足りる。
FOCUS に入れたい場合は `CLAUDE_TOOLSTATS_FOCUS` で上書きする。

⚠️ **雑多な使用量内訳（`python·44 grep·8` 等）は既定で出さない**（`MAX_OTHERS=0`）。
ステータスラインでは読まれず、桁を食うだけだった。全件は `/tool-usage` で見る。

## ダッシュボードは全件列挙する

`/tool-usage` は **上位 N で切らない**。種別ごとに全件出す:

- MCP サーバー（呼び出しがあったもの＋載っていただけのもの）
- CLI（Bash を分解して判定・約 45 種のルール）
- 組み込みツール（Read / Edit / Agent / Skill / Artifact …）
- サブエージェント委譲先（`agent:<subagent_type>`）
- Skill（`skill:<name>`）
- **分類外の Bash コマンド**（= 追跡漏れの候補。ここに常用品があれば `CLI_RULES` に足す）

切ると「入れたのに使っていない道具」が消えるが、このダッシュボードで一番見たいのは
まさにそれなので省略しない。

## リアルタイム表示の仕組み

ステータスラインは**毎描画で走る**ので、そこで集計してはいけない（jq も python も起動しない）。

1. `hook.sh` が PostToolUse で `collect.py` を**切り離して**起動する（hook は待たない）
2. `collect.py` が state/<session>.line に **ANSI 込みで整形済みの1行**を書く
3. ステータスラインはそれを `cat` するだけ。経過秒（`◂ Bash▸ast-grep 4s`）だけ描画時に計算する
4. サブエージェント実行中は PostToolUse が主セッションで発火しないことがあるため、
   ステータスライン側も **transcript が state より新しく、かつ state が3秒以上前**なら
   取り込みを促す（3秒のクールダウンが無いとストリーミング中に毎描画で python が起動する）

🔴 **macOS の base には `setsid` コマンドが無い。** 最初 `setsid nohup ...` と書いたところ
hook は exit 0 のまま集計だけが一切走らない**完全な silent failure** になった。
perl の `POSIX::setsid` を使う（別のプロジェクトの `.claude/hooks/` でも同じ結論に至っている）。

## 使い方

```bash
/tool-usage              # 直近7日
/tool-usage month        # 直近30日
/tool-usage all          # 全期間
/tool-usage 90d

python3 ~/.claude/toolstats/report.py all           # 直接実行（色つき）
python3 ~/.claude/toolstats/report.py week --json    # 機械可読
python3 ~/.claude/toolstats/report.py --session latest  # 1 セッションだけ判定（道具選定テスト用）
python3 ~/.claude/toolstats/collect.py --all         # 取り込みだけ
python3 ~/.claude/toolstats/collect.py --all --reset # 分類を変えたら再構築（約6秒）
bash    ~/.claude/toolstats/selftest.sh             # 全経路のスモークテスト
```

## 設定（環境変数）

| 変数 | 既定 | 意味 |
|---|---|---|
| `CLAUDE_TOOLSTATS_DISABLE` | — | `1` で hook を無効化 |
| `CLAUDE_TOOLSTATS_FOCUS` | 上表の6件 | 0 でも常に表示する道具（カンマ区切り） |
| `CLAUDE_TOOLSTATS_WATCH` | `DEFAULT_WATCH` | 非 0 のときだけ表示する道具（カンマ区切り） |
| `CLAUDE_TOOLSTATS_MAX_OTHERS` | `0` | それ以外の使用量上位をいくつ出すか（0 = 出さない） |
| `CLAUDE_TOOLSTATS_MIN_EXPOSURE` | `5` | 呼び出し 0 の MCP を表示する露出セッション数の下限 |
| `CLAUDE_TOOLSTATS_DIR` | `~/.claude/toolstats` | データの置き場所 |

道具のキーは 5 種類 — `mcp:<server>` / `cli:<name>` / `builtin:<Tool>` / `agent:<subagent_type>` /
`skill:<name>`。ラベルは `classify.py` の `LABELS` で確認・変更する。
**新しい MCP サーバー・サブエージェント・Skill は `classify.py` を触らなくても自動で分類される。**
CLI だけは Bash の中身を見る必要があるので `CLI_RULES` に追記する
（`/tool-usage` の「分類外の Bash コマンド」が追記候補のリストになっている）。

## 道具が選ばれるかをテストする

### 原則

1. 🔴 **プロンプトに道具名を書かない。** 書いた瞬間「指示追従のテスト」になり、
   測りたい「自分で選ぶか」が測れなくなる
2. **タスクの形で誘導する。** CLAUDE.md のトリガに一致する形にする —
   ast-grep なら「引数の形」か「ネストの関係」が条件、Serena ならシンボル単位の編集か参照元調査
3. 🔴 **対照試行を必ず取る。** 名指しで同じことをやらせて成功するか見る。
   これが無いと `srn·0` が「選ばなかった」なのか「LSP が死んでいて使えなかった」なのか区別できない
4. **1 セッション 1 題材。** 同じセッションで両方測ると、1 つ目で使った道具に引きずられる
5. **検証可能な正解を先に用意する。** 出てきた答えが合っているかを別経路で確認できるようにする

### A/B（hook の効果を測る場合）

`advise_tool_selection.sh` は「引数の形の質問に grep を使っています」という助言を出す。
素の選定を測るなら切る:

```bash
HRG_TOOL_ADVICE=false claude     # 試行A: hook なし（素の選定）
claude                           # 試行B: hook あり（助言つき）
```

### 判定

```bash
python3 ~/.claude/toolstats/report.py --session latest
```

`✔ / ✘` と「競合相手（同じ用途で選ばれた道具）」が出る。
ステータスラインの `sg` / `srn` / `lsp` はセッション中もリアルタイムに見える。

### Serena を測るときの交絡（これを潰さないと結果が読めない）

| 前提 | 確認 | 欠けたときの症状 |
|---|---|---|
| `.mcp.json` の MCP が承認済み | `claude mcp list` | 繋がっておらず呼べない |
| worktree ごとに `activate_project`（**絶対パス**） | — | 別 worktree のファイルを黙って読む |
| `.ruby-lsp/` composed bundle がある | `ls .ruby-lsp/Gemfile.lock` | `LanguageServerTerminatedException` |
| `ruby-lsp` gem が `.ruby-version` と同じ Ruby に入っている | `RBENV_VERSION=$(cat .ruby-version) gem list ruby-lsp` | `command not found` |
| 他セッションが Serena を activate していない | — | **後勝ち**で別 worktree を見る（並列 worktree の罠） |

⚠️ **セッション途中で作った worktree には SessionStart hook が効かない。**
先に `printf '' | ruby-lsp` を回して composed bundle を作る（初回は `bundle install` で数分）。
⚠️ **一度 LSP 起動に失敗すると Serena がセッション内で失敗をキャッシュする。**
直したら Claude Code の再起動（MCP 再接続）が必要。

## 撤去のしかた

1. `~/.claude/settings.json` の `PostToolUse` / `Stop` / `SessionStart` から
   `bash ~/.claude/toolstats/hook.sh` の要素を消す
2. `~/.claude/statusline-command.sh` の `--- ツール使用状況（toolstats） ---` ブロックと
   最終行の `[ -n "$TOOLS_LINE" ] && ...` を消す
3. `rm -rf ~/.claude/toolstats ~/.claude/commands/tool-usage.md`

導入時のバックアップは `~/.claude/*.bak.<timestamp>` にある。
