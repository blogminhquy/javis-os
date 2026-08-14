# Getting started & first-run setup

*[Tiếng Việt](../01-bat-dau-thiet-lap.md) · **English***

This page takes you from opening Javis for the first time to Javis being ready to talk: creating an admin account, choosing the AI provider that acts as the "brain", picking a model, and checking system status on the Settings page.

## What this covers

Javis OS is an AI operating layer that runs on your own machine or VPS. The brain is whichever AI provider you wire in: Claude Code, ChatGPT (through Codex), Antigravity CLI, OpenRouter, OpenAI API, Anthropic API, Google Gemini, Groq or Ollama Cloud. The first-run wizard **preselects** Claude Code because that is the recommended choice, but Javis is not locked to any provider.

Before it is usable, Javis needs three things:

1. An admin account (to keep strangers out - required when running publicly on a VPS).
2. An AI provider that is signed in or has an API key pasted in.
3. A main model to answer conversations.

The first time you open the app, a wizard appears and walks you through exactly those three. Everything set here can be changed later on the management pages.

## Where to find it

- On a personal machine, open a browser at `http://localhost:7777` (7777 is the default port).
- On a VPS or Docker, use the address your provider gave you, e.g. `http://<vps-ip>:7777` or an HTTPS link like `https://<app>.<vps>.hstgr.cloud`.

Once setup is done, the related items sit on the navigation rail on the left. The rail has 7 groups, and **you have to open a group before its items appear**:

| Group | Item | Used for |
|---|---|---|
| Connections | **Models** | Change the main model, sign providers in and out (see [Models & engines](../10-models-va-engine.md)) |
| System | **Settings** | Four collapsible config groups: system status, interface & brain, voice/branding, start with Windows |
| System | **Updates** | The running version, the update button, progress and the version changelog |
| System | **Account** | Change the password, sign out, disable login (see [Security & accounts](../14-bao-mat-tai-khoan.md)) |

## Step by step

### Step 1: Open the app and meet the wizard

Open `http://localhost:7777` (or your VPS address). If this is the first run and no account exists, Javis shows a **Welcome to Javis** window with three numbered sections.

On a personal machine (localhost), the password and SETUP TOKEN fields are optional and can be left empty. When running publicly (VPS/Docker), Javis requires both a password and a SETUP TOKEN before letting you through; a prompt then appears under the button explaining that an account, a password of at least 8 characters and the SETUP TOKEN are needed to protect Javis on a public server.

### Step 2: Name the workspace

Under **1. Workspace**, type a display name in the **Display name** box (your shop name or your own name, for instance). Left empty, Javis uses "Javis OS". It is only a label and can be changed at any time.

### Step 3: Create the admin account (and the SETUP TOKEN if needed)

Under **2. Admin account**:

1. Type a username in the **Username** box (it suggests `admin`).
2. Type a password in the **Password** box. It must be at least 8 characters.
3. If Javis is running publicly, a **Setup token** box appears. Paste the SETUP TOKEN there (see "When you need a SETUP TOKEN" below for how to get one).

On a personal machine, leaving the password empty means Javis creates no account and anyone who can open the link on this machine can use it. Only do that when you are the only person on the machine.

### Step 4: Choose the AI provider (the brain)

Under **3. AI provider (brain)**, pick one of three cards:

| Choice | Text on the card | What it needs |
|---|---|---|
| **🧠 Claude Code** (preselected) | "Sign in with a Claude subscription → full MCP, skills, file read/write, self-improvement loops. The strongest, most complete option." | One sign-in with a Claude subscription (no API key) |
| **💬 ChatGPT (subscription)** | "Sign in with ChatGPT Plus/Pro (through Codex) → still reaches every Javis MCP." | Sign in to ChatGPT on the Models page |
| **🌐 OpenRouter** | "Many cheap models in one place, still with full Javis MCP + skills + brain file access. Only needs an API key - no sign-in." | Paste an OpenRouter API key (now or later on Models) |

Any of the three gives you a fully capable Javis: all of them reach the connection store (MCP), read and write files in the brain, run skills, queue work and create loops. The only difference is **running shell commands**, which only the CLI engines (Claude Code, Codex, Antigravity CLI) can do. The wizard shows three cards for brevity; the **Models** page also has OpenAI API, Google Gemini, Anthropic API, Groq and Ollama, and you can change at any time.

