<div align="center">

# 🧠 Javis OS

**A model-agnostic agentic AI layer + Second Brain - swap the brain (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Gemini, Anthropic API, Groq, Ollama) without losing tools: voice, a knowledge graph, MCP-driven business reporting, and a self-improvement loop.**

*[Tiếng Việt](README.md) · **English***

</div>

---

## What is Javis?

Javis OS is **not** a chatbot. It is a **self-hosted agentic AI** running on your own machine or VPS: it reads and writes files, calls tools (MCP), runs skills, queues background work, schedules itself - all wrapped in a **voice-controlled dashboard** with a **Second Brain** (memory + wiki) that accumulates knowledge over time.

**You pick the brain, and you can change it whenever you like.** Ten paths work today: **Claude Code**, **ChatGPT/Codex** and **Antigravity CLI** (these run on the subscription you already pay for - no separate API purchase), plus **Gemini CLI · OpenRouter · OpenAI API · Google Gemini · Anthropic API · Groq · Ollama Cloud** (an API key is all they need).

> ⚠️ **Read this before letting a subscription run background work.** Anthropic scopes Claude Pro/Max to **ordinary personal use** of Claude Code. Continuous background execution (loops, reminders, Kanban jobs, chatbots), running on a VPS, or several people sharing one account all fall outside that scope, and accounts **have been suspended** over it. Javis does not read your login token (that path was removed in 0.26.17) - it runs the `claude` binary itself, but that does not make round-the-clock background use legitimate either. If you want to be safe: on the **Models** page set Claude Code to run on an **API key**, or point the **background-work model** at a different provider. See `server/claude_auth.py`.

> ⚠️ **Gemini CLI no longer covers personal tiers.** Google cut personal Code Assist off on 18 June 2026. The CLI returns `IneligibleTierError` / `UNSUPPORTED_CLIENT` on the free tier, Google AI Pro and Ultra alike; only an enterprise Code Assist licence or an API key still works. That is a server-side block on Google's end, not a misconfiguration. For Gemini models on a personal Google plan, use **Antigravity CLI** instead - same model line-up as the Antigravity IDE, including non-Google models.

> The philosophy: **capability lives in Javis, not in the model.** Every brain gets the same toolbox through one shared connection hub (MCP Hub) - wired-up MCP servers, brain read/write tools, skills, Kanban jobs, agents, workflows, loops and reminders. The only real difference: the CLI engines can also run **shell commands**, fetch a URL, search the web and spawn sub-agents. Switching from Claude to Gemini costs you nothing beyond that.

You wire in **your own connections** (POS/sales, ads, calendar, email, Zalo, notes…) → Javis discovers them and **reports on your business and your life** with real numbers, in plain speech.

### What makes Javis different

| | An ordinary chatbot | **Javis OS** |
|---|---|---|
| Brain | Hard-wired to one model, one stateless API call per message | **Swappable**: 10 providers, each with the full set of tools, MCP, skills and sessions |
| Memory | Forgets after every session | **A living Second Brain** - remembers you, thickens with every conversation |
| Data | Made up, or absent | **Real numbers** from the connections you wire in (POS, Ads, Calendar, Zalo…) |
| Self-improvement | None | **Background loops** + an AI-run work queue |
| Interface | A chat box | Dashboard + knowledge graph + **hands-free voice** + Telegram |
| Deployment | Locked to one vendor | **Self-hosted**: Hostinger one-click / Docker / any VPS |

> 💡 **Philosophy:** Javis *compiles* knowledge once, from raw notes into a Wiki, then *maintains* it alive against every new source. Knowledge **accumulates** instead of being rediscovered each time.

---

## ✨ Highlights

