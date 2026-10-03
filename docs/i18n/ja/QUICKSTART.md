<!-- translated-from: QUICKSTART.en.md sha256:5d7f812cbbae -->
# Javis OS - クイックスタート

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · **日本語***

> このページは英語版クイックスタートの自動翻訳です。

数分で Javis OS を動かせます。詳しいガイド：[docs/](../../../docs/en/README.md)。

## 方法 1 - Hostinger VPS（Docker Manager、ワンクリック）

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

[docs/README.md](../../../docs/en/README.md) をご覧ください。機能ごとのガイドがあります（チャット／音声、ナレッジグラフ、Skill、Agent、Workflow、定期ジョブ、Kanban、自己学習、接続、Telegram、Zalo、Plugin、セキュリティ、バックアップなど）。ほとんどのページはベトナム語で書かれており、これまでに翻訳された分は [docs/en/](../../../docs/en/README.md) にあります。

## よくある問題

- **Hostinger でアプリ内のアップデートボタンが何もしない**：これは仕様です。Hostinger では Docker Manager の **Redeploy** を使ってください。アプリ内のボタンには Watchtower が必要ですが、Hostinger は通常 Docker ソケットをブロックしています。
- **ChatGPT/Codex が「model not supported」と言う**：Models ページで有効な Codex モデル（例：`gpt-5.5`）を選んでください。`gpt-5-mini` や `gpt-4o` は使わないでください。これらは API 用のモデルで、Codex アカウントでは動かせません。
- その他：[docs/17 - トラブルシューティング](../../../docs/en/17-troubleshooting.md)。
