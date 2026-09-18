---
name: agy-review
description: 設計文書・PR・実装方針を、別セッションの Antigravity CLI（`agy`）にレビューさせる。Prowl の隣 pane で `agy` を起動し、依頼文をファイルで渡し、結果をファイルで受け取るまで。Triggers 「別のモデルにレビューさせて」「agy にレビューしてもらって」「設計書をレビューさせて」「セカンドオピニオンが欲しい」「別セッションレビューを回して」。⚠️ `gemini` CLI は個人アカウントでは使えなくなっているので使わない（本文の §0 参照）。
---

# agy にレビューさせる

自分（Claude Code）が書いた設計文書や実装方針を、**別のモデル・別のコンテキスト**に見せて指摘を得るための手順。

同じセッションで自己レビューしても、自分の前提がそのまま通るだけで穴は見つからない。別プロセスに
**リポジトリを実際に読ませて**指摘させることに意味がある。

---

## 0. 🔴 `gemini` CLI は使わない

`@google/gemini-cli` は**個人アカウントのサインインが打ち切られている**。2026-09-18 に実測:

```
Failed to sign in. Message: This client is no longer supported for Gemini Code Assist for
individuals. To continue using Gemini, please migrate to the Antigravity suite of products:
https://antigravity.google
```

Vertex AI 経路に逃げることもできるが、SA のプロジェクトで Agent Platform API が無効なら 403 になり、
**有効化は課金が発生する変更**なので勝手にやらない。

→ **`agy`（Antigravity CLI）を使う。** `command -v agy` で確認する。

---

## 1. 依頼文を**ファイル**に書く

プロンプトを引数に直接埋めない。長文をターミナルへ送ると壊れる（§5-1）。

```bash
cat > tmp/agy_review_request.md <<'EOF'
# レビュー依頼

## 対象
<ファイル/ディレクトリを列挙。分量が大きいものは「ここが主対象」と明示>

## 前提
<何をしようとしているプロジェクトなのか。3〜5行>

## 見てほしい観点（優先度順）
1. 🔴 <最優先の軸。過去に重大な指摘を生んだ軸があるならそれを1番に置く>
2. ...

## 出力形式
VERDICT: APPROVE | CHANGES_REQUESTED
## BLOCKER / ## MAJOR / ## MINOR / ## 良かった点
（各項目に [ファイル:行] 指摘 / 根拠 / 提案）

## 重要なお願い
- 🔴 推測で「おそらくこうなっている」と書かない。確認していない主張は「未確認」と明記する
- 指摘には必ず根拠（読んだ箇所・実行したコマンドと出力）を添える
- 文書の修正はしない。指摘だけを返す
- 出力は `tmp/agy_review_result.md` に書き出す

作業ディレクトリは <絶対パス> です。
EOF
```

**効く指示**（実測で効果があったもの）:

- **観点に優先度を付ける。** 「全部見て」より「1 が最優先」の方が深く見る
- **`file:line` の主張は実ファイルを開いて確かめて**と書く。書かないと文書を読むだけで終わる
- **出力をファイルに書かせる。** 画面はスクロールで欠ける（§5-4）
- **修正させない。** レビューと編集を同時にやらせると差分が混ざって切り分けられなくなる

---

## 2. 隣に pane を作る

`prowl-cli` skill の識別ガードを通してから作る。

```bash
me="$(prowl list --json | jq -c --arg p "$PROWL_PANE_ID" '.data.items[] | select(.pane.id == $p)')"
[ -z "$me" ] && { echo "自分の pane を特定できないので中止"; exit 1; }

pane="$(prowl create pane "$PROWL_PANE_ID" --direction right --json | jq -r '.data.target.pane.id')"
echo "$pane" > /tmp/agy_pane.txt   # scratchpad があればそちらへ
```

⚠️ **Prowl の Profile 経由（`--profile`）は使えない。** `agy` の Profile は標準では無く、
`Gemini CLI` Profile は PATH 判定で `unavailable` になる（そして §0 のとおり使えない）。
素の pane を作って `prowl send` で起動する。

---

## 3. 起動する前に、作業ツリーを綺麗にしておく

🔴 **これを先にやる。** 次の手順で権限プロンプトを全部スキップするため、
**agy が何か書いても `git status` で見えて戻せる状態**にしておく必要がある。

```bash
git status --short          # 空であること
git rev-list --left-right --count @{u}...HEAD   # 0 0（push 済み）
```

汚れているならコミットするか、レビューを待たせる。

---

## 4. `agy` を起動する

```bash
pane="$(cat /tmp/agy_pane.txt)"
prowl send --pane "$pane" 'agy --dangerously-skip-permissions --effort high -i "$(cat tmp/agy_review_request.md)"' --no-wait --json
```

