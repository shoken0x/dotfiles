---
name: browser-auth
description: "ログイン・OAuth 同意・管理コンソールの操作を、ユーザーが資格情報を入力しエージェントが画面を見て誘導する形で進める。Triggers: 「ブラウザを起動して操作して」「認証は私が入力するので教えて」「ログイン画面を出して」「gcloud auth login を通して」「GCP/Slack App/kintone/Anthropic のコンソールを操作して」「2段階認証の先を手伝って」。パスワードや2FAコードはエージェントが入力せず、必ずユーザーに委ねる。"
disable-model-invocation: false
---

# ブラウザを立ててユーザーに認証してもらう

エージェントが画面を「見て」次に押すものを伝え、資格情報の入力だけユーザーが行う。
成果物は認証済みの状態そのもの（`gcloud` の credential、コンソール上の設定変更など）。

## 大原則

- **パスワード・2FAコード・リカバリコードは絶対に入力しない。** `fill` はメールアドレスや
  プロジェクト名のような非秘密の値にだけ使う。秘密の入力欄が出たらユーザーに渡す。
- 🔴 **起動そのものがユーザーの作業を止める。ウィンドウを開く回数を最小にすることが、
  フォーカス制御より優先する。** 2026-09-08、フォーカス修正を検証するために再起動を
  繰り返し、「毎回新規ウィンドウが開く。作業ができません」と止められた。
  ブラウザで済ませる作業と、ユーザーに手でやってもらう作業を先に切り分ける。
  数クリックで終わる管理画面の操作は、誘導するより渡した方が速い。
- **フォーカスを奪わない（既定）。** `drive.py` は `goto` の完了を待たずに元のアプリへ
  フォーカスを戻し、`hold_focus()` で数秒張り付いて戻し続ける。
  ユーザーが入力する場面だけ `--focus` を付ける。
  ⚠️ **`hold_focus()` は未検証。** 単発の `activate` だけでは Chrome が起動完了時に
  前面を取り返すことは実測済み（`now: Google Chrome`）。張り付きが効くかは確かめていない。
  次に触るときは**まずここを単体で検証**してから使う。効かない場合の候補は、
  起動直後に CDP `Browser.setWindowBounds` の `windowState: "minimized"` で最小化し、
  ユーザーが入力するときだけ Dock から戻してもらう形（スクリーンショットが
  最小化状態で撮れるかは未確認）。
- **ウィンドウ位置は固定する。** `--window left,top,width,height`（既定 `60,60,1280,900`）。
  永続プロファイルは前回のウィンドウ位置を復元するため `--window-position` フラグだけでは
  効かない。CDP の `Browser.setWindowBounds` で起動後に上書きしている。
- **`page.screenshot()` は再描画を起こす。** 毎回撮ると画面がチラつくので、
  `drive.py` は URL 変化時と明示要求時にしか撮らない。この前提を崩す改造をしない。
- 🔴 **ドライバを途中で再起動しない。** 再起動のたびにウィンドウが出てフォーカスが動き、
  ユーザーの作業を邪魔する。ページ移動は `goto` で行い、**1セッション1プロファイルにつき
  ドライバは1回だけ起動する。** 機能が足りないと気付いても、その場で `drive.py` を
  書き換えて再起動するのは最後の手段にする（2026-09-08 に op を足すために5回以上
  再起動して、実際に苦情になった）。
- **既定の Chrome プロファイルは使わない。** 通常 Chrome が起動しているとロックされている。
  `--profile` でサイトごとに分ける（`gcloud` / `slack` / `kintone` / `anthropic` など）。
  一度ログインすればそのプロファイルにセッションが残り、次回は入力が要らない。

## 手順

### 1. 起動する

`drive.py` はブラウザを開いたまま常駐し、状態を書き出し続ける。**必ず background で走らせる。**

```bash
SK=~/.claude/skills/browser-auth
RT=<scratchpad>/browser        # セッションの scratchpad 配下に置く
python3 -u "$SK/drive.py" --url "<URL>" --profile gcloud --runtime "$RT" \
  > "$RT/gcloud/driver.log" 2>&1
```

- **既定でフォーカスを奪わない。** ウィンドウは出るが、フォーカスはすぐ元のアプリへ戻る。
  ユーザーが入力する場面では「ウィンドウをクリックしてから入力してください」と伝える
- ユーザーがすぐ入力する場面だけ **`--focus`** を付ける（ブラウザにフォーカスを残す）
- ウィンドウ位置・サイズを変えるときは **`--window left,top,width,height`**
- 出力先ディレクトリは先に `mkdir -p "$RT/<profile>"` しておく

### 2. 画面を見る

