# Troubleshooting and FAQ

*[Tiếng Việt](../17-khac-phuc-su-co.md) · **English***

This page gathers the problems people hit most often with Javis OS and how to work through each one. Most of them need only one of two actions: restart the server, or reload the browser with Ctrl+Shift+R. A short FAQ closes the page.

If you have just installed Javis for the first time, read [Getting started and first setup](01-getting-started.md) first. If you are editing environment variables, see [.env configuration](16-env-configuration.md).

## Before you read on: the two rescue actions used most

A great many errors disappear after one of these, so try them before worrying:

1. **Restart the server (when you or an update just changed Python `.py` code).**
   - On **Windows**: run `stop-javis.bat` to stop it, then `start-javis.vbs` (runs in the background) or `setup.bat` (shows a window) to start it again.
   - On **Docker / VPS**: `docker compose restart`.
   - On **Linux (systemd)**: `sudo systemctl restart javis`.
2. **Reload the interface with a clean cache (when the screen is wrong, a button is missing, or you just changed the interface).** Press **Ctrl+Shift+R** in the browser (Mac: Cmd+Shift+R). This is a hard refresh, forcing the browser to reload every interface file instead of using the cached copy.

> The simple rule to remember: change the core (a `.py` file) means **restart the server**; the interface displaying wrong means **Ctrl+Shift+R**.

## Common problems table