Pick **OpenRouter** and an **OpenRouter API key** box appears - paste the key now or leave it empty and paste it later on the Models page. Below the list is a hint line that changes with your choice; picking ChatGPT, for example, suggests "Once inside: **Models** → sign in to ChatGPT".

Press **Start using Javis →** to save and enter the app. The wizard also sets a default model for the provider you chose: `sonnet` for Claude Code, `gpt-5.5` for ChatGPT, `openai/gpt-4o-mini` for OpenRouter. Change it on the Models page whenever you like.

### Step 5: Sign in to Claude as the brain

This is the important step if you chose Claude Code. The wizard only saves the provider choice; signing in to Claude happens on the **Models** page (**Connections** group):

1. Open **Models** on the left rail.
2. Find the **Anthropic OAuth (Claude Code)** card. It starts at "○ Not signed in".
3. Press **Sign in to Claude**.
4. Javis shows a link. Open it (in a new tab) and sign in at claude.ai.
5. If the page shows a code afterwards, paste it into the **paste code (if any)** box and press **Send code**. Some flows need no code; Javis re-checks status every 3 seconds and updates the card.
6. When it is done, the card reads "● Connected" (with the email/plan when available).

This is a device-code flow: no API key required. It works on a headless VPS. If you have terminal access to the server you can instead sign in once with `claude auth login --claudeai`.

The **↻ Re-check** button on the card reloads the sign-in status at any time. **Disconnect** signs Claude out of Javis.

The Javis Claude engine runs through the **Claude Agent SDK**, but the SDK still calls the `claude` CLI on the machine, so the machine running Javis must have `claude` installed for sign-in and native MCP to work.

### Step 6: Choose the main model and the background-work model

Once signed in, check and choose models on the **Models** page:

- **◆ Main Model** shows the model used for conversations. Press **Change model ▾** to pick another.
- **◆ Providers** lists all providers: Anthropic OAuth (Claude Code), OpenAI OAuth (ChatGPT), Google Antigravity CLI, Google Gemini CLI, OpenRouter, Anthropic (API), OpenAI (ChatGPT API), Google Gemini (API), Groq (API) and Ollama Cloud. Cards that need a key have a key box and **Connect** / **Change key** / **Disconnect** buttons.
- **◆ Background-work model** (subtitled "loops · Kanban work · reminders · self-learning · source ingestion") lets you pick a cheap model for background work to spare your quota. Until you change it, the status line reads "Claude Code default". Press **Change model ▾** to pick, **Reset to default** to undo. Choosing a provider that is not connected shows "⚠ this provider is not connected - background work will fall back to Claude".
- **◆ Reasoning** sets how deeply it thinks before answering: **Off**, **Low**, **Medium**, **High**. The default is Off (fast answers).

Background work runs on API providers too, not just Claude. The real difference is elsewhere: Claude Code and Codex read and write files directly in the brain and can run shell commands, while API models read and write through the Javis vault tools and cannot run shell commands - which suits reading, summarising and note-writing.

Full detail on each provider and model: [Models & engines](../10-models-va-engine.md).

## The Settings page: four config groups

Open **Settings** (**System** group on the rail). The page splits into four collapsible groups; click a heading to open or close it.

### Group 1: System

Subtitle: "Current status and shortcuts into the deeper groups". Four status boxes:

| Box | Tells you |
|---|---|
| **Engine** | The provider label behind the main model, e.g. "Anthropic OAuth (Claude Code)", "OpenRouter", "Google Gemini (API)" |
| **Model** | The main model in use, or "Default" |
| **Workspace** | The workspace name you set in the wizard |
| **Telegram** | "On" or "Off" (see [Telegram](../11-telegram.md)) |

Below are four shortcuts that jump straight to the matching page: **Models**, **Channels**, **Account**, **Updates**.

### Group 2: Interface & Brain

Subtitle: "Graph performance and data structure". Three cards.

**The Brain graph card** tells you whether the knowledge graph is on or off.

