# .env configuration

*[Tiếng Việt](../16-cau-hinh-env.md) · **English***

This page lists the environment variables Javis OS reads at startup, with their meaning, default value and when you would change them. The content follows the `env.example` file and how the server actually reads `os.getenv(...)` in the source (`server/config.py`, `server/main.py`, `server/web_security.py`, `server/claude_cli.py`, `server/sessions.py`, `server/plugins_host.py`...).

The most important thing to remember: **everything runs with every line left empty**. On a personal machine you barely ever need to touch `.env`. Editing it is mainly for putting Javis on a VPS or public server, or for changing the voice, the port or the data paths.

If you install through **Hostinger Docker Manager**, you do not need the full advanced list below. The Hostinger compose file surfaces only 3 user fields in the Environment box: `DOMAIN_NAME`, `JAVIS_ADMIN_USER`, `JAVIS_ADMIN_PASSWORD`. The internal variables for ports, state, brains and the working folder are already inside the Docker image.

## What this feature is

`.env` is a text file in the **project root** (the folder holding `env.example`, `docker-compose.yml` and the `server/` folder). Each line is a variable shaped `VARIABLE_NAME=value`. When Javis starts, it reads them to learn: which port to listen on, whether login is required, where the Second Brain data lives, what the default voice is.

Three configuration places need to be kept apart:

- **The `.env` file**: system-level settings, read once at startup. A change only takes effect after restarting Javis.
- **The ⚙ Settings panel in the app** (the Account, Models, Channels pages...): settings changed live through the interface, saved into `settings.json`, no file editing. For example: switching model, the OpenRouter API key, the Telegram token, the custom domain, the logo. More in [Models and engines](10-models-and-engines.md), [Security and accounts](14-security-and-accounts.md), [Branding and domains](15-branding-and-domains.md).
- **A few `settings.json` keys with no interface**: currently the `media` block (the rules for clearing images and temporary files). Changing them means opening the file by hand. See the dedicated section below.

In short: `.env` handles "where it runs, who gets in, where the data lives". The in-app Settings panel handles "which model, which key, which voice". `settings.json` is where the two meet, and a few rare keys can only be edited there.

## Where to open it in Javis

`.env` has no button in the dashboard. It is a file you create and edit in a text editor (Notepad, VS Code...).

Creating the `.env` file the first time:

