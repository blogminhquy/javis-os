# Javis OS - Quick start

***English** · [Tiếng Việt](QUICKSTART.md) · [简体中文](docs/i18n/zh/QUICKSTART.md) · [Español](docs/i18n/es/QUICKSTART.md) · [日本語](docs/i18n/ja/QUICKSTART.md) · [हिन्दी](docs/i18n/hi/QUICKSTART.md) · [Português](docs/i18n/pt-BR/QUICKSTART.md) · [한국어](docs/i18n/ko/QUICKSTART.md) · [Русский](docs/i18n/ru/QUICKSTART.md) · [Deutsch](docs/i18n/de/QUICKSTART.md) · [Français](docs/i18n/fr/QUICKSTART.md) · [Bahasa Indonesia](docs/i18n/id/QUICKSTART.md)*

Get Javis OS running in a few minutes. Full guides: [docs/en/](docs/en/README.md).

## Personal computer (Windows, macOS) - download the installer

Install Javis like any other app: download one file, open it, and you get a JAVIS OS icon to click every day. The installer checks what the computer is missing (Git, Python, Node, the AI brains) and installs only that.

- **Windows 10/11:** download [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe), double-click it and press Next to the end. The install progress shows inside the Setup window itself, step by step (a few minutes), with no separate black window. When it is done there is a JAVIS OS icon on the Desktop and in the Start menu.
- **macOS 11 or newer:** download [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg), open it, drag **JAVIS OS** into **Applications**, then open it from Launchpad. The first time, Terminal opens to install (it may ask you to set a Javis admin account and for your Mac password once).

Clicking the icon opens Javis in its own window (no address bar), Javis starts with the computer, and the in-app **Update** button works as usual. Your data lives in the `JavisOS` folder in your user folder; uninstalling the app keeps that folder.

**Install without the warning screen (recommended).** Both installers are not code-signed yet, so a browser download gets blocked the first time. Paste one line instead and you get the same installer with the Javis logo, unblocked:
- **Windows:** press Start, type `PowerShell`, open it, paste this line and press Enter:
  ```
  irm https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/windows/get-javis.ps1 | iex
  ```
- **macOS:** open **Terminal** (Launchpad, type Terminal), paste this line and press Enter:
  ```
  curl -fsSL https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/macos/get-javis.sh | bash
  ```

If you already downloaded the file with the browser and it was blocked:
- Windows shows "Windows protected your PC": click **More info**, then **Run anyway**.
- macOS says it cannot open the app: go to **System Settings → Privacy & Security**, scroll down, click **Open Anyway**, then open JAVIS OS again.

## Option 1 - Hostinger VPS (Docker Manager, one click)

> 🛒 **No VPS yet?** [Get a Hostinger VPS here](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN). Docker Manager comes built in, so Javis installs in one click. Once it is ready, come back to the steps below.

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

VPS on **Ubuntu 26** or a plain OS without Hostinger's Traefik: paste the same link, `DOMAIN_NAME` may stay empty: **Open** moves you to `https://javis.srvXXXX.hstgr.cloud` or `https://srvXXXX.hstgr.cloud` (since 0.302.0). **Settings → Domain** says whether the link works yet. The bundled `javis-gateway` container issues HTTPS for `DOMAIN_NAME` when ports 80/443 are free (since 0.300.0); open ports 80 and 443 in the firewall.

To update: press **⬆ Update now** in the app (Updates page), or **Redeploy** in Docker Manager (image `:latest`, `pull_policy: always`). Brain data stays in the volume.

## Option 2 - Docker on any machine or VPS

> 🛒 **Need a VPS?** A [Hostinger VPS](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN) runs this option too.

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

- **The in-app update button does not work on Hostinger**: it needs the bundled `javis-watchtower` container (included since 0.55.56). If the stack shows "Partially running", open that container's log; if it cannot be fixed, update with **Redeploy** in Docker Manager.
- **ChatGPT/Codex says "model not supported"**: pick a valid Codex model on the Models page (e.g. `gpt-5.5`). Do not use `gpt-5-mini` or `gpt-4o` - those are API models and a Codex account cannot run them.
- More: [docs/17 - Troubleshooting](docs/en/17-troubleshooting.md).