- Press **Turn graph off** to cut load to a minimum; while off, the button becomes **Turn graph on**.
- On a narrow screen (under 860px, i.e. a phone), Javis enters light mode automatically: the graph stops even with the switch on. The app still opens on the Javis screen as it does on a desktop - that screen already has the chat box, it simply does not draw the brain canvas.

Graph detail: [Knowledge graph](../03-do-thi-tri-thuc.md).

**The Normalise brain card** collects the `agents`, `workflows`, `memory` and `skills` folders of the selected brain into one flat structure. Press **Normalise the selected brain** to run it.

It is safe: it only moves when the destination does not exist, it never overwrites, and running it repeatedly is harmless (for example moving `Javis/agents` to `agents`, `Memory` to `memory`). Afterwards Javis reports what it moved, or "Nothing to move (already normalised)".

**The AI image provenance card** decides whether images Javis generates carry a provenance mark (Content Credentials, the C2PA standard). The corner label reads "Keeping" or "Stripping".

- The default is **Keep the mark**: images carry a record that they were AI-generated. Facebook reads it and labels posts "AI-generated content".
- Press **Strip the mark** and new images no longer carry it, so platforms usually stop showing the label. Images generated earlier are unchanged.
- Either way the `javisos.com` author tag stays, and you remain responsible for disclosing AI content under the law and the terms of whatever platform you post to.

### Group 3: Voice, branding & access

Subtitle: "TTS, avatar and custom domain". This holds the **⚙ QUICK SETTINGS** block:

- The **🔊 Read answers aloud** switch.
- The **VOICE PROVIDER** block: choose "Edge TTS - free (default)", "OpenAI - smooth, multilingual" or "ElevenLabs - most natural", paste the matching key and press **Save provider**. A paid provider that errors falls back to Edge.
- **LISTENING LANGUAGE** (Vietnamese `vi-VN` or English `en-US`), **VOICE (Edge)**, **SPEED** and a **▶ Preview** button. The Edge voice block only appears when the provider is Edge.
- **AVATAR**: **Upload an image** or **Restore default**.
- **DOMAIN & SSL**: enter a domain, press **Save & check**, watch the `DNS:` and `SSL:` labels, then **Enable SSL** or **Re-check**.

Detail: [Chat & voice](../02-tro-chuyen-va-giong-noi.md) and [Branding & domains](../15-thuong-hieu-ten-mien.md).

### Group 4: Start with Windows

This group **only appears on the Windows build**; the Docker/Linux build hides it entirely. The **Auto-start Javis** card shows the state ("On" or "Off") and has a single button: **Enable auto-start** or **Disable auto-start**. When on, Javis runs in the background as soon as you sign in to Windows, and `localhost:7777` is ready.

#### When the card says "On but not running"

If you boot the machine and `localhost:7777` reports **ERR_CONNECTION_REFUSED**, reopen this page. Javis checks three causes and writes the cause straight under the card, because none of the three leaves an error anywhere:

- **Windows is blocking this startup entry.** In Task Manager's **Startup** tab, pressing Disable deletes nothing - it just sets a flag telling Windows to skip the entry. Plenty of "clean up your PC, speed up boot" tools set the same flag without asking. Pressing **Enable auto-start** again clears it.
- **The install folder moved** and the startup command still points at the old path. Press enable again to update it.
- **`start-javis.vbs` or `.venv\Scripts\python.exe` is missing.** Run `setup.bat` again to rebuild what is missing.

If the card says **On** with no warning and boot still does not bring it up, open `server\javis.log` in the install folder: that is where the server records errors when it does start but dies part-way.

For the Second Brain (memory, Wiki, vault structure), see [Second Brain: memory, Wiki, INGEST](../13-second-brain-bo-nho-wiki.md).

## Updating the version

This lives under **Updates** (**System** group). The Javis OS panel at the top shows the running version and whether a newer one exists on GitHub.

- A new version: "🆕 New version **v...** available (running v...)" with an environment label (`Windows`, `Linux`, `macOS` or `Docker / VPS`), and a "What's new" block listing up to the two most recent releases.
- Already current: "✅ Running the latest version (v...)".
- Press **Re-check** to compare against the latest at any time.

### When the "⬆ Update now" button appears

**⬆ Update now** only appears when Javis can update itself in place. Javis does not guess from the provider name: it **actually probes** for a listening Watchtower container.