- 🎙️ **Hands-free voice** - speak, and Javis listens and answers out loud. Pick your voice provider: Edge TTS (free, default), OpenAI or ElevenLabs.
- 🌌 **Knowledge graph** - your brain rendered as a network of notes joined by `[[wikilink]]`, on a light canvas that works offline.
- 💬 **Conversation sessions** - save, reopen and **full-text search** every past conversation; long sessions are compacted into summaries instead of having their memory truncated.
- 🗂️ **File manager** - browse, **edit `.md`/`.txt` right in the browser**, search files by name or by content, upload and download.
- 🧩 **Skills** - group, search, **toggle individually**, add/edit/delete, import/export as packages; Javis files new skills into the right group by itself.
- 🧰 **Plugins** - drop in a Python folder and every engine gains a **native tool or hook**, with no core changes.
- 🤖 **Agents & workflows** - build specialist assistants (each with its own memory) plus multi-step automation chains with verification steps.
- ♻️ **Recurring jobs & reminders** - several background loops in parallel, each doing exactly the one job you described and then checking its own work; plus reminders on a fixed time or a cron expression.
- 🗃️ **Work (Kanban)** - hand over a goal in plain words; the AI writes the spec, picks a worker, runs it in the background and only calls you on exceptions.
- 🧠 **Self-learning** - after each conversation Javis distils memories, wiki knowledge and skills; every learning pass is a git commit, so it is **one-tap undoable**.
- 🔌 **Multi-account connection store** - Pancake POS, Zalo, Meta/Google/TikTok Ads, Google Workspace, Slack, Webcake, Substack… several accounts per service, each with its own permission level, and Javis **hard-blocks** anything above that level.
- 📱 **Telegram & Zalo** - ask Javis over Telegram; read, search history and send Zalo messages through the standard `zalo-agent-cli` MCP.
- 🎨 **Image generation** on the ChatGPT plan you are already signed in to - no separate API key.
- 📊 **Usage** - Javis measures its own tokens in/out and cost per day and per provider, separating what you typed from what it ran on its own.
- ⇅ **Back the brain up to GitHub** - two-way sync of every brain to a private repo, shared between your home machine and a VPS.
- 🔄 **Multi-engine, no feature loss on a switch** - Claude Code, ChatGPT (Codex), Antigravity CLI, Gemini CLI, OpenRouter, OpenAI API, Google Gemini, Anthropic API, Groq, Ollama. Change it in **Models** with one click; every brain reaches the Javis MCP hub, the brain file tools and the skills.
- 🌐 **Multilingual** - reply language, interface language and locale are three separate settings. Vietnamese and English ship today; adding a language is a data change, not a code change (see [docs/dev/them-mot-ngon-ngu.md](docs/dev/them-mot-ngon-ngu.md)).
- 🔐 **Safe on a VPS** - login is forced automatically when running publicly, plus account-takeover protection, rate limiting, CSRF blocking and encrypted secrets in the config.

---

## 🚀 Installation

> ⚠️ **Security matters here:** Javis runs an AI brain with **full rights** on the machine. When it runs publicly (Docker/VPS/Hostinger), Javis **forces login by itself** - opening the app gives you a create-account / sign-in screen, and nobody drives it without a password.

### Option 1 - Hostinger Docker Manager (domain + HTTPS) ⚡

Hostinger VPS → **Docker Manager → Compose → URL** → paste the **Hostinger file** and **Deploy**:
```
https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
```
The **Environment** box on the current template needs only three fields: `DOMAIN_NAME`,
`JAVIS_ADMIN_USER`, `JAVIS_ADMIN_PASSWORD`. The technical variables for ports, state,
brains and working directories are hidden because the Docker image sets them correctly.

Set `DOMAIN_NAME` so Hostinger's Traefik issues HTTPS:
- **Free link** (no domain purchase needed): `DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud`
  (find the hostname under hPanel → VPS, e.g. `javis.srv1562015.hstgr.cloud`).
- **Your own domain:** `DOMAIN_NAME=example.com` + point an A record at the VPS IP.

