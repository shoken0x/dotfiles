---
description: ツール使用状況のダッシュボード（Serena / ast-grep / context7 等を使ったか。週次・月次・全期間）
argument-hint: "[week|month|all|90d]"
allowed-tools: Bash(python3 ~/.claude/toolstats/report.py:*), Bash(~/.claude/toolstats/report.py:*), Bash(python3 /Users/shoken/.claude/toolstats/report.py:*)
---

引数: `$ARGUMENTS`

## やること

1. 引数を `week` / `month` / `all` / `90d` のいずれかに正規化する（空なら `week`）。
   日本語で渡された場合も `report.py` 側が解釈するのでそのまま渡してよい
   （`週次` `月次` `全期間` `今週` `今月` は対応済み）。

2. 次のコマンドを1回だけ実行する。

   ```bash
   python3 ~/.claude/toolstats/report.py $ARGUMENTS
   ```

3. **出力をそのままコードブロックに入れて提示する。**
   要約・並べ替え・数値の言い換えをしないこと（このダッシュボードは実測値を見るためのもので、
   要約すると「どの道具を使っていないか」という肝心の 0 が消える）。

4. 出力の下に、**気づいたことを2〜3行だけ**添える。
   書くのは「到達率が極端に低い注目ツール」「選択比が偏っているペア」「露出はあるのに呼び出し 0 の MCP」など、
   数字から直接言えることに限る。推測で理由を書かない。

## 補足

- 集計は実行時に `collect.py --all` が増分で走るので、最新のセッションまで反映される（フル再構築でも約6秒）
- **出力は全ツール・全 MCP を列挙する（上位 N で切らない）。** 種別は MCP / CLI / 組み込み /
  サブエージェント委譲先 / Skill / 分類外 Bash コマンド。長くても省略せず全部見せること
- 期間を変えて見たいと言われたら、同じコマンドを別の引数で再実行する
- 「なぜこの数字なのか」を聞かれたら、生データは `~/.claude/toolstats/toolstats.db`（SQLite）にある。
  `report.py --json` で機械可読の出力も取れる
- 分類ロジックの定義は `~/.claude/toolstats/classify.py`、仕様は `~/.claude/toolstats/README.md`