| How you run it | One-tap update? |
|---|---|
| Windows | Yes |
| Linux / macOS, run directly | Yes |
| Docker with Watchtower running | Yes |
| Docker without Watchtower | No; the panel says why and how to enable it |

**Why one machine has the button and another does not.** Almost always because Watchtower sits inside `profiles: ["update"]` in `docker-compose.yml`, so the habitual `docker compose up -d` **does not start it**. Enable it once, in the folder holding the compose file:

```bash
docker compose --profile update up -d
```

Reload the page and the button appears. If you would rather not enable it, updating by hand still works: `docker compose up -d --pull always`.

The **Hostinger stack** (`docker-compose.hostinger.yml`) deliberately omits Watchtower - it cannot reach the Docker socket there, so running it just loops on errors. Hostinger machines update via **Redeploy** in Docker Manager; there is nothing extra to enable.

The Updates panel distinguishes these two cases and prints the right procedure for your machine.

### The six-step progress bar

Press **⬆ Update now** and Javis asks to confirm ("Update Javis to the latest version? The app will restart; on failure the system will try to roll back."). Once you agree, a progress bar lights up through six steps:

**Prepare → Download code → Install dependencies → Restart → Health check → Done**

The running step shows ⏳, finished steps show ✅. During the run the status line reads "⏳ Updating… do not close this page." If the local source has local modifications, Javis reports "📦 Local changes stashed in git." (stashed, not deleted). When it finishes you get "✅ Update complete. Reloading…" and the app reloads after about 1.5 seconds.

### When the new build is broken: rolling back

Javis keeps a way back and will not strand you on a broken build:

- **Automatic rollback:** if the new build fails the health check, Javis returns to the old one. The progress bar shows "↩ New build failed, rolling back…", then "↩ New build failed, **rolled back automatically**."
- **Manual rollback on Docker:** if the version still has not changed after a while, Javis reports "⚠ The new build has not come up - it may have failed." and shows a **How to roll back on Docker** block with `docker compose pull && docker compose up -d`, plus a hint to pin `ghcr.io/blogminhquy/javis-os:<old-version>` and Redeploy.
- **Other errors:** the panel names the specific error and points at `update.log`. If the server does not come back within roughly 3 minutes, the panel says "The server has not come back after about 3 minutes - try reloading the page."

Below the update panel is the version changelog: what each release added, paginated, with the installed version marked.

## When you need a SETUP TOKEN, and where to get it

A **SETUP TOKEN** only appears when Javis runs publicly (listening on `0.0.0.0`, i.e. VPS/Docker/Hostinger) and has no admin account yet. Because the brain runs with full rights on the machine at that point, Javis will not let anyone who merely has the link create the admin account. The SETUP TOKEN is a secret string printed only to the server log/terminal, so only someone with server access can read it.

On a personal machine (localhost), Javis never asks for it.

How to get it:

| Situation | Command |
|---|---|
| Hostinger, in the App terminal (inside the `javis` container) | `cat /data/state/.setup_token` |
| SSH into the Docker host | `docker compose logs javis`, then look for the `SETUP TOKEN` line |

Paste it into the **Setup token** box in the wizard and press **Start using Javis →**. The token is single-use; Javis deletes it once the account is created.

**How to skip the token entirely:** set the environment variables `JAVIS_ADMIN_USER` and `JAVIS_ADMIN_PASSWORD` at deploy time. Javis creates the admin at startup, and opening the app gives you a sign-in screen with no token prompt. Details: [.env configuration](../16-cau-hinh-env.md).

## Quick reference: buttons and states