1. Open the project root (where you downloaded or unzipped Javis; on Docker that is `/app` inside the image, while `.env` sits next to `docker-compose.yml` on the host).
2. Find the template file `env.example` (the name deliberately has NO leading dot, so Hostinger's Docker Manager does not auto-scan `.env*` files and import every comment line into the Environment box).
3. Copy it and rename the copy to `.env` (the copy DOES have the leading dot, and no `.txt` extension).
4. Open `.env` in an editor, remove the `#` in front of the variables you want on, then fill in the values.
5. Save the file. Restart Javis.

The quick way to copy by command (run in the project folder):

- Windows PowerShell: `Copy-Item env.example .env`
- Git Bash / Linux / macOS: `cp env.example .env`

A note on `#`: a line starting with `#` is a comment and Javis ignores it. To enable a commented variable, delete the `#` at the start of that line. For example change `# JAVIS_PORT=7777` into `JAVIS_PORT=8080`.

## The list of variables

Grouped by function. The "Default" column is the value used when you leave it empty or do not declare it. Groups 1 to 5 are the ones users normally touch; groups 6 and 7 are advanced and almost never need editing.

### Group 1: Workspace display

| Variable | Meaning | Default | When to change |
|---|---|---|---|
| `WORKSPACE_NAME` | The workspace name shown on the dashboard | `Javis OS` | You want your own name for the workspace. Note: if you already set a name in the app, the app's saved name wins and this variable is only a fallback. |
| `USER_NAME` | The displayed user name | `Bạn` ("you") | You want Javis to address you by name rather than "you". |

### Group 2: Network (port and listening address)

| Variable | Meaning | Default | When to change |
|---|---|---|---|
| `JAVIS_HOST` | The address the server listens on. `127.0.0.1` = only this machine can reach it. `0.0.0.0` = listen everywhere (public, anyone with the address gets in) | `127.0.0.1` (the Docker image presets `0.0.0.0`) | Only switch to `0.0.0.0` when running on a VPS/server and wanting access from other machines. You must then turn login on (see group 3). |
| `JAVIS_PORT` | The dashboard's listening port | `7777` | Port `7777` is taken or you want another one. After changing, open that port in the browser. |

An important detail about `JAVIS_HOST`: Javis uses a "safe by default" rule. If the listening address is NOT loopback (anything other than `127.0.0.1`, `localhost`, `::1`), the server treats itself as public and **turns forced login on** so nobody gets in without an account. The reason: an AI brain runs with full power on the machine, and leaving it open is dangerous.

### Group 3: Login and security

| Variable | Meaning | Default | When to change |
|---|---|---|---|
| `JAVIS_REQUIRE_LOGIN` | Force login on or off. `1`/`true`/`yes`/`on` = on. `0`/`false`/`no`/`off` = off | Automatic (on when bound public) | Running on localhost but exposed through a tunnel (Cloudflare, ngrok...): set `JAVIS_REQUIRE_LOGIN=1` to keep strangers out. |
| `JAVIS_ADMIN_USER` | The admin username created at deploy time | `admin` | Set it alongside `JAVIS_ADMIN_PASSWORD` to preseed the account, so you never need the SETUP TOKEN from the log. |
| `JAVIS_ADMIN_PASSWORD` | The admin password created at deploy time | (empty) | Public deploy: put a strong password here. With this variable set and no admin yet, Javis creates the admin at startup and closes the create-account screen entirely (the safest option for public). |
| `JAVIS_SECURE_COOKIE` | Send the cookie only over HTTPS. `1`/`true`/`yes`/`on` = on | Off | Only turn on when you are CERTAIN of end-to-end HTTPS (a custom domain with SSL). Turning it on by mistake behind an HTTP proxy causes a login loop (the right password still bounces you back to the sign-in page). |
| `JAVIS_ALLOWED_HOSTS` | Extra hostnames allowed to call Javis (CSRF and DNS-rebinding protection). Comma separated | (empty) | Running behind a reverse proxy on a domain not declared in the app, with no password set, and getting 403 "host not allowed". `localhost`, `127.0.0.1`, `::1` and the domain you set in Settings are already allowed. |
| `JAVIS_ENABLE_USER_PLUGINS` | The HARD gate for plugins you install. Only `true` loads them | Off | You installed a plugin yourself (the global `plugins/` folder or one inside a brain) and want it to run. User plugins run REAL PYTHON CODE inside the server process, so they are blocked by default. Old alias: `JAVIS_ENABLE_VAULT_PLUGINS`. Plugins bundled with the app are not subject to this gate. See [Plugins](20-plugins.md). |
| `JAVIS_TERMINAL` | The switch that removes the Terminal in the Code group entirely. `0`/`off`/`false`/`no` = off | On | You do not want any command line openable from a browser. The Terminal is already only open to a SIGNED-IN browser (API tokens cannot reach it), but many people still want it hard-locked at the server layer. See [The Code group: Terminal](27-code-terminal.md). |
| `JAVIS_TERMINAL_SHELL` | The shell the Terminal runs | `$SHELL`, falling back to `bash`/`sh`. Windows: `powershell.exe` then `cmd.exe` | You want to force another shell (`zsh`, `fish`, `cmd.exe`). |
| `JAVIS_TERMINAL_CWD` | The folder the terminal opens in | The HOME of the user running Javis | You want the shell to open at the brain root or another project folder. |

About the SETUP TOKEN: when running public with no admin account, opening the app the first time asks for a setup token. The token is only printed to the server log at startup, so only someone who can see the log or terminal can create the account, and whoever merely has the URL can do nothing. If you preset `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` the token is not needed at all, just sign in with that account. More in [Security and accounts](14-security-and-accounts.md).

About custom domains and HTTPS: on a Caddy VPS you enter the domain right in **Settings → Voice, branding and access → Domain and SSL** then click **Enable SSL**. On Hostinger the wizard prepares the `DOMAIN_NAME` variable for you to copy into Docker Manager before a Redeploy. When you access the proper domain over HTTPS, the server enables the Secure cookie by itself so `JAVIS_SECURE_COOKIE` need not be set manually. Details in [Branding and domains](15-branding-and-domains.md).

### Group 4: Data paths (Second Brain and state)

| Variable | Meaning | Default | When to change |
|---|---|---|---|
| `CLAUDE_CWD` | The working folder of the CLI engine (where it reads `CLAUDE.md` and inherits MCPs) | The project root (Docker: `/app`) | You want the engine to work in another folder. |
| `BRAINS_DIR` | The parent folder holding every brain, one subfolder per Second Brain. The default brain is `<BRAINS_DIR>/Brain Default` | `brains/` in the project (Docker: `/brains`) | You want the brains elsewhere (a separate data disk, a git-backup mount). |
| `OBSIDIAN_VAULT_PATH` | The path of the main Second Brain vault | `vault/` in the project (Docker: `/data/vault`) | If the server already has a real Obsidian vault, point this at it. Left empty, Javis uses the sample vault in the repo (so a fresh machine runs immediately). |
| `BRAIN_PATH` | The old-style brain folder from the single-brain era. Kept only to migrate old data | `brain/` in the project (Docker: `/data/brain`) | Almost never needed. Do not use it for a new install. |
| `SOURCES_PATH` | Where chat attachments are stored (as sources for the Second Brain) | `brain/01 - Sources/` in the project | You want the source folder somewhere else. |
| `JAVIS_STATE_DIR` | Where Javis writes its own state: `settings.json`, login sessions, recurring job configuration, the `.secret_key` encryption key, the conversation database | `server/` (Docker: `/data/state`) | On Docker/VPS this must point at a writable volume (the source tree inside the container is read-only). On a personal machine, leaving it empty is fine. |
| `JAVIS_SESSIONS_DB` | The path of the database file holding conversation sessions (`conversations.db`) | Inside `JAVIS_STATE_DIR` | You want the session history file elsewhere. See [Sessions](04-sessions.md). |
| `JAVIS_FILES_ROOT` | The browsing ceiling of the Files page (you cannot click "Up" beyond it). `brain`/`vault` = locked inside the brain; `drive`/`root` = the whole disk holding the brain; `<path>` = a specific folder (which must contain the brain) | localhost: the whole disk; public bind: locked to the brain | Running public (VPS) but still wanting wide browsing: set `drive` or a parent folder. Wanting a hard lock inside the brain while running locally: set `brain`. |

A note about the Second Brain: `BRAINS_DIR` is the folder that actually holds your brains (not `brain/` at the repo root, which is the old-style path). Left empty, it runs immediately with the sample data in the repo. Read more about how memory works in [Second Brain: memory, Wiki, INGEST](13-second-brain.md) and [Knowledge graph](03-knowledge-graph.md).

**A warning about `.secret_key`:** inside the `JAVIS_STATE_DIR` folder is a small file named `.secret_key`. It is the key that encrypts the secret fields in `settings.json` (OpenRouter/Anthropic/OpenAI/Gemini API keys, ChatGPT sign-in tokens, the Telegram token, the GitHub backup token, the ElevenLabs key). Copying `settings.json` to another machine while forgetting `.secret_key` means **every key is lost**: Javis cannot decrypt them, returns empty strings, and you must re-enter each one. Back up the pair together. If the machine lacks the `cryptography` library, Javis cannot encrypt: secrets fall back to the `plain:` prefix with a warning line in the log; `pip install cryptography` then restart and it is fixed. Details in [Security and accounts](14-security-and-accounts.md).

### Group 5: Voice (TTS)

| Variable | Meaning | Default | When to change |
|---|---|---|---|
| `TTS_VOICE` | The default reading voice (using free Edge TTS) | `vi-VN-HoaiMyNeural` | You want another voice. A male Vietnamese voice or a foreign-language voice, say. |
| `TTS_RATE` | Reading speed, as a plus/minus percentage | `+5%` | Too fast, so lower it (`+0%` or `-10%`); faster, so raise it (`+15%`). |

Note: these two TTS variables apply to the default free Edge TTS voice. If you pick another voice provider (OpenAI TTS or ElevenLabs), that is configured in the app's Settings panel rather than through `.env`. How to chat and turn voice on: [Chat and voice](02-chat-and-voice.md).

### Group 6: Deploy, domains and updates

| Variable | Meaning | Default | When to change |
|---|---|---|---|
| `DOMAIN_NAME` | The domain the reverse proxy (Hostinger's Traefik) routes to Javis. Javis reads it to compare against the domain you entered in the app and to know whether a Redeploy is needed | (empty; the Hostinger compose sets `localhost`) | Hostinger deploy: set it to your domain in Docker Manager then Redeploy. The in-app wizard has a **Copy variable** button that prepares this line. |
| `JAVIS_DEPLOY_TARGET` | Declares the environment explicitly: `hostinger`, `vps`, `native`, `windows` | Auto-detected (a `.hstgr.cloud` hostname = hostinger; running Docker = vps) | Almost never needed by hand. The Hostinger compose already sets `hostinger`. Set it when Javis guesses the environment wrong and the domain wizard shows the wrong instructions. |
| `WATCHTOWER_TOKEN` | The token the "Update now" button (the **Updates** page) uses to call Watchtower when running Docker | In `docker-compose.yml`: `javis-update`. Outside Docker: empty (no variable means Javis assumes Watchtower is not running) | For tighter security: change it to a random string, setting the same value on both the app and the watchtower service. |

### Group 7: Advanced variables (rarely need touching)

| Variable | Meaning | Default | When to change |
|---|---|---|---|
| `JAVIS_CLAUDE_IDLE_TIMEOUT` | The ceiling on waiting when the engine has answered then gone quiet mid-turn with NO tool running, in seconds. `0` = no limit | `0` | The default removes the ceiling: engine silence does NOT mean a hang (a model thinking at high effort, or composing a long file to write out, both go quiet for minutes). Only set a positive number if you genuinely need turns cut off automatically. |
| `JAVIS_CLAUDE_FIRST_TIMEOUT` | The ceiling on waiting for the FIRST characters of a turn, in seconds. `0` = no limit | `0` | Same reason as above: a long conversation has to reload the whole context on the first turn, which takes time. |
| `JAVIS_CLAUDE_TOOL_TIMEOUT` | The ceiling on waiting while a TOOL is mid-run (rendering video, removing a background, building...), in seconds. `0` = no limit | `3600` | This ceiling is kept because it measures a REAL live child process rather than measuring silence. Raise it for work over an hour (encoding a long video, training a model...). |
| `JAVIS_CODEX_SANDBOX` | Whether to use Codex's (ChatGPT's) own sandbox rail for background work. `auto` = yes, matched to the job's permission level (suggest becomes read-only, auto becomes workspace-write). `off` = no separate rail | `auto`, but the **Docker image presets `off`** | Codex wraps file read/write commands in bubblewrap, and bubblewrap cannot start inside a container (an ordinary user, no CAP_SYS_ADMIN, and Ubuntu 24.04 also blocks user namespaces through AppArmor), so the rail is not tighter but simply dead: every background job on ChatGPT fails to read a single file. Outside Docker, leave it at `auto`. The trade-off with `off`: Codex has no per-call allowlist like Claude, so the `suggest` level loses what stopped it writing files; the money/order/publishing/messaging rails are UNAFFECTED because they live in the MCP Hub. |
| `JAVIS_AGY_PROMPT_DAI` | Forces how Javis hands a prompt to Antigravity CLI when it exceeds the command-line ceiling: `stdin` (through a pipe), `file` (write it out and tell the model to read it), `argv` (straight onto the command line) | (empty, Javis chooses: stdin first, falling back to file on failure) | Only for odd cases on your machine. Windows caps the whole command line at 32767 characters while Javis's system prompt is already over 36,000, so `argv` there is guaranteed to break. See [Models and engines](10-models-and-engines.md). |
| `JAVIS_AGY_TIMEOUT` | The time ceiling for one Antigravity CLI run, in seconds. Javis passes the same number down to the CLI's own `--print-timeout` | `900` | Raise it when long background work gets cut off. Left unset, `agy` cuts itself off at minute 5 and returns a half-finished answer rather than an error. |
| `JAVIS_AGY_MCP_HOME` | Whether Javis may write the MCP configuration into your HOME (`~/.gemini/config/mcp_config.json`, the place `agy` ACTUALLY loads MCP from). `0` = no, only write `<brain>/.agents/mcp_config.json` | (empty = it does write) | Setting `0` accepts that Antigravity **loses every Javis tool** on any `agy` build that has not patched issue #60 (that build finds the workspace configuration then ignores it). Only set it if you do not want Javis touching a file shared with the Antigravity IDE. |
| `JAVIS_AGY_MCP_CONFIG` | Write `agy`'s MCP configuration into EXACTLY this file instead of the two default HOME paths | (empty) | Use it when your `agy` build keeps its configuration elsewhere. |
| `JAVIS_AGY_MCP_KEY` | The URL key name Javis writes into the MCP entry: `serverUrl` (current) or `url` (older 1.0.x builds) | (empty = write both) | Only when your `agy` build rejects an entry with an unknown key. Writing both is so every build recognises it; the machine building Javis cannot download `agy`, so this is not directly measured. |
| `JAVIS_GROK_BIN` | A direct path to the `grok` binary (Grok Build CLI) | (empty, Javis searches PATH and `~/.local/bin`) | Only when the machine installed it somewhere unusual. |
| `GROK_DISABLE_AUTOUPDATER` | Turns Grok Build CLI's auto-updater off. Javis sets `1` ITSELF for every run of `grok` | `1` (set by Javis, but a value you set is respected) | Set `0` if you want the CLI to upgrade itself. Not recommended: Javis runs it headless, and an updater cutting in mid-turn either prints extra text into the result stream or writes into a read-only place. Upgrade by hand with `grok update`. |
| `JAVIS_GROK_TIMEOUT` | The time ceiling for one Grok Build CLI run, in seconds | `900` | Raise it when long background work gets cut off. This ceiling is not only precaution: if the CLI build on the machine does not declare the `--permission-mode` flag, Javis does not pass it, and a headless run that stops to ask for approval hangs silently forever; this is the only thing that unblocks that case. |
| `JAVIS_MAX_TOOL_ROUNDS` | The maximum tool-call rounds for ONE answer from the API-key engines (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama). Clamped between 1 and 120 | `30` | Since 0.47.1 this rarely needs touching: the main brake against a looping model is detecting "the same tool called with the same arguments" (a nudge on round 3, a stop on round 5), and this ceiling is only a distant safety net. Raise it and restart Javis if very long work still hits it. Claude Code and Codex are NOT subject to it, they manage their own loops. |
| `JAVIS_KANBAN_MAX_WORKERS` | How many Kanban jobs run in parallel. Clamped between 1 and 8 | `2` | Raise it on a strong VPS with a long queue; set `1` on a weak or congested machine. See [Work / Kanban](21-kanban-work.md). |
| `JAVIS_MEMORY_INDEX_MAX` | The character ceiling of the memory index (`MEMORY.md`) loaded into every chat turn. Over the ceiling Javis shortens descriptions gradually rather than dropping memories | `20000` | A very thick memory costs tokens on every turn; lower this to tighten it. See [Second Brain](13-second-brain.md). |
| `JAVIS_CLAUDE_ENGINE` | (Historical) Since 0.9.37 the Claude engine always runs through the official Agent SDK, so this variable does nothing; setting `cli`/`sdk-loops` is ignored with a log line | `sdk` | Nothing to do. If the Claude engine misbehaves, it reports the error with the server log. |
| `JAVIS_CODEX_BIN` | The absolute path of the `codex` executable | Auto-detected in PATH and the usual install locations | You installed the Codex CLI somewhere Javis cannot find. |
| `CLAUDE_CONFIG_DIR` | Claude Code's configuration folder (where `.credentials.json` lives). Setting it OVERRIDES entirely, matching Claude Code's own behaviour | `~/.claude` | You changed Claude Code's configuration folder yourself. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code's OAuth token, used to ask Anthropic for the real model list | (empty, read from the credentials file) | An environment with no credentials file (CI, a minimal container) that still wants the dynamic model list. |
| `JAVIS_CLAUDE_PROJECTS_DIR` | Where Javis reads Claude Code session logs to compute **Usage** | `~/.claude/projects` | Claude Code logs are somewhere else. See [Usage: tokens and cost](23-usage-and-cost.md). |
| `JAVIS_CODEX_SESSIONS_DIR` | Where Javis reads Codex session logs to compute **Usage** | `~/.codex/sessions` | Codex logs are somewhere else. |
| `JAVIS_YOUTUBE_PROXY` | A SEPARATE proxy just for reading YouTube subtitles, shaped `http://user:password@host:port`. Only YouTube traffic goes through it | (empty, direct) | Javis keeps reporting that YouTube suspects this server is a robot. The root of that error is **IP reputation**: YouTube flags the IP ranges of server providers (AWS, Google Cloud, Azure, cheap VPSs), so the same code runs fine at home and gets challenged on a VPS. Routing through a residential proxy means standing somewhere else on the Internet. Do not use the system's `HTTPS_PROXY` for this: it pushes **all** of Javis's traffic through it, model calls and MCP included, which is both slow and leaks data to a third party. See [Chat](02-chat-and-voice.md). |
| `JAVIS_IMAGE_HOST_MODEL` | The "host" chat model used to call the image-generation tool through the ChatGPT plan | `gpt-5.5` | The provider renamed the model and image generation broke. |
| `JAVIS_IMAGE_MODEL` | The model that actually generates images | `gpt-image-2` | As above. |

Note: `JAVIS_ENABLE_USER_PLUGINS` is also an advanced variable, but because it is a security rail it is listed in group 3.

## The `media` block in settings.json (no interface)

Each brain's `attachments/` and `inbox/` folders are a **cache**, not a knowledge store: images are material passing through, and once read and reduced to `.md` that is enough. So Javis clears them by age and by size, sweeping every six hours. The temporary stage folder (where a file you paste into the chat box lands) has its own, much shorter limit.

These clearing rules **have no field in Settings**. To change them, open `settings.json` in the state folder (personal machine: `server/settings.json`; Docker: `/data/state/settings.json`) and edit the `media` block:

```json
"media": {
  "enabled": true,
  "max_age_days": 30,
  "max_mb": 300,
  "staging_days": 3
}
```

| Key | Meaning | Default |
|---|---|---|
| `enabled` | `false` = clear nothing at all | `true` |
| `max_age_days` | Media files older than this many days are deleted. `0` or negative = the age rule is off | `30` |
| `max_mb` | The size ceiling of each brain's media area, in MB. `0` or negative = the size rule is off | `300` |
| `staging_days` | The separate limit for the temporary stage folder in the state folder | `3` |

Restart Javis after editing. An image that was cleared but is still referenced in an old conversation shows as a grey box saying the image expired, not a broken icon. To keep images long term, attach an external store (Drive, for instance) through the **Connections** page rather than letting Javis hold them.

## What to remember about ANTHROPIC_API_KEY

Javis uses the very **subscription** you already pay for as its brain (Claude Code for a Claude plan, Codex for a ChatGPT plan), so the `ANTHROPIC_API_KEY` variable in `.env` is **not needed**. MCPs you installed into Claude Code are inherited automatically. If you want models through an API provider (OpenRouter, OpenAI API, Anthropic API, Google Gemini API, Groq API), you enter the key in the app on the **Models** page, not in `.env`. Keys entered there are encrypted before being saved into `settings.json`. See [Models and engines](10-models-and-engines.md).

## Example of a minimal .env file

A personal machine, only changing the name and the reading speed, everything else untouched:

```
WORKSPACE_NAME=Trợ lý của Quy
USER_NAME=Quy
TTS_RATE=+0%
```

A public deploy on a VPS, preseeding the admin and opening it to outside access:

```
JAVIS_HOST=0.0.0.0
JAVIS_ADMIN_USER=admin
JAVIS_ADMIN_PASSWORD=put-a-really-strong-password-here
OBSIDIAN_VAULT_PATH=/data/vault
JAVIS_STATE_DIR=/data/state
JAVIS_ALLOWED_HOSTS=javis.yourname.com
```

In the second example, because `JAVIS_HOST=0.0.0.0` (public) Javis turns forced login on by itself, and because `JAVIS_ADMIN_PASSWORD` is set you sign straight in with that account, no SETUP TOKEN needed.

## Tips

1. Always keep `env.example` as the reference original. Only edit `.env`.
2. A change in `.env` only takes effect after restarting Javis. Unlike the in-app Settings panel, where a change applies at once.
3. If you are unsure what a variable does, leave the `#` (comment) in place. The defaults already work well.
4. For on/off variables (`JAVIS_REQUIRE_LOGIN`, `JAVIS_SECURE_COOKIE`, `JAVIS_ENABLE_USER_PLUGINS`), on accepts `1`, `true`, `yes`, `on`. Off accepts `0`, `false`, `no`, `off`.
5. The `.env` file holds passwords and sensitive configuration. Do not put it anywhere public. On a shared machine, restrict read permissions. The `.secret_key` file in the state folder deserves the same care, and matters even more: losing it loses every stored API key.
6. Turning on `JAVIS_ENABLE_USER_PLUGINS=true` is a weighty decision: plugins you install run real Python code inside the server process. Only turn it on when you know exactly where every plugin in the `plugins/` folder came from.

## Common problems

**You edited .env but nothing changed.** You have not restarted Javis. `.env` is only read at startup. Stop the server and start it again.

**After changing the port you cannot reach the app.** Your browser is still on the old port. Changing to `JAVIS_PORT=8080` means opening `http://localhost:8080`, not `7777`.

**The right password keeps bouncing back to the sign-in page.** Most likely you turned `JAVIS_SECURE_COOKIE=1` on while actually browsing over HTTP (not HTTPS). A Secure cookie is only sent over HTTPS, so the browser cannot hold the session. Delete that line or set it off, then restart.

**Everything returns 403 "host not allowed".** You reached Javis through a domain not on the allowlist, with no password set. Add the domain to `JAVIS_ALLOWED_HOSTS` (or enter it in Settings → Domain and SSL), or simply set a password.

**A plugin is enabled in the app but still does not run.** Plugins you install also need `JAVIS_ENABLE_USER_PLUGINS=true` in `.env` plus a restart. The app states this sentence too when you enable a plugin that is blocked.

**Opening the app asks for a SETUP TOKEN and you do not know where to get it.** The token is printed to the server log at startup. On Docker, check the container log for the "SETUP TOKEN" line, or read the `.setup_token` file in the state folder. Neater still: preset `JAVIS_ADMIN_PASSWORD` in `.env` to skip the token step.

**You set the workspace name in .env but the app shows another one.** The app prefers the name saved in Settings over the `WORKSPACE_NAME` variable. Edit the name in the app's Settings panel, or clear the saved name so the app falls back to the `.env` value.

**You pointed OBSIDIAN_VAULT_PATH at a real vault and Javis sees no data.** Check that the path is right and that Javis has permission to read the folder. On Docker the volume must be mounted at the path you declared. After fixing, restart and rebuild the graph (see [Knowledge graph](03-knowledge-graph.md)).

**After restoring a backup, every API key is empty.** You copied `settings.json` without `.secret_key` from the same folder. There is no recovery, you have to re-enter the keys on the Models and Channels pages.

If you are still stuck, see [Troubleshooting and FAQ](17-troubleshooting.md).

## Related

- [Getting started and first setup](01-getting-started.md)
- [Security and accounts](14-security-and-accounts.md)
- [Branding and custom domains](15-branding-and-domains.md)
- [Models and engines](10-models-and-engines.md)
- [Plugins](20-plugins.md)
- [Usage: tokens and cost](23-usage-and-cost.md)