```bash
cat "$RT/<profile>/state.json"     # URL / タイトル / 見出し / 入力欄 / ボタン
```

`state.json` は2秒ごとに更新される（DOM だけなので再描画なし）。
`screen.png` を Read すると実際の見た目が分かる。**URL が変わったときにしか更新されない**ので、
同じ画面のまま変化を見たいときは `{"op": "shot"}` を投げてから Read する。

### 3. ユーザーに伝える

`state.json` の `headings` と `inputs` から、いま何を入力する画面かを特定して伝える。
このとき **次に出る画面も併せて予告する**（ユーザーが迷わずに進める）。

```
いま出ている画面: 「Sign in — to continue to Google Cloud SDK」/ Email or phone 欄
この順で進みます:
1. メールアドレス → Next
2. パスワード → Next
3. 2段階認証
4. 同意画面「... wants to access your Google Account」→ Allow
```

見慣れない画面（アカウント選択・組織ポリシー・電話番号確認）が出たら、
スクリーンショットを撮ってから何を押すか伝える。

### 4. エージェントが操作する

`cmd.jsonl` に1行1 JSON で追記する。ドライバが順に実行し、結果を `driver.log` に書く。

```bash
echo '{"op":"click","selector":"text=Allow"}' >> "$RT/<profile>/cmd.jsonl"
sleep 3 && tail -3 "$RT/<profile>/driver.log"
```

| op | 用途 |
|---|---|
| `shot` | 今の画面を撮り直す |
| `goto` | `url` へ遷移する |
| `click` | `selector` をクリックする |
| `fill` | `selector` に `value` を入れる（**非秘密の値だけ**） |
| `type` | `selector` に1文字ずつ打つ（**非秘密の値だけ**） |
| `press` | `key` を押す（`Enter` / `Escape` / `Tab` など） |
| `insert` | `text` を一括挿入する。`clear: true` で全選択して置き換え。コードエディタ用 |
| `select` | `<select>` を `label` か `value` で選ぶ |
| `upload` | `path` のローカルファイルを file input に流す。`selector` 省略で `input[type=file]` |
| `value` | input の value を `value.txt`（`file` で変更可）に書く。**秘密の値の受け渡し用** |
| `html` | DOM を `dom.html`（`file` で変更可）に落とす。セレクタが当たらないとき構造を見る |
| `text` | ページの可視テキストを `text.txt` に落とす。`selector` 省略で `body` |
| `stop` | ブラウザを閉じて終了する |

`fill` は value を直接代入するので、**`keyup` / `input` を待って動く JS のフィルタや
検索ボックスには効かない**（値は入るが一覧が絞り込まれない）。そういう欄は `type` を使う。
一覧や表の中身を確かめたいときは、スクリーンショットを睨むより `text` の方が速く確実。

**コードエディタ（CodeMirror / Monaco）には `fill` も `type` も向かない。** `fill` は値を
代入するだけでエディタが変更に気付かず、`type` は自動インデントと括弧の自動補完で
JSON が壊れる。`insert`（`clear: true` 付き）を使う。JSON は1行に詰めて渡すと確実。

同意画面の Allow やコンソールのボタンはエージェントが押して良い。ただし
**課金・削除・権限付与のような後戻りしにくい操作は、押す前にユーザーに確認する。**

### 5. 片付ける

```bash
echo '{"op":"stop"}' >> "$RT/<profile>/cmd.jsonl"
```

プロファイル（`$RT/<profile>/profile`）にはログインセッションが残る。scratchpad は
セッション固有なので、次のセッションでは再ログインになる。同じセッション内で
複数のコンソールを触るなら、プロファイルを使い回して起動し直すのが速い。

## トークン・シークレットの取り出し方

管理コンソールから取り出した Bot Token や Signing Secret は、**エージェントの文脈に
載せずにファイルのまま次へ渡す。** 画面から読み取って会話に出すと、その値が
トランスクリプトに残る。

```bash
# 1. input の value をファイルに書く（値は表示されない。文字数だけログに出る）
echo '{"op":"value","selector":"input[value^=xoxb-]","file":"bot-token.txt"}' >> $RT/<profile>/cmd.jsonl
# 2. そのファイルをそのまま Secret Manager に流す
gcloud secrets create <name> --data-file="$RT/<profile>/bot-token.txt" --project=<project>
# 3. 検証は「先頭数文字」と「文字数」だけで行う。全体を cat しない
head -c 5 "$RT/<profile>/bot-token.txt"; wc -c < "$RT/<profile>/bot-token.txt"
# 4. 登録できたらローカルのファイルを消す
rm -f "$RT/<profile>/bot-token.txt"
```