| Button / label | Where | What it does |
|---|---|---|
| **Start using Javis →** | Wizard | Saves the workspace, account and provider, then enters the app |
| **Sign in to Claude** | Models, Anthropic OAuth (Claude Code) card | Starts the device-code flow and shows the claude.ai link |
| **Send code** | Models, after pressing Sign in to Claude | Submits the code taken from claude.ai |
| **↻ Re-check** | Models, Claude Code card | Reloads the sign-in status |
| **Disconnect** | Models | Signs the provider out of Javis |
| **Change model ▾** | Models, Main Model and Background-work model | Opens the model picker |
| **Reset to default** | Models, Background-work model | Returns background work to the Claude Code default |
| "○ Not signed in" / "● Connected" | Models | Provider status |
| **Turn graph on** / **Turn graph off** | Settings, Brain graph card | Enables or disables the knowledge graph |
| **Normalise the selected brain** | Settings, Normalise brain card | Flattens the brain folder structure |
| **Keep the mark** / **Strip the mark** | Settings, AI image provenance card | Toggles the C2PA mark on generated images |
| **Enable auto-start** / **Disable auto-start** | Settings, Start with Windows | Runs Javis in the background at Windows sign-in |
| **Re-check** | Updates | Compares the version against GitHub |
| **⬆ Update now** | Updates (only when self-update is possible) | Runs the six-step update, then reloads |

## Tips

- If you only run this on a personal machine and are not worried about strangers, leave the wizard password empty for a fast entry. You can set one later on the **Account** page.
- If the app reports Claude is not signed in after you get in, go back to **Models** and press **Sign in to Claude** once.
- Avatar, domain, voice and speed live under **Settings → Voice, branding & access**, not in the first-run wizard.
- If the interface does not change after a version update, press Ctrl+Shift+R for a clean reload.
- Pick a cheap **Background-work model** from the start: loops, Kanban work, reminders, self-learning and source ingestion run a lot, and leaving them on an expensive model burns quota fast. Watch the real figures on the [Usage](../23-muc-dung-token.md) page.

## Common problems

- **The app wants a SETUP TOKEN and you do not know where to get it:** in the App terminal (Hostinger) run `cat /data/state/.setup_token`, or on the host run `docker compose logs javis` and look for `SETUP TOKEN`. Or preset `JAVIS_ADMIN_PASSWORD` so no token is needed.
- **"Wrong or missing SETUP TOKEN":** the pasted token is wrong or absent. Fetch the correct one from the server log and paste again, watching for stray whitespace.
- **"Password must be at least 8 characters":** use a password of 8 characters or more.
- **"An account already exists - please sign in":** an admin was created earlier (through env vars, for instance). Use the sign-in screen with those credentials.
- **Claude reports it is not signed in:** go to **Models**, press **Sign in to Claude**, open the link, paste the code if asked. Or run `claude auth login --claudeai` in the server terminal.
- **Forgot the admin password:** press "Forgot password?" on the sign-in screen for instructions. The procedure is to open `server/settings.json`, delete the `"auth"` block (or empty it), and restart the server; reopening the app returns you to the wizard to create a new account. See [Security & accounts](../14-bao-mat-tai-khoan.md).
- **Too many failed sign-ins, "Too many attempts":** Javis locks temporarily to stop password guessing. Wait a few minutes and try again.
- **Update says "Already updating, hold on.":** another update is in flight. Wait for it to finish and try again.
- **No "⬆ Update now" button:** you are on Docker without Watchtower running. The Updates panel says exactly what your machine is missing. On a self-managed VPS run `docker compose --profile update up -d` once and reload - the habitual `docker compose up -d` does NOT start Watchtower because it sits in its own profile. On Hostinger it cannot be enabled; use Redeploy.
- **The port is right but nothing loads:** check that the address really is `http://localhost:7777` (or the VPS IP with port 7777). If you just changed code, restart the server and try again.

Still stuck? See [Troubleshooting & FAQ](../17-khac-phuc-su-co.md).

## Related

- [Chat & voice](../02-tro-chuyen-va-giong-noi.md) - the first thing to do once setup is done.
- [Models & engines](../10-models-va-engine.md) - every provider in detail and how to change model.
- [Connections & business data](../09-mcp-va-so-lieu.md) - wire data sources into the **Connections** page.
- [Plugins](../20-plugins.md) - add native tools for every engine.
- [Work / Kanban](../21-viec-kanban.md) - hand over one-off background work.
- [Recurring jobs & reminders](../08-viec-dinh-ky.md) - repeating work and clock-time reminders.
- [Self-learning](../22-tu-hoc.md) - consolidate memory and audit Wiki health.
- [Usage: tokens & cost](../23-muc-dung-token.md) - what you spent per day and per provider.
- [Security & accounts](../14-bao-mat-tai-khoan.md) - lock access down before going to a VPS.