Deploy → wait 1-3 minutes for Traefik to issue the certificate → open `https://<DOMAIN_NAME>`. (Details and troubleshooting: [DEPLOY.md](DEPLOY.md).)

> Just want `http://<ip>:7777` without a domain? Use `docker-compose.yml` (Option 2).

**Three one-time steps:**
1. **Make the GHCR image Public:** GitHub → repo → **Packages** → `javis-os` → *Package settings* → Visibility = **Public**.
2. **Create the admin account** (pick one):
   - *Recommended:* fill in `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` in the Environment box → open the app and **sign straight in**.
   - *Or:* open the app and it asks for a **SETUP TOKEN** - in the **App terminal** (inside the container) run `cat /data/state/.setup_token`.
3. **Sign in to a brain:** App terminal → `claude auth login --claudeai` → open the link, paste the code. (On a ChatGPT plan, sign in on the **Models** page after opening the app.)

### Option 2 - Docker on any VPS (pull the image, no clone needed)

```bash
# Docker required (don't have it?  curl -fsSL https://get.docker.com | sh)
mkdir javis && cd javis
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml

docker compose run --rm javis claude auth login --claudeai   # sign in to Claude once
docker compose up -d                                          # pull the image and run
```
Open `http://<vps-ip>:7777` → the admin-account screen (find the SETUP TOKEN in `docker compose logs javis`).

### Option 3 - Install directly on Linux/macOS (no Docker)

```bash
git clone https://github.com/blogminhquy/javis-os.git javis && cd javis
chmod +x install.sh && ./install.sh
```
The script installs Python + Node + both CLI engines (Claude Code, Codex), creates a venv, registers a systemd service that starts at boot, and prints the address. If it reports Claude is not signed in, run this once: `claude auth login --claudeai`.

### Option 4 - Windows (personal machine)

```
1. Install Python 3.12 (tick "Add to PATH") + Node.js LTS
2. Double-click  setup.bat   (runs in a visible window - installs Claude Code + Codex)
   To run it silently next time: start-javis.vbs   (log at server\javis.log)
3. Open http://localhost:7777 → the Models page, sign in to the brain you want
4. To stop: stop-javis.bat
```

> 🪟 **Windows - open it like an app:** after the first `setup.bat` run, from then on just double-click **`JAVIS OS.bat`** - the server starts in the background (no black window) and the dashboard opens as its **own window** with no address bar and its own taskbar entry. Start at login: `javis-autostart.bat install` (remove: `uninstall`).

### Several Javis instances on one VPS (each with its own link)

Run as many as you like - brains, settings and accounts are fully separate per instance.
Only three values have to differ between them: `JAVIS_NAME`, `JAVIS_HOST_PORT`, `DOMAIN_NAME`.

- **Hostinger:** deploy `docker-compose.hostinger.yml` as a second stack and fill in those three boxes.
- **Self-managed VPS:** run the shared proxy `docker-compose.proxy.yml` **once for the whole machine**, then give each instance its own folder using `docker-compose.multi.yml`. The proxy discovers new instances and requests SSL by itself - adding one changes nothing on the proxy.
- **Native:** `JAVIS_NAME=javis-shop JAVIS_PORT=7778 ./install.sh`.

Leave those variables empty and you get exactly the old single-instance install. Step by step: **[DEPLOY.md](DEPLOY.md)**.

📄 More detail (fixed named-tunnel URLs, building from source…) in **[DEPLOY.md](DEPLOY.md)**.

---

## 🎬 First-run setup

Open Javis and the setup wizard walks you through:

