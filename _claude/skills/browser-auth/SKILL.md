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
- **フォーカスを繰り返し奪わない。** headed Chrome への `page.screenshot()` は再描画を
  起こすため、毎回撮ると画面がチラつく。`drive.py` は URL 変化時と明示要求時にしか撮らない。
  この前提を崩す改造をしない。
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

- ユーザーが入力する場面は **`--background` を付けない**（起動時にブラウザへフォーカスが要る）
- エージェントだけが操作する場面は **`--background`** を付ける。起動後に元のアプリへ
  フォーカスを戻すので、ユーザーの作業を邪魔しない

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
| `stop` | ブラウザを閉じて終了する |

同意画面の Allow やコンソールのボタンはエージェントが押して良い。ただし
**課金・削除・権限付与のような後戻りしにくい操作は、押す前にユーザーに確認する。**

### 5. 片付ける

```bash
echo '{"op":"stop"}' >> "$RT/<profile>/cmd.jsonl"
```

プロファイル（`$RT/<profile>/profile`）にはログインセッションが残る。scratchpad は
セッション固有なので、次のセッションでは再ログインになる。同じセッション内で
複数のコンソールを触るなら、プロファイルを使い回して起動し直すのが速い。

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
