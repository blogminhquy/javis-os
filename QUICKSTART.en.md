# Javis OS - Quick start

***English** · [Tiếng Việt](QUICKSTART.md) · [简体中文](docs/i18n/zh/QUICKSTART.md) · [Español](docs/i18n/es/QUICKSTART.md) · [日本語](docs/i18n/ja/QUICKSTART.md) · [हिन्दी](docs/i18n/hi/QUICKSTART.md) · [Português](docs/i18n/pt-BR/QUICKSTART.md) · [한국어](docs/i18n/ko/QUICKSTART.md) · [Русский](docs/i18n/ru/QUICKSTART.md) · [Deutsch](docs/i18n/de/QUICKSTART.md) · [Français](docs/i18n/fr/QUICKSTART.md) · [Bahasa Indonesia](docs/i18n/id/QUICKSTART.md)*

Get Javis OS running in a few minutes. Full guides: [docs/en/](docs/en/README.md).

## Option 1 - Hostinger VPS (Docker Manager, one click)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Paste this URL:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Optional, for HTTPS + a domain) set this in the **Environment** box:
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (Find the hostname under hPanel → VPS, e.g. `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Wait 1-3 minutes. Open the app with the **Open** button (or `https://<DOMAIN_NAME>`).
5. On first run the screen asks you to create an admin account. After that, sign in to Claude Code once inside the container terminal: `claude auth login --claudeai`.

To update: press **Redeploy** in Docker Manager (image `:latest`, `pull_policy: always`). Brain data stays in the volume.

## Option 2 - Docker on any machine or VPS

```
docker compose -f docker-compose.yml up -d
```
Open http://localhost:7777. For HTTPS through Caddy, add `-f docker-compose.https.yml`.

## Option 3 - Run directly (Windows, no Docker)

1. Install Python 3.12 + Node 22.
2. In the project folder run `setup.bat` once - it creates .venv, installs dependencies, and installs the two CLI engines (Claude Code, Codex) for you.
3. `start-javis.bat` to run in the background (`stop-javis.bat` to stop).
4. Open http://localhost:7777.

## Once it is running

- **Pick an engine/model**: the **Models** page (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, DeepSeek, Ollama).
- **Wire up connections** (POS, ads, calendar, Zalo...) so reports run on real numbers: the **Connections** page - see [docs/09](docs/en/09-connections-and-business-data.md).
- **Back the brain up to GitHub** so you do not lose data: the **Self-learning** page - see [docs/18](docs/en/18-github-backup.md).
- **Watch token spend**: the **Usage** page - see [docs/23](docs/en/23-usage-and-cost.md).

## Full documentation

See [docs/en/README.md](docs/en/README.md) - a guide per feature (chat/voice, knowledge graph, skills, agents, workflows, recurring jobs, Kanban, self-learning, connections, Telegram, Zalo, plugins, security, backup...). The same guides in Vietnamese: [docs/README.md](docs/README.md).

## Common problems

- **The in-app update button does nothing on Hostinger**: that is by design - on Hostinger use **Redeploy** in Docker Manager. The in-app button needs Watchtower, and Hostinger usually blocks the Docker socket.
- **ChatGPT/Codex says "model not supported"**: pick a valid Codex model on the Models page (e.g. `gpt-5.5`). Do not use `gpt-5-mini` or `gpt-4o` - those are API models and a Codex account cannot run them.
- More: [docs/17 - Troubleshooting](docs/en/17-troubleshooting.md).