1. **Admin account** - set a password (required when running publicly, to keep strangers out).
2. **Pick a brain** - on a subscription you sign in once and need no API key: Claude Code keeps its token in `~/.claude` (Docker: a dedicated volume, so updates do not lose it), and ChatGPT/Codex signs in right on the **Models** page. On an API key you just paste an OpenRouter / OpenAI / Gemini / Anthropic key. The Claude Code card also has a **"Run via"** selector: keep the signed-in subscription, or switch to an Anthropic API key. Both keep every capability - they differ only in who pays and who carries the risk (see the warning above).
3. **Pick a model** - Claude Code is preselected, but switching to any provider on the **Models** page **loses no features** (except shell commands, which only the CLI engines have).
4. **Wire up connections** (optional) - go to **Connections**, pick a service from the store and paste a key or scan a QR code. Javis then reports on real numbers from it.

---

## 📖 Using Javis

> 📚 **Detailed docs:** see the **[docs/](docs/README.md)** folder - a guide per feature (where to open it, what to press, how to use it). Most pages are in Vietnamese; [docs/en/](docs/en/README.md) has the translated ones. The table below is a quick map.

The left navigation rail groups **19 pages** into **7 groups** (click a group name to open it):

| Group | Item | What it does | Guide |
|---|---|---|---|
| **Assistant** | **Javis** | The main screen: chat (typed or spoken), knowledge graph, brain file tree on the left. | [Chat & voice](docs/02-tro-chuyen-va-giong-noi.md) · [Knowledge graph](docs/03-do-thi-tri-thuc.md) |
| | **Chat** | A full-width chat pane with a conversation-history column. | [Sessions](docs/04-phien-hoi-thoai.md) |
| **Brain** | **Files** | Browse the brain, **edit `.md`/`.txt` in place**, search by name or content, upload and download. | [File manager](docs/05-quan-ly-tep-tin.md) |
| | **Self-learning** | Javis distils memories, wiki entries and skills after each conversation; undoable. | [Self-learning](docs/22-tu-hoc.md) |
| **Code** | **Terminal** | A **real shell** on the machine running Javis, right in the browser - no SSH needed. | [Code group: Terminal](docs/27-tab-code-terminal.md) |
| **Capabilities** | **Agents** | Build specialist assistants (role + skills + their own memory). | [Agents & workflows](docs/07-agents-va-workflows.md) |
| | **Skills** | Group, search, **toggle**, add/edit/delete, import/export skills. | [Skills](docs/06-skills.md) |
| | **Workflows** | Build and run automation chains (agent → agent) with verification steps. | [Agents & workflows](docs/07-agents-va-workflows.md) |
| | **Plugins** | Add native tools/hooks for every engine with one Python folder. | [Plugins](docs/20-plugins.md) |
| | **Chatbot** | Put an agent in front of customers on its own Telegram/Zalo bot and its own brain. | [Chatbot](docs/25-chatbot.md) |
| **Work** | **Work** | A background task queue the AI specs and runs itself; you only handle exceptions. | [Work (Kanban)](docs/21-viec-kanban.md) |
| | **Recurring** | Several background loops plus reminders on a clock time or a cron expression. | [Recurring jobs & reminders](docs/08-viec-dinh-ky.md) |
| **Connections** | **Connections** | The external-service store, several accounts per service, three permission levels. | [Connections & data](docs/09-mcp-va-so-lieu.md) |
| | **Channels** | Turn on the Telegram bot (ask Javis from your phone). | [Telegram](docs/11-telegram.md) · [Zalo](docs/12-zalo.md) |
| | *(terminal)* | `pip install javis-cli`, then `javis "..."` - a third channel into the same Javis. | [Javis CLI](docs/24-cli-terminal.md) |
| | **Models** | Main model, providers, reasoning depth, background-work model. | [Models & engines](docs/10-models-va-engine.md) |
| **System** | **Usage** | Tokens and cost per day, per provider, per source. | [Usage](docs/23-muc-dung-token.md) |
| | **Settings** | System status, interface & brain, voice, branding, custom domain. | [Getting started](docs/en/01-getting-started.md) |
| | **Updates** | Current version, update/Redeploy, progress and the feature changelog. | [Troubleshooting](docs/17-khac-phuc-su-co.md) |
| | **Account** | Workspace, sign in/out, change or disable the password, API tokens for the CLI. | [Security & accounts](docs/14-bao-mat-tai-khoan.md) · [Javis CLI](docs/24-cli-terminal.md) |