`text` を使うと `text.txt` に画面全体が入り、そこに秘密が混ざることがある。
秘密を扱った後の `text.txt` は `cat` せず、必要な行だけ `grep` で抜くか消す。

🔴 **`dom.html` から要素を探すとき、`value=` だけを伏せても足りない。**
実際に踏んだ: Slack の Basic Information は、`value` にはマスク文字列を入れ、
**本物の秘密を `data-password` 属性に持っている。** `value="[^"]*"` だけを置換して
タグを出力した結果、Signing Secret と Client Secret がそのまま会話に流出した。

DOM から秘密を探すときは、**属性値を出力しない**のが唯一安全な方法。
`id` / `for` / `class` / `data-qa` だけを抜き出して表示し、値は一切通さない。

```python
# 安全: 属性名で場所を突き止め、値は触らない
ident = re.search(r'\bid="([^"]*)"', tag)
cls   = re.search(r'\bclass="([^"]*)"', tag)
print(ident.group(1) if ident else "-", cls.group(1) if cls else "-")
```

秘密を出してしまったら、**その場で再生成して露出した値を無効化する。**
Slack なら Basic Information の Regenerate（Client Secret は再生成後に旧値が
`Expiring Client Secret` として残るので Revoke も押す）。

もう一つの罠: **再生成すると要素が作り直され、`data-qa` のような属性が落ちることがある。**
Slack の Signing Secret は再生成後に `data-qa="signing_secret"` が消え、`id` だけが残った。
再生成した直後は、セレクタを作り直す前提で `html` を撮り直す。

**「N番目の password 欄」で秘密を選ばない。** 例えば Slack の Basic Information には
Client Secret と Signing Secret が並んでいて、どちらも32桁の16進数で見分けがつかない。
`html` で `id` / `aria-label` / `data-*` を確かめ、その属性で一意に指す。
ラベルの隣という前提（`following::input[1]` など）も、間に隠し input があると外れる。

## 中断されたコマンド投入に注意

`cmd.jsonl` への追記とその後の待機を**1つの Bash 呼び出しにまとめると、途中で中断された
ときに「投入だけ済んでいる」状態が起こる。** 2026-09-08、ユーザーが拒否した呼び出しの
1コマンド目が `cmd.jsonl` に残っており、ドライバがそれを実行していた。

拒否・中断のあとは、**次の操作の前に `cmd.jsonl` の末尾を確認する。**

```bash
tail -3 "$RT/<profile>/cmd.jsonl"   # 意図しないコマンドが入っていないか
tail -5 "$RT/<profile>/driver.log"  # それが実行されたか
```

そして、**予期しない状態変化を見つけても、時刻が重なっているだけで自分の操作のせいだと
報告しない。** ログに該当操作の記録が無く機構も説明できないなら、まず
「これはご自身の操作ですか」と聞く。

## 新しいタブ・ポップアップ

ドライバは `ctx.pages[0]` だけを見ている。OAuth の同意画面などが**別タブで開くと
見えない**（画面が変わらないので、処理中なのか待ち受けなのか区別できない）。
そのときは、いま見ているページを目的の一覧ページへ `goto` して**結果から判断する**
（例: アプリが実際に作られたかを一覧で確かめる）。

## `gcloud auth login` の場合

`gcloud auth login` は**自分で既定ブラウザを開き、`localhost:8085` で待つ**。
つまり URL は gcloud が出したものを使い、コールバックはどのブラウザからでも成立する。

```bash
# 1. gcloud を background で起動しておく（localhost:8085 で待機に入る）
# 2. その出力から URL を取り出す
grep -o 'https://accounts\.google\.com/\S*' <gcloud の出力ファイル>
# 3. その URL で drive.py を立てる（--profile gcloud）
# 4. ユーザーが 1〜4 を入力し、同意すると gcloud が自動で完了する
gcloud auth list --format="table(account,status)"
```

すでにユーザーの既定ブラウザに同じ URL のタブが開いている。**そこでログイン済みなら
1クリックで済む**ので、新規プロファイルで入力し直す前に「開いているタブで完了できないか」を
一度尋ねる価値がある。

## つまずいた点

- **`ntn` などの CLI に `-d @file.json` を渡すとき、stdin が繋がっていると stdin を優先する。**
  `while read` ループの中や、Python の `subprocess` から呼ぶと stdin 待ちで固まる。
  `< /dev/null` を付ける。ブラウザ操作とは別件だが、同じ「常駐＋コマンド投入」の型で踏む。
- **`launch_persistent_context` は `channel="chrome"` を指定しないと Playwright 同梱の
  Chromium を使う。** ユーザーが普段使う Chrome の見た目・拡張とは別物になるので、
  「いつもの画面と違う」と混乱させないために `chrome` を明示する。