| Symptom | What to do |
|---|---|
| You edited code (or just updated) and **nothing changed** | If a `.py` file changed: **restart the server** (Windows: `stop-javis.bat` then `start-javis.vbs`; Docker: `docker compose restart`). If only the interface changed: press **Ctrl+Shift+R**. |
| **Port 7777 is held** and the new build will not come up | Kill the old process FIRST, then start again. Windows: run `stop-javis.bat`, or `taskkill /F /PID <pid>` with the PID holding the port. Docker: `docker compose down` then `docker compose up -d`. |
| **Hostinger cannot pull the image** | Set the GHCR package to **Public** (GitHub, the repo, Packages, choose `javis-os`, Package settings, Visibility = Public). Then wait for the GitHub Action build to finish (the repo's Actions tab) and Deploy again. |
| Opening the app **asks for a SETUP TOKEN** | Get the token in the container's App terminal: `cat /data/state/.setup_token`. If you are on the host: `docker compose logs javis` and find the line with `SETUP TOKEN`. To avoid the token entirely: preset the env vars `JAVIS_ADMIN_USER` and `JAVIS_ADMIN_PASSWORD` at deploy time and sign straight in. |
| **Claude reports it is not signed in** (Javis cannot answer) | Sign the Claude "brain" in once. In the app: open **Models**, on the Claude Code card click **Sign in to Claude**, open the link, paste the code if asked. By command: `claude auth login --claudeai` (on Docker, run it in the App terminal). |
| **The Files page errors at "Loading..."** | The server has no Files endpoint yet (a 404). **Restart the server** to load the new endpoint, then press **Ctrl+Shift+R**. |
| Images in old conversations show a grey **Image expired** box | By design: `attachments/` and `inbox/` are a cache, and files over 30 days (or when the 300MB ceiling is passed) are cleared. See "Old images and files disappear" below for how to keep them or turn clearing off. |
| Voice / microphone will not turn on | Browsers only grant microphone permission over **HTTPS** (or on localhost). Opening `http://<ip>:7777` is always blocked. Use an `https://` URL (Hostinger `*.hstgr.cloud`, Cloudflare Tunnel, or a custom domain with SSL). See [Branding and custom domains](15-branding-and-domains.md). |
| You updated in the app but **the version did not change** | Wait a little longer; if it still reports the old build, check the update log: `update.log` in the state folder (`server/update.log` locally, `/data/state/update.log` on Docker), or `docker compose logs`. |
| **`javis` reports 401** or "invalid token" | The token is wrong or was revoked. Create a new one at **Account > API tokens** then run `javis login <address>` again. See [The Javis CLI](24-cli.md). |
| **`javis task add` / `javis brain ls` report 403** | Your token is the **chat only** kind. These commands need a **full power** token, so create one at Account > API tokens. |
| **`javis up` reports it cannot find a Javis install** | Exactly as it says: the CLI package does NOT contain the server. Point `JAVIS_HOME` at the Javis folder, run the command from inside that folder, or use `javis login <address>` to connect to a Javis running elsewhere. |

The sections below explain each row in more detail.

## You edited code and nothing changed

Javis has two parts that run differently, so refreshing them differs too:

1. **Changing the core (Python `.py` files in `server/`)**: the running server still holds the old build in memory. You must **stop and start the server**:
   - Windows: run `stop-javis.bat`, wait a few seconds, then run `start-javis.vbs`.
   - Docker / VPS: `docker compose restart`.
   - Linux systemd: `sudo systemctl restart javis`.
2. **Changing the interface (HTML/CSS/JS in `dashboard/`)**: the server needs no restart, but the browser often keeps the old build in cache. Press **Ctrl+Shift+R** for a clean reload.

If neither helps, check that you are on the right port and the right brain.

## Port 7777 is held and the new build will not come up

Javis's default port is **7777**. When an old process has not fully stopped and you start a new build, the new one errors because the port is busy. Work through it in order:

1. Stop the old process first. Windows: run `stop-javis.bat`. If it persists, find the PID holding the port then `taskkill /F /PID <pid>`. Docker: `docker compose down`.
2. Start again. Windows: `start-javis.vbs`. Docker: `docker compose up -d`.

To move to another port (when 7777 collides with other software), set `JAVIS_PORT` in the `.env` file; see [.env configuration](16-env-configuration.md).

## Hostinger cannot pull the image

When deploying through Hostinger Docker Manager and it cannot download the image, there are usually two causes:

1. **The image is Private.** Go to GitHub, open the repo, choose **Packages**, choose `javis-os`, go to **Package settings** and set **Visibility = Public**. Only then can Hostinger pull without a registry login.
2. **The image has not finished building.** Every push to the `main` branch starts a new GitHub Action build. Open the repo's **Actions** tab, wait for the latest build to finish (a green tick), then Deploy again on Hostinger.

## Opening the app asks for a SETUP TOKEN

When Javis runs public (Docker/VPS/Hostinger), opening the app the first time shows the create-admin screen and may ask for a **SETUP TOKEN**. This stops a stranger who only has the URL from creating the account (because the engine runs with full power on the machine). Get the token like this:

1. **In the container's App terminal** (that terminal is INSIDE the container so it has no `docker` command): run `cat /data/state/.setup_token`, copy the string, paste it into the SETUP TOKEN field.
2. **On the host (outside the container)**: run `docker compose logs javis` and find the line containing `SETUP TOKEN`.
3. **Skip the token entirely**: preset the admin at deploy time with the two env vars `JAVIS_ADMIN_USER` and `JAVIS_ADMIN_PASSWORD` in the compose file. Then opening the app takes you straight to sign-in with no token question.

Security details and how to set a password: [Security and accounts](14-security-and-accounts.md).

## Claude reports it is not signed in

When you run the Claude engine, Javis borrows the `claude` CLI's own login session on the machine: sign in once and it survives every restart and update. If Javis does not answer or reports it is not signed in:

1. **In the interface:** open **Models** (the **Connections** group on the left nav rail). On the Claude Code card, the status line reads **○ Not signed in**. Click **Sign in to Claude**, the app shows a link; open it to sign in to claude.ai; if the page shows a code, paste it into the field and click **Send code**. When it finishes, the status changes to **● Connected**. There is a **↻ Check again** button to refresh the status.
2. **By command:** run `claude auth login --claudeai` once (on Docker, run it in the **App terminal**), open the link, paste the code.

The login token lives in `~/.claude` (Docker: the `claude-auth` volume), so it survives updates. If you already signed in on another machine, you can copy the `~/.claude` folder across. See also [Models and engines](10-models-and-engines.md).

## The Files page errors at "Loading..."

If you open **Files** (**Brain** group) and the file list errors instead of appearing, the server is usually running an old build with no Files endpoint (a 404). The interface itself says so: **restart the server** (Windows: `stop-javis.bat` then `start-javis.vbs`) then **reload the page** with Ctrl+Shift+R.

If it reports an expired session (a 401), just reload the page and sign in again. The full Files guide is at [File manager](05-file-manager.md).

## Old images and files disappear (the grey "Image expired" box)

Scrolling back through an old conversation and finding only a grey box reading **Image expired**, or a file you once uploaded no longer opening: this is deliberate behaviour, not a bug.

A brain's `attachments/` and `inbox/` folders (images Javis generated, files you sent through chat or Telegram) are treated as a **cache**, not as knowledge. Knowledge is the `.md` files. Javis clears them under two rules:

| Rule | Default | Meaning |
|---|---|---|
| File age | 30 days | Files in `attachments/` + `inbox/` older than this are deleted. |
| Size ceiling | 300 MB | If the total cache area passes the ceiling, delete oldest first until it is back under. |
| Temporary stage folder | 3 days | Where files you paste or upload into the chat box land before the engine reads them (`.staging` in the state folder). Here `.md` files are cleared too. |

The clearing pass runs in the background **every 6 hours**. `.md` files that end up in `attachments/` and `inbox/` are **never deleted** (only the temporary stage folder clears `.md` as well).

**To keep something long term:** do not leave the image in the cache area. Once read, pull its content into an `.md` note in the brain, or move the file into another folder of the brain (only `attachments/`, its variants, and `inbox/` are cleared), or store it externally.

**To turn clearing off entirely:** open `settings.json` in the state folder (`server/settings.json` locally, `/data/state/settings.json` on Docker) and add the `media` block:

```json
"media": { "enabled": false }
```

Setting `"enabled": false` clears nothing at all. To loosen rather than disable, adjust the numbers: `"max_age_days": 90`, `"max_mb": 2000`, `"staging_days": 7`; setting `max_age_days` or `max_mb` to 0 disables just that rule. After editing, **restart the server**.

A note if you have GitHub sync on: `attachments/` and `inbox/` ARE within the sync scope, so clearing also propagates to the backup repo and to other machines on the next sync. See [Backing the brain up to GitHub](18-github-backup.md).

## The provider reports a rate limit

The free tiers of API providers (Groq most visibly) tighten **four things in parallel**, and each demands a completely different response. Javis reads the error message and classifies it, so reading the notice in chat tells you which one you hit:

- **Tokens per minute, this turn is too large.** Javis shortens the context itself and resends. If it still does not fit, turn on the **Optimised** level at the top of the Usage page, or ask a shorter question.
- **Tokens per minute, the window is full.** Earlier turns have not aged out. Javis waits exactly the number of seconds the provider states then resends. Shortening the question does not help.
- **Requests per minute.** Calls came too thick and fast. Wait a moment then ask again.
- **A DAILY limit** (tokens or requests). The day's quota is spent. Shortening the question does not help at all. You have to wait for the new day, switch temporarily to another brain on the **Models** page, or upgrade your plan with the provider.

If Javis cannot classify it, it shows the **provider's error message verbatim** rather than guessing. Sending that exact sentence in a bug report makes it far easier to trace.

To hit this far less often: choose the **Optimised** or **Ultra-saving** level at the top of the **Usage** page (since 0.24.7 new machines default to Ultra-saving). After the first refusal, Javis remembers that account's real limits (as stated by the provider itself) and keeps the context under the threshold on later turns, with nothing to declare.

### When the provider stumbles once, Javis re-asks by itself

Since version 0.24.4, a model call that fails on a **transient** error (429 too many calls, 5xx overload, a network blip) is retried automatically up to three times, seconds apart. If the provider sends `Retry-After`, Javis obeys that exact number of seconds. You usually see nothing at all, only an answer arriving a second or two later.

Two cases where Javis **deliberately does not** retry:

- **The answer already started appearing.** Retrying would make you read the answer twice.
- **The turn already ran tools** (sent a message, wrote a file, scheduled something). Retrying the whole round would do those things a second time. Better to report the error.

If all three attempts fail, Javis reports the provider's error verbatim with the note *(retried 3 times)* so you know it was not a momentary blip. **Non**-transient errors (a wrong key, a wrong model name, a spent daily quota, exceeding the context size) are reported on the first attempt, because retrying identically only burns another call to receive the same error.

## Where to see the logs

There are several places, depending on what you want to see:

1. **The log of Javis running in the background**: open the **Work** group on the left nav rail, choose **Recurring jobs**, and scroll to **Recent log**. This is where turns of Javis waking to do a job are recorded, filterable per loop. See [Recurring jobs and reminders](08-recurring-jobs.md).
2. **The self-learning log**: the **Self-learning** page (**Brain** group) has two separate panels, **What Javis taught itself (latest commit)** and **Learning log**. See [Self-learning](22-self-learning.md).
3. **The Updates page** (**System** group, the page title is **Update log**): this is where you see the running version and the feature history per release. There is no separate "Logs" or "Activity log" page any more; the `logs` item on the rail is this page.
4. **The server's technical log** (when you need to dig into an error):
   - Windows running in the background through `start-javis.vbs`: the log is at `server\javis.log`.
   - Docker / VPS: `docker compose logs javis` (add `-f` to follow: `docker compose logs -f`).
   - Linux systemd: `journalctl -u javis -f`.
5. **The update log** when you click the update button in the app: the `update.log` file in the state folder, so `server/update.log` locally and `/data/state/update.log` on Docker (the path follows `JAVIS_STATE_DIR`). You usually do not need to open it: when an update fails the interface already shows the notice, and the app reads the last 50 lines of this file to report the state.

## Frequently asked questions

### Is data lost during an update?

No, if you run Docker. Every note, brain, setting and even the Claude login token lives in a **Docker volume** (`javis-data`, `claude-auth`), separate from the image. When you update (clicking **⬆ Update now** on the **Updates** page, a Redeploy on Hostinger, or `./update.sh` on a VPS), the image is replaced but the volumes stay, so data is **not** lost. On a native install the data is in the repo's `brains/` folder, which `git pull` does not delete either.

### How does in-app updating work?

Open **Updates** (**System** group); the **Javis OS** card shows the running version and checks GitHub for a newer one. If there is one, the status line reads **🆕 New version available** with a **What's new** panel, and the **⬆ Update now** button appears when the environment supports it. Click it, confirm, and the app runs through the 6 steps shown on the progress bar (Prepare, Download code, Install libraries, Restart, Health check, Done) then reloads the page. If the new build is broken, Javis **rolls back by itself** and reports **↩ The new build failed, rolled back**. Below the card is the update-log timeline of released versions.

An install directly on the machine (Windows, Linux, macOS) can always update itself. The Docker build only updates in place when the **Watchtower** container is running.

Watchtower is under `profiles: ["update"]`, so `docker compose up -d` does **not** start it, which is the most common reason one machine has the button and another does not. Start it once with `docker compose --profile update up -d` then reload the page. The Hostinger stack deliberately omits Watchtower (it cannot reach the Docker socket), so that machine updates through **Redeploy**. The Updates panel tells you which case your machine is in.

**A compose command reporting `not found`** comes in three shapes with three entirely different causes:

| Error | Cause | What to do |
|---|---|---|
| `no configuration file provided: not found` | You are in the wrong folder. The folder name depends on how you cloned: `javis` if you followed the command in DEPLOY.md, `javis-os` if you cloned straight without renaming | `cd` into the folder holding `docker-compose.yml`. If you cannot remember where it is, ask Docker: `docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project.working_dir"}}'` |
| `docker: command not found` | You are typing **inside** the Javis container (the app's terminal) rather than on the host | SSH into the VPS and type it there |
| `docker: 'compose' is not a docker command` | An old Compose (v1) | Write it hyphenated: `docker-compose --profile update up -d` |

### Can I run several brains (second brains)?

Yes. Javis manages several brains in the `brains/` folder. From the brain dropdown in the interface you can:

1. Create a new brain: click the add-brain button and give it a name when asked.
2. Switch brain: pick another one in the dropdown; the Files page, the graph and the memory all follow the selected brain.
3. Delete a brain: select it and click the delete button, and the interface requires you to **type the brain name exactly** to confirm (against accidental deletion). The **default brain** cannot be deleted.

Details in [Second Brain: memory, Wiki, INGEST](13-second-brain.md).

### Can a deleted brain be recovered?

Yes, within 30 days. Deleting a brain is not permanent: Javis moves the whole brain folder to a **local trash** at `brain-trash` inside the state folder (`server/brain-trash` locally, `/data/state/brain-trash` on Docker), named `<brain name>__<date time>`. That copy is kept 30 days before being cleared, and it does **not** go to the sync repo. To recover, copy the folder back into `brains/` and reload the page.

Conversely, the deletion **propagates to other machines** syncing the same repo (Javis writes a "tombstone" so the other machine does not resurrect the deleted brain). So if you want to recover, do it soon and do it on the machine that still holds the trash copy.

### Are uploaded images and files kept forever?

No. `attachments/` and `inbox/` are a cache: by default files over **30 days** old, or the excess above the **300 MB** ceiling, are cleared, and the temporary stage folder after **3 days**. A cleared image shows as a grey **Image expired** box in the old conversation. How to keep them or turn clearing off is in "Old images and files disappear" above.

### How do I change Javis's voice?

The default voice is `vi-VN-HoaiMyNeural` (Vietnamese Edge TTS) at `+5%` speed. To change the voice or speed, set two variables in `.env` and restart the server:

| Variable | Meaning | Default |
|---|---|---|
| `TTS_VOICE` | The voice name | `vi-VN-HoaiMyNeural` |
| `TTS_RATE` | The reading speed | `+5%` |

How to set variables: [.env configuration](16-env-configuration.md). Note: the speaker button in the interface only turns reading answers aloud on and off, it does not change the voice. How to use voice in a conversation: [Chat and voice](02-chat-and-voice.md).

### The microphone will not turn on over remote access?

Browsers require **HTTPS** before granting microphone permission (localhost aside). Opening the app on a bare IP like `http://<ip>:7777` always blocks the microphone with no manual override. The fix: use an `https://` URL through Hostinger (`*.hstgr.cloud`), Cloudflare Tunnel (which gives a `https://...trycloudflare.com` URL), or a custom domain with SSL. See [Branding and custom domains](15-branding-and-domains.md).

## Still stuck?

1. Collect the server log (see "Where to see the logs" above) to find the specific error.
2. Try in order: restart the server, then Ctrl+Shift+R.
3. Check that the environment variables in `.env` are set correctly, see [.env configuration](16-env-configuration.md).
4. Check that the "brain" is still signed in (on **Models**, the card of the engine you use must read **● Connected**).