**Full table of contents (27 pages):** [docs/README.md](docs/README.md) - it also covers [Second Brain: memory / Wiki / INGEST](docs/13-second-brain-bo-nho-wiki.md), [Backing the brain up to GitHub](docs/18-sao-luu-github.md), [Tasks & Dataview in notes](docs/19-task-va-dataview.md), [Branding & custom domains](docs/15-thuong-hieu-ten-mien.md) and [.env configuration](docs/16-cau-hinh-env.md).

### A few common flows

- **Ask for numbers:** *"How is revenue today? Against yesterday?"* → Javis calls the right connection and returns real figures plus suggestions.
- **Digest knowledge (INGEST):** drop in a file or a note → Javis summarises it, extracts insight, writes it into the Wiki and proposes tasks.
- **Hand over background work:** go to **Work** → **+ New goal** → describe it in plain words (e.g. *"summarise this week's sales, find slow-moving stock, draft three captions to push it"*) → the AI specs and runs it, then reports back over Telegram.
- **Recurring work:** go to **Recurring** → **+ Add** → choose *Loop* (every N minutes) or *Reminder* (8:30 every day).
- **Voice:** press the mic (or turn on hands-free) → speak → Javis answers out loud.

---

## ⚙️ Configuration (`.env`)

Every line can be left empty and it still runs. Copy `env.example` → `.env` (the sample file deliberately has no leading dot, so Hostinger's Docker Manager does not import it into the Environment box).

| Variable | Meaning | Default |
|---|---|---|
| `JAVIS_HOST` | Listen address. `127.0.0.1`=this machine only; `0.0.0.0`=public | `127.0.0.1` |
| `JAVIS_PORT` | Port | `7777` |
| `JAVIS_REQUIRE_LOGIN` | `1`/`0` to force login on/off (default: on when bound publicly) | *(auto)* |
| `JAVIS_ADMIN_USER` / `JAVIS_ADMIN_PASSWORD` | Create the admin at deploy time (no SETUP TOKEN needed) | - |
| `JAVIS_ALLOWED_HOSTS` | Extra hostnames on the allow-list (CSRF / DNS-rebinding protection) | localhost + your domain |
| `JAVIS_SECURE_COOKIE` | Force the `Secure` cookie flag. Only turn on with end-to-end HTTPS | *(auto, from the domain)* |
| `JAVIS_STATE_DIR` | Where state is written (settings, sessions, encryption key, recurring-job config) | `server/` (Docker: `/data/state`) |
| `BRAINS_DIR` | Parent folder holding every brain | `brains/` (Docker: `/brains`) |
| `OBSIDIAN_VAULT_PATH` | An external Second Brain vault (if you already have one) | `vault/` (Docker: `/data/vault`) |
| `CLAUDE_CWD` | Working directory for the Claude brain | repo root |
| `JAVIS_ENABLE_USER_PLUGINS` | `true` is required before your own plugins run (real Python inside the server) | *(off)* |
| `WATCHTOWER_TOKEN` | Token for the "Update now" button on the Docker build | `javis-update` |
| `TTS_VOICE` / `TTS_RATE` | Voice and speed (Edge TTS) | `vi-VN-HoaiMyNeural` / `+5%` |

Every variable: [docs/16 - .env configuration](docs/16-cau-hinh-env.md).

---

## 🔐 Security

- When running publicly, **login is required** before any feature works (the brain runs with full rights on the machine).
- Creating the first admin needs a **SETUP TOKEN** (printed in the server log) or an admin preset through env vars → someone who only has the URL cannot claim the account.
- **Login rate limiting** (temporary lockout after repeated failures), passwords ≥ 8 characters, `secure` cookies under HTTPS, sessions expiring after 30 days.
- **CSRF and DNS-rebinding blocked**: any write request with an unknown Origin is rejected.
- **Secrets are encrypted** inside `settings.json` (API keys, OAuth tokens, Telegram bot tokens, backup tokens) with a per-machine key at `JAVIS_STATE_DIR/.secret_key`.
- **Your own plugins are blocked by default** - you have to set `JAVIS_ENABLE_USER_PLUGINS=true` yourself, because they run real Python inside the server process.
- Remote access should go over **HTTPS** (Hostinger `*.hstgr.cloud` or a Cloudflare Tunnel) - do not expose a raw port.

---

## 🔄 Updating

```bash
# On your machine (after changing code): push to GitHub
git add -A && git commit -m "..." && git push     # → CI builds a new image onto GHCR

# On the VPS: pull the new build
cd javis && ./update.sh          # pulls the image and restarts (volume data is NOT lost)
```

In the app: open **Updates** (System group) → **⬆ Update now** where the environment supports it, with a progress bar and a rollback button if the new build breaks.

## 🌐 Remote access (non-Hostinger VPS)

```bash
docker compose --profile tunnel up -d
docker compose logs tunnel | grep trycloudflare   # → https://xxx.trycloudflare.com
```

---

## 🏗️ Architecture

```
Browser (voice + graph) ───┐                        ┌→ Claude Agent SDK   (Claude plan)
Telegram ──────────────────┤→ FastAPI (server/) ────┼→ Codex CLI          (ChatGPT plan)
Zalo Agent MCP ────────────┤          │             ├→ Antigravity CLI    (Google plan)
                           │          │             └→ OpenRouter / OpenAI / Gemini / Anthropic / Groq / Ollama
                           │          ├→ MCP Hub  (the shared connection store for EVERY engine)
                           └──────────┴→ Second Brain (markdown vault: Memory + Wiki + Sources)
```
- **Backend:** Python FastAPI in `server/`.
  - Brains and engines: `claude_sdk_engine.py` (the Claude engine, via the Claude Agent SDK), `claude_cli.py` (factory + auth for Claude/Codex), `antigravity_cli.py`, `gemini_cli.py`, `engine.py` (the API engines plus the MCP tool-call loop), `aux_engine.py` (engine selection for background work + the fallback chain when an engine dies).
  - Tools: `mcp_hub.py`, `mcp_store.py`, `mcp_client.py`, `mcp_catalog.py`, `plugins_host.py`, `oauth_mcp.py`.
  - Background work: `self_improve.py` (recurring jobs), `reminders.py`, `tasks.py` + `task_store.py` (Kanban), `learn.py` (self-learning).
  - Data: `sessions.py`, `compaction.py`, `git_brain.py`, `media_gc.py`, `usage_index.py` + `usage_store.py`.
  - Channels: `telegram_bot.py`, `channel_context.py`; Zalo goes through the MCP Hub.
  - Language and locale: `lang.py` (which language is this turn), `lang_registry.py` (one entry per language), `lexicon/` (per-language safety-gate vocabulary), `localefmt.py` (timezone, currency, formats).
  - Platform: `main.py`, `routes/` (domain, graph), `config.py`, `web_security.py`, `secrets_store.py`.
- **Frontend:** plain HTML/CSS/JS (`dashboard/`) - no framework, light on a VPS. Interface strings live in `dashboard/i18n/`.
- **Second Brain:** a markdown vault in `brains/<brain name>/` - living memory plus an accumulating Wiki.

---

## 🩺 Troubleshooting

| Symptom | What to do |
|---|---|
| Code changed but nothing looks different | Changed a `.py`? **Restart the server** (Windows: `stop-javis.bat` → `start-javis.vbs`). Changed the UI? **Ctrl+Shift+R**. |
| Port 7777 held, the new build will not come up | Kill the old process FIRST (`stop-javis.bat`, or `taskkill /F /PID <pid>`), then start again. |
| Hostinger cannot pull the image | Set the GHCR package to **Public**; wait for the GitHub Action build to finish (Actions tab). |
| The app asks for a SETUP TOKEN | App terminal (inside the container): `cat /data/state/.setup_token`. On the host: `docker compose logs javis \| grep "SETUP TOKEN"`. Or set `JAVIS_ADMIN_PASSWORD` so no token is needed. |
| The brain says it is not signed in | Go to **Models**, find the provider card, press sign in. Or run `claude auth login --claudeai` once (Docker: in the App terminal). |
| Old images in a conversation show a grey box | By design: `attachments/` is a cache that expires after 30 days or 300MB. See [Troubleshooting](docs/17-khac-phuc-su-co.md). |

---

## 📂 Repository layout

```
javis-os/
├── server/              # FastAPI backend (engines, connections, background work, channels, memory…)
│   └── routes/          # Split-out routes (domain, graph)
├── dashboard/           # Frontend (voice, graph, console, studio, usage)
│   └── i18n/            # Interface string catalogues, one JSON per language
├── brains/              # ALL second brains (default: brains/Brain Default)
├── system/              # Ships with the app: bundled plugins, system skills, the connection catalogue
├── tests/               # Python + JS test suite
├── website/             # Marketing site
├── docs/                # Detailed user guides (27 pages + index)
├── Dockerfile           # Image: python + Node + Claude CLI
├── docker-compose.yml   # Production (pulls the GHCR image) - plain VPS, reachable at http://<ip>:7777
├── docker-compose.hostinger.yml  # For Hostinger: domain + HTTPS via Traefik (set DOMAIN_NAME)
├── docker-compose.https.yml      # Auto-HTTPS via Caddy on a plain VPS (used with the file above)
├── install.sh           # Native install for Linux/macOS
├── update.sh            # Update on a VPS
├── env.example          # Environment variable template
├── VERSION · CHANGELOG.md
├── QUICKSTART.md        # Quick start (Vietnamese) · QUICKSTART.en.md (English)
├── DEPLOY.md            # Detailed deployment guide
└── CLAUDE.md            # The "system prompt" + conventions for AI agents
```

---

## 🙏 Credits

- **Brains:** [Claude Code](https://claude.com/claude-code) and the [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) (Anthropic), [Codex CLI](https://developers.openai.com/codex/cli) (OpenAI), [Antigravity](https://antigravity.google) (Google), plus the APIs of [OpenRouter](https://openrouter.ai), OpenAI, [Google Gemini](https://ai.google.dev), Anthropic, [Groq](https://groq.com) and [Ollama](https://ollama.com).
- **Tool standard:** [Model Context Protocol](https://modelcontextprotocol.io) - the entire Javis connection store runs on it.
- The Second Brain and digital Bullet Journal patterns.

---

## 📄 License

Open source under the **MIT License** - use, modify and distribute freely, just keep the copyright notice. See [LICENSE](LICENSE).

---

## ☕ Support Javis OS

Javis OS is open-source and free to use, and it's still just one person (me) writing the code and covering the test server bills every day. If Javis has been useful for your work or your life, a small donation buys me more time to fix bugs and ship new features instead of worrying about server costs.

No obligation, no perks attached - just a thank-you sent as money to someone quietly coding at night.

- 🏦 **MB Bank** (Vietnam): `6636966369`
- 📱 **MoMo wallet** (Vietnam): `0372752740`
- 🌍 **PayPal**: [paypal.me/quy01](https://paypal.me/quy01)

Can't donate? No worries - using Javis, sending feedback, or opening a Pull Request counts as support too.

---

<div align="center">

Made with ☕ by **[Minh Quý](https://minhquy.vn)** · Repo: `github.com/blogminhquy/javis-os`

</div>
