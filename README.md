# PocketDesk (ポケットデスク)

ポケットの中に、自分のPCを。

スマホや別のPCから、自分のPCを遠隔操作するアプリです。
スマホ側にアプリは不要で、PCに表示されたQRコードを読み取るだけで使えます。

## かんたんな使い方 (Windows アプリ版)

1. [Releases](../../releases) または Actions の「Build Windows exe」から `PocketDesk.exe` をダウンロード
2. ダブルクリックで起動 (初回はファイアウォールの確認が出るので「プライベートネットワーク」で許可)
3. 窓に出たQRコードをスマホで読み取る → PCの画面が出て操作できます

アプリの窓でできること:

- 接続先の切り替え: **外出先 (Tailscale)** / **家のWi-Fi**
- URLのコピー
- **PCの起動時に自動で起動する** (チェックするだけ)
- **スマホ接続中はPCをスリープさせない**
- 画質: 高画質 / 標準 / 軽量 (モバイル回線向け)
- 合言葉を作り直す (スマホをなくしたときなど、古いURLを使えなくする)

設定は `%APPDATA%\PocketDesk\config.json`、動作ログは同じフォルダの `log.txt` に保存されます。

> 署名のない exe なので、初回は Windows SmartScreen の警告が出ます。「詳細情報」→「実行」で起動できます。

## スマホアプリ (Android .apk)

1. Actions の「Build Android apk」(タグを付けた場合は Releases) から `PocketDesk.apk` をダウンロード
2. スマホで開いてインストール (「提供元不明のアプリ」の許可を求められたら許可)
3. アプリの「QRコードを読み取る」で、PCの窓に出ているQRコードを読み取る
4. 次回からはアプリを開くだけで、すぐPCの画面が出ます

- 全画面表示で、操作中は画面が消えません
- 戻るボタンで「再読み込み / 接続先を変更 / 終了」

> 更新版を上書きインストールするには、毎回同じ鍵で署名する必要があります。
> リポジトリの Settings → Secrets に `ANDROID_KEYSTORE_BASE64` / `ANDROID_KEYSTORE_PASSWORD` /
> `ANDROID_KEY_ALIAS` / `ANDROID_KEY_PASSWORD` を登録すると、その鍵で署名されます。
> 未設定の場合は、更新時に一度アンインストールしてから入れ直してください。

iPhone の場合は、Safari でURLを開いて「ホーム画面に追加」すると、アプリのように使えます。

## 外出先から使う (Tailscale)

1. PC と スマホ の両方に [Tailscale](https://tailscale.com/download) を入れ、同じアカウントでログイン
2. アプリの窓で「外出先 (Tailscale)」を選び、表示されたQRコードをスマホで読み取る
3. スマホで開いたページを「ホーム画面に追加」しておくと、次からアイコン1つで接続できます

通信は Tailscale が暗号化します。**ルーターのポート開放でインターネットに直接公開しないでください。**

## スマホでの操作

- **直接タップ**: タップ=クリック / 長押し=右クリック / なぞる=ドラッグ / 2本指=スクロール
- **トラックパッド**: 1本指でカーソル移動 / タップ=クリック / 2本指タップ=右クリック
- 下の入力欄で文字入力 (日本語OK)、「キー」ボタンで Enter・矢印・Ctrl+C/V・Alt+Tab など

## Python から使う (Windows / macOS / Linux)

```bash
pip install -r requirements.txt
python -m remote_control.app       # アプリ版 (窓あり)
python -m remote_control           # コマンドライン版
```

コマンドライン版のオプション:

| オプション | 説明 |
|---|---|
| `--show-url` | 接続URLとQRコードを表示して終了 |
| `--new-token` | 合言葉を作り直して保存 |
| `--install-autostart` / `--uninstall-autostart` | PC起動時の自動起動を登録 / 解除 |
| `--port` `--fps` `--max-width` `--quality` `--monitor` | 一時的に設定を上書き |

OSごとの注意:

- **macOS**: 「システム設定 → プライバシーとセキュリティ」で「画面収録」と「アクセシビリティ」を許可
- **Linux**: X11 環境が必要 (Wayland では画面キャプチャ・入力が制限されます)

## exe のビルド

GitHub に push すると、GitHub Actions が Windows 上で自動ビルドし、起動テストまで行います。
`v1.0.0` のようなタグを push すると Releases にも exe が公開されます。

手元でビルドする場合 (Windows):

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name PocketDesk --add-data "remote_control/static;remote_control/static" --hidden-import PIL.ImageTk run_app.py
```

## 開発

```bash
pip install -r requirements.txt pytest pytest-asyncio
python -m pytest
```
