<!-- translated-from: QUICKSTART.en.md sha256:2f4928f341af -->
# Javis OS - クイックスタート

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · **日本語** · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> このページは英語版クイックスタートの自動翻訳です。

数分で Javis OS を動かせます。詳しいガイド：[docs/en/](../../../docs/en/README.md)。

## パソコン（Windows、macOS）- インストーラーをダウンロード

Javis を普通のアプリのようにインストールできます。ファイルを 1 つダウンロードして開けば、毎日クリックする JAVIS OS アイコンができます。インストーラーはパソコンに足りないもの（Git、Python、Node、AI ブレイン）を確認し、足りない分だけをインストールします。

- **Windows 10/11:** [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe) をダウンロードし、ダブルクリックして最後まで Next を押します。黒いウィンドウに進行状況が表示されます（数分）。完了するとデスクトップとスタートメニューに JAVIS OS アイコンができます。
- **macOS 11 以降:** [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg) をダウンロードして開き、**JAVIS OS** を **Applications** にドラッグしてから Launchpad で開きます。初回はターミナルが開いてインストールします（Javis の管理者アカウントの設定と、Mac のパスワードを一度求められることがあります）。

アイコンをクリックすると Javis は専用ウィンドウ（アドレスバーなし）で開き、パソコンの起動時に自動で動き、アプリ内の **Update** ボタンも通常どおり使えます。データはユーザーフォルダ内の `JavisOS` フォルダにあり、アプリをアンインストールしてもこのフォルダは残ります。

どちらのインストーラーもまだコード署名されていないため、初回に確認が表示されます:
- Windows で「Windows protected your PC」と出たら、**More info** を押してから **Run anyway** を押します。
- macOS で開けないと表示されたら、**System Settings → Privacy & Security** を開き、下にスクロールして **Open Anyway** を押し、もう一度 JAVIS OS を開きます。

## 方法 1 - Hostinger VPS（Docker Manager、ワンクリック）

> 🛒 **VPS をまだお持ちでない方へ：** [Hostinger VPS はこちら](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN)。Docker Manager が標準搭載なので、Javis はワンクリックで入ります。準備ができたら下の手順に戻ってください。

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**。
2. 次の URL を貼り付けます。
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. （任意。HTTPS + ドメインを使う場合）**Environment** 欄に次を設定します。
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   （ホスト名は hPanel → VPS で確認できます。例：`javis.srv1782015.hstgr.cloud`。）
4. **Deploy** を押します。1-3 分待ちます。**Open** ボタン（または `https://<DOMAIN_NAME>`）でアプリを開きます。
5. 初回起動時に、管理者アカウントの作成を求める画面が表示されます。そのあと、コンテナのターミナルで Claude Code に一度だけサインインします：`claude auth login --claudeai`。

アップデートするには：Docker Manager で **Redeploy** を押します（イメージは `:latest`、`pull_policy: always`）。Brain のデータはボリュームに残ります。

## 方法 2 - 任意のマシンや VPS で Docker

> 🛒 **VPS が必要ですか？** この方法も [Hostinger VPS](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN) で動きます。

```
docker compose -f docker-compose.yml up -d
```
http://localhost:7777 を開きます。Caddy 経由で HTTPS を使う場合は `-f docker-compose.https.yml` を追加してください。

## 方法 3 - 直接実行（Windows、Docker なし）

1. Python 3.12 + Node 22 をインストールします。
2. プロジェクトのフォルダで `setup.bat` を一度実行します。.venv を作成し、依存関係をインストールし、2 つの CLI エンジン（Claude Code、Codex）もインストールしてくれます。
3. `start-javis.bat` でバックグラウンド実行します（停止は `stop-javis.bat`）。
4. http://localhost:7777 を開きます。

## 起動したら

- **エンジン／モデルを選ぶ**：**Models** ページ（Claude Code、ChatGPT/Codex、Antigravity CLI、OpenRouter、OpenAI、Google Gemini、Anthropic API、Groq、Ollama）。
- **接続をつなぐ**（POS、広告、カレンダー、Zalo など）と、実際の数値にもとづいたレポートが出せます：**Connections** ページ。[docs/09](../../../docs/en/09-connections-and-business-data.md) を参照。
- **Brain を GitHub にバックアップ** して、データを失わないようにします：**Self-learning** ページ。[docs/18](../../../docs/en/18-github-backup.md) を参照。
- **トークンの消費を確認する**：**Usage** ページ。[docs/23](../../../docs/en/23-usage-and-cost.md) を参照。

## 完全なドキュメント

[docs/en/README.md](../../../docs/en/README.md) をご覧ください。機能ごとのガイドがあります（チャット／音声、ナレッジグラフ、Skill、Agent、Workflow、定期ジョブ、Kanban、自己学習、接続、Telegram、Zalo、Plugin、セキュリティ、バックアップなど）。同じガイドのベトナム語版は [docs/README.md](../../../docs/README.md) にあります。

## よくある問題

- **Hostinger でアプリ内のアップデートボタンが何もしない**：これは仕様です。Hostinger では Docker Manager の **Redeploy** を使ってください。アプリ内のボタンには Watchtower が必要ですが、Hostinger は通常 Docker ソケットをブロックしています。
- **ChatGPT/Codex が「model not supported」と言う**：Models ページで有効な Codex モデル（例：`gpt-5.5`）を選んでください。`gpt-5-mini` や `gpt-4o` は使わないでください。これらは API 用のモデルで、Codex アカウントでは動かせません。
- その他：[docs/17 - トラブルシューティング](../../../docs/en/17-troubleshooting.md)。