| フラグ | 理由 |
| --- | --- |
| `--dangerously-skip-permissions` | 付けないと**1コマンドごとに確認が出て進まない**。レビューは数十回ファイルを読むため、代理で答え続けるのは現実的でない。§3 の前提とセット |
| `--effort high` | 既定より深く読む。レビュー用途では効く |
| `-i`（`--prompt-interactive`） | 初回プロンプトを渡してセッションを継続する。追加質問を投げられる |
| `"$(cat ...)"` | 長文を安全に渡す。引数に直書きしない（§5-1） |

**初回だけ**フォルダ信頼の確認が出る。リポジトリに `.agy` / `GEMINI.md` 等の
設定が無いことを確認してから `enter` を送る。

```bash
ls -la .gemini .agy GEMINI.md 2>/dev/null || echo "リポジトリ固有の設定は無し"
prowl key --pane "$pane" enter --json
```

⚠️ 信頼を選ぶと **agy は再起動する**（`Antigravity CLI is restarting to apply the trust changes...`）。
再起動後にプロンプトが戻るまで待つ。

---

## 5. 踏んだ罠（すべて 2026-09-18 に実測）

### 5-1. シェルが起動しきる前に `send` すると、貼り付けエスケープが本文に混ざる

新しい pane を作った直後に送ると、こうなる:

```
% ;2;13~[200~cd /Users/shoken/... && npx -y @google/gemini-cli@latest~
zsh: command not found: 2
zsh: bad pattern: 13~[200~cd
```

対処: **一度 `clear` を `--capture` で送って、シェルが応答することを確認してから**本命を送る。

```bash
prowl key --pane "$pane" ctrl-c --json >/dev/null
prowl send --pane "$pane" 'clear' --capture --timeout 20 --json | jq -r '.data.wait.exit_code'   # 0 を確認
prowl send --pane "$pane" '<本命>' --no-wait --json
```

### 5-2. 🔴 `agy` の生存判定に `prowl agents` を使わない

`prowl agents` の検出は **agy が長いターンを回している間、何分も消える**。
2026-09-18 に 2 回誤検知した（1 回目は即時判定、2 回目は「連続 4 回（2 分）不在」でも誤検知）。
どちらも agy は稼働中で、直後の `prowl read` にツール実行が写っていた。

**閾値を上げて粘るのではなく、判定材料を変える。** 生存は**画面が変わっているか**で見る:

```bash
prev=""; still=0
while true; do
  [ -f tmp/agy_review_result.md ] && { echo "結果が出た: $(wc -l < tmp/agy_review_result.md) 行"; break; }
  cur=$(prowl read --pane "$pane" --last 12 --json | jq -r '.data.text' | md5)
  if [ "$cur" = "$prev" ]; then still=$((still+1)); else still=0; fi
  prev="$cur"
  # 画面が 5 分動かない = 完了して待機中か、止まっているか。どちらも人が見る必要がある
  [ "$still" -ge 10 ] && { echo "画面が5分動いていない。pane を確認すること"; break; }
  sleep 30
done
```

⚠️ `prowl agents --json` の `status` は**参考情報**として見るのはよいが、
**それだけで「終了した」と結論しない**。必ず `prowl read` で画面を見て裏を取る。

### 5-3. 起動直後は `agents` に出てこない。検出を待ってから次を送る

`npx` 経由だとダウンロードで数十秒かかる。検出前に送った入力は起動中のランタイムに飲まれる。

```bash
until prowl agents --json | jq -e --arg p "$pane" '.data.agents[]|select(.pane.id==$p)' >/dev/null; do sleep 5; done
```

### 5-4. 画面を読むな、ファイルを読め

`prowl read` は viewport なので折り返し・省略（`(ctrl+o to expand)`）で欠ける。
**結果は必ずファイルに書かせて `cat` で読む。**

---

## 6. 結果を受け取ったら

1. **指摘を鵜呑みにしない。** 各指摘を**自分でコマンドを叩いて再検証する**。
   別モデルも間違える（file:line のずれ、母数の数え間違い）
2. **正しかった指摘 / 誤っていた指摘を分けて報告する。** 「全部直した」ではなく
   「N 件中 M 件が正しく、M' 件は誤りだった（根拠）」
3. 設計文書を直すなら、**レビュー記録を凍結文書として残す**
   （`design_review_YYYYMMDD.md` 等。履歴なので後から書き換えない）
4. pane を片付ける: `prowl close "$pane" --json`

---

## 7. 追加で質問したいとき

`-i` で起動していればセッションが続いている。同じ pane に送ればよい。

```bash
prowl agents wait "$pane" --until idle --timeout 120 --json >/dev/null
prowl send --pane "$pane" 'BLOCKER 2 の根拠になったファイルと行を、コマンド出力付きで示して' --no-wait --json
```

⚠️ **idle を待たずに送ると、走っているターンに文字列が混ざる。**
