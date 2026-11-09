# Security and accounts

*[Tiếng Việt](../14-bao-mat-tai-khoan.md) · **English***

This page explains how Javis OS protects itself when you put it on the network, and how to use the **Account** page in the dashboard to set a password, sign out, turn login off and rename the workspace.

## What this feature is

Javis runs an AI brain with **full power over your machine or VPS**: it can read files, run commands, call tools. So if the dashboard is exposed to the Internet without a password, anyone who knows the address controls your machine.

Javis handles this in 7 layers:

1. **Login is forced automatically when running public.** When the server listens externally (not just this machine), Javis blocks every function until you sign in. On a personal machine (localhost) nothing is forced and you use it as before.
2. **Set the admin early, then turn on two-factor.** The first-run screen only asks for a username and password, so on a public server **whoever opens the link before an admin exists can create it**. Preset the admin through environment variables (or create the account right after deploying), then turn on 2FA (TOTP) on the **Account** page.
3. **Brute-force protection.** Too many wrong attempts temporarily locks that IP address; every wrong attempt is slowed down.
4. **Blocking foreign web pages from commanding Javis (CSRF) and blocking unknown domains pointed at your machine (DNS rebinding).** See the dedicated section below.
5. **Encryption of secret keys stored in `settings.json`.** API keys, Telegram tokens, GitHub tokens and the rest are not sitting on disk in plain text.
6. **API tokens for CLI and scripts, with NONE existing by default.** The login cookie only suits a browser; to call Javis from a terminal you must create a token by hand, choose its scope, and can revoke it at any time. See the dedicated section below.
7. **Blocking search engines and AI bots.** If the admin link leaks, Google does not list it and AI bots read nothing, not even the login screen. See the dedicated section below.

## Where to open it in Javis

Every account action lives under **Account** in the **System** group of the left nav rail. The **Settings** page has a condensed block covering the three most common actions (change password, sign out, turn login off) plus a two-factor status line; enabling two-factor and the sign-in history are on the **Security** tab of the **Account** page. API tokens for the CLI and scripts are on the **Integrations** page (**Work** group), tab **API token**.

The **Account** page has 2 tabs.

The **Account** tab:

- **Workspace**: rename the displayed workspace.
- **Login account**: set a password, sign out, turn login off.

The **Security** tab (added after the incident of 2026-11-09):

- **Overview**: whether 2FA is on, devices signed in, the last sign-in (time, IP, device), failed sign-ins in 7 days, API tokens. A red line when the settings file was ever changed outside Javis, an amber line while `JAVIS_ADMIN_PASSWORD` or `JAVIS_RESET_2FA` is still in the environment.
- **Two-factor authentication**: turn on, turn off, regenerate recovery codes.
- **Devices signed in**: one row per browser (device, IP, last activity). Sign out one, or press **Sign out all other devices** without changing the password.
- **Sign-in and security history**: every successful and failed sign-in, sign-out, username or password change, 2FA change, new token, reset from the environment, outside edit of the settings file, and AI assistant call blocked near a secret file. Filter by Sign-ins, Changes, Warnings.

## When Javis forces a login

Javis decides whether to force a login based on how the server is running:

| Situation | Login forced? |
|---|---|
| Running on a personal machine, listening on `127.0.0.1` / `localhost` (or `::1`) | No (unless you set a password yourself) |
| Running public (Docker/VPS/Hostinger), listening on `0.0.0.0`, `::` or a LAN IP | Yes, turned on automatically |
| A password has been set on the Account page | Yes, in every mode |

You can force it either way with the `JAVIS_REQUIRE_LOGIN` environment variable:

- `JAVIS_REQUIRE_LOGIN=1` : always force login, localhost included. Set this when you expose Javis through a tunnel (Cloudflare Tunnel, ngrok...) from a personal machine.
- `JAVIS_REQUIRE_LOGIN=0` : turn forced login off.

The safety principle is fail-closed: if the server listens on an address that is **not** purely localhost, Javis treats it as public and turns login on. Environment variable details in [.env configuration](16-env-configuration.md).

## How to use it (step by step)

### A. Creating the first admin account on a VPS or public server

The first time you open the dashboard on a public server with no admin yet, Javis shows the **create account** screen, which only asks for a username and password. Whoever opens the link first can create the admin, so do not let that window stay open. There are 2 ways:

**Way 1 - Set the admin through environment variables (recommended):**

1. In your deploy configuration (the Hostinger compose file, say), add 2 variables:
   - `JAVIS_ADMIN_PASSWORD` : the admin password you choose.
   - `JAVIS_ADMIN_USER` : the username (optional, defaults to `admin`).
2. Start Javis. At boot it creates the admin from these two variables and **closes** the create-account screen entirely. Opening the app takes you straight to the sign-in screen.
3. Sign in with the user and password you just set.

**Way 2 - Create the account right after deploying:**

1. Open the dashboard as soon as the deploy finishes.
2. On the create-account screen, enter a username and a password (**at least 8 characters**).
3. Click the create-account button. Javis creates the admin and signs you straight in.

Whichever way you pick, **turn on two-factor authentication (2FA)** on the **Account** page after your first sign-in.

### B. Setting a password (running on a personal machine, no password yet)

If you run Javis at home and want to lock it before moving to a VPS:

1. Go to **Account** in the left nav rail.
2. In the **Login account** block, enter the **Username** (leaving it empty uses `admin`).
3. Enter the **Password**.
4. Click **Set password**.
5. Javis saves the account and immediately grants you a session (it never locks you out).

The password must be at least **8 characters**, and the interface enforces exactly that number before sending, so you do not click Save and only then discover it was too short.

### C. Changing the password or username

Once a password exists, the **Login account** block shows the line "🔒 Password set · account: <your name>", adds a **Current password** field, and the button changes to **Change password**.

1. Go to **Account** in the left nav rail (or the **Login account** block on the **Settings** page, both do the same).
2. Enter the **Current password**. Required even while you are signed in: a machine left with the dashboard open must not be able to change the password and lock the owner out.
3. Enter the **New password** (8 characters or more). To change only the username, leave this empty and edit only the **Username** field.
4. Click **Change password**.

Afterwards **every other session is destroyed** (other machines, other browsers, phones) while the machine you are on is granted a new session right away so you are not thrown out. Two-factor authentication and the recovery codes are unchanged, no QR to scan again.

Changing only the username leaves other sessions alive, since the password did not change.

**If you forget the current password** there is no back door in the dashboard, you have to fix it from the server:

1. Stop the container (or stop Javis).
2. Delete (or empty) the `"auth"` block in `settings.json` in the state folder (Docker: `/data/state/settings.json`).
3. Set `JAVIS_ADMIN_PASSWORD` (and `JAVIS_ADMIN_USER` if you want) then restart. Javis recreates the admin from the environment variables at boot.

### D. Signing out

1. Go to **Account**.
2. Click **Sign out**.
3. Javis deletes the current session and reloads the page. Next time you must sign in again.

Signing out only ends the session in this browser, it does not delete the password.

### E. Turning login off (deleting the password)

Only do this on a personal machine, never on a VPS.

1. Go to **Account**.
2. Click **Turn login off**.
3. Confirm in the dialog warning that anyone opening the dashboard will be able to use it.
4. Javis deletes the password and **signs out every open session**.

Note: if the server is still running public (or you set `JAVIS_REQUIRE_LOGIN=1`), turning the password off does **not** throw the dashboard open, it returns to the forced create-account screen. Login is only truly off when the server listens on localhost and login is not forced.

### F. Renaming the workspace

1. Go to **Account**.
2. In the **Workspace** block, edit the **Workspace name**.
3. Click **Save**. The new name appears at the top of the dashboard immediately.

## Security log and alerts

Javis writes each security event as one line of `security_log.jsonl` in the state folder (Docker: `/data/state`), so the log **survives updates and redeploys**, unlike container logs. Each line has the time, IP, browser, the username typed and details. Passwords, 2FA codes and tokens are never written. Behind Caddy or Traefik the IP is the visitor's real address, not the proxy's.

These events are **sent to the owner right away** (bell, push notification, the owner's Telegram):

- A sign-in from a network never seen before (the same /24 is not new, so a phone moving between towers does not keep alerting).
- A sign-in with a 2FA recovery code.
- Username or password changed, 2FA turned on or off, recovery codes regenerated, API token created, login turned off.
- The account created or reset from the environment, 2FA removed with `JAVIS_RESET_2FA`.
- **The settings file changed outside Javis** (below).

### Detecting an outside edit of the settings file

Every time Javis itself writes the account (password change, 2FA...), it stores a fingerprint of the account block in `.auth_stamp.json`. When the username, password or 2FA in `settings.json` changes WITHOUT going through Javis (someone in a server terminal editing the file), Javis sees the mismatch within seconds, **signs out every device**, logs the event and tells the owner. Before, such an edit signed nobody out, so the owner could miss it entirely.

It detects, it does not prevent: whoever can write files on the server can still edit it. It tells you AT ONCE so you can follow "If you suspect a takeover" below. If you edit the file yourself over SSH (removing 2FA by hand, say), you are signed out once too; sign in again.

### The AI assistant may not touch secret files

The assistant runs commands on the server and reads messages from outside (Zalo, Telegram, webhooks). A planted message could ask it to edit the settings file. So at **every permission level** Javis refuses a shell command or tool call that touches: `settings.json` in the state folder, `.secret_key`, the session and token files, the security log, `~/.claude/.credentials.json`, `~/.codex/auth.json`, `authorized_keys`. This covers Claude Code (refused before the tool runs) and the terminal of the API engines. Each refusal is logged. Codex, Grok Build and Antigravity run in their own sandboxes and do not have this layer yet.

It stops the plain request, it is not a wall: code running as the same OS user can still build the path in pieces. To read or edit those files, use the Account page or a real server terminal (SSH, hPanel).

## If you suspect a takeover

Signs: an unknown username, the right password reported wrong, your 2FA codes no longer accepted, a "settings file changed outside Javis" alert, or an unknown device in the Security tab. In this order:

1. **Take the account back.** On Hostinger: add `JAVIS_ADMIN_USER` and `JAVIS_ADMIN_PASSWORD` (a NEW password) in the Environment box and redeploy. Javis resets the account, keeps 2FA and signs out every old session.
2. **2FA is not yours?** Add `JAVIS_RESET_2FA=1` in the same step. Javis removes 2FA once at startup. It applies once per value; to use it again later, set another value, such as the date (`JAVIS_RESET_2FA=2026-11-09`).
3. **Sign in, open Account > Security.** Read the sign-in history (IP, device, time) and press **Sign out all other devices**.
4. **Turn 2FA on again** with your phone and keep the 8 recovery codes somewhere safe.
5. **Remove `JAVIS_ADMIN_PASSWORD` and `JAVIS_RESET_2FA` from the Environment box** and redeploy. The account is not affected. The password sits there in plain text, so do not leave it.
6. **Find how they got in.** Whoever edited the settings file had access to the server: look for unknown SSH keys (`cat /root/.ssh/authorized_keys`), change the root password (`passwd`), change the password of the Hostinger account and turn on its 2FA, block port 7777 at the firewall once an HTTPS domain works.
7. **Rotate the connection keys** stored in Javis (POS, Cloudflare, Gmail, Zalo, API keys), money and customer data first: someone on the server may have read them.
8. **Look for anything left behind**: unknown recurring jobs, reminders, agents, plugins, MCP servers; on the server run `crontab -l`.

From this version the Hostinger compose closes port 7777 to the Internet once `DOMAIN_NAME` is set (HTTPS through the domain only). Without a domain the port stays open as before, since it is the only way in.

## Blocking CSRF and DNS rebinding

This layer runs in the background and needs nothing turned on, but it is worth knowing about because it is occasionally the culprit behind a puzzling 403.

The problem it solves: the dashboard listens on `localhost:7777`. When you have **not** set a password, any web page open in your browser can still fire a POST request at `http://localhost:7777/...`. The browser stops that page from READING the result, but it does not stop the request from running, so the action still happens. An attacker can also point one of their domains at `127.0.0.1` to slip past origin checks.

Javis blocks both paths with a gate standing in front of the login gate itself:

| Case | Handling |
|---|---|
| A WRITE request (POST/PUT/DELETE/PATCH) with an `Origin` different from Host and not on the allowlist | Blocked, 403 with "cross-origin request blocked" |
| A request arriving with an unknown domain (Host) while the login gate is **not** on | Blocked, 403 with "host not allowed" |
| Same origin (Origin matches Host) | Allowed |
| A non-browser client (no `Origin` sent, for example the CLI, curl, MCP) | Allowed |
| Host is an IP address | The Host check is skipped |

The allowlist contains: `localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, plus the custom domain you set in **Settings → Domain and SSL**, plus every name in the `JAVIS_ALLOWED_HOSTS` environment variable (comma separated).

When you might need to touch this: running Javis behind a reverse proxy on a domain not declared in the app, while **no** password is set. Javis then treats that domain as unknown and returns 403. The fix: set a password (turning the login gate on makes the Host check step aside), or add the domain to `JAVIS_ALLOWED_HOSTS`.

## Blocking search engines and AI bots

This layer also runs in the background and needs nothing turned on. It is for the day the admin link gets out: pasted into a group chat by mistake, listed in the public SSL certificate logs, or found by an Internet scanner. Google then keeps the page out of its results, and AI bots read nothing, not even the login screen.

| Layer | What it does |
|---|---|
| `X-Robots-Tag: noindex` header | Sent with EVERY answer from Javis (login page, share links, error pages), so any page a search engine does reach is dropped from its results. |
| `/robots.txt` | Tells AI bots (GPTBot, ClaudeBot, PerplexityBot, CCBot...), SEO tools and every unknown robot to fetch nothing. |
| 403 answer | A request that calls itself an AI bot, search engine, SEO tool or scanner (Shodan, Censys), or signs as a bot (`Signature-Agent`), gets 403 and sees none of the page. |

Never blocked: real people's browsers (including the ones inside Zalo, Facebook and Coc Coc), link previews when a link is pasted into Zalo, Telegram, Facebook, Slack or Discord, webhooks and OAuth callbacks from outside services, Javis Gate (ChatGPT and Claude calling into Javis), the CLI, `curl` and tools running on this machine.

Why `robots.txt` does not block Google: Google can only remove a page it is able to read. Blocked by `robots.txt`, Google never reads it, never sees `noindex`, and can still show the bare link in results when another page points to it. Letting Google in and answering 403 with `noindex` is what removes the link for good.

Quick check against your server (change the domain):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -A GPTBot https://your-domain/
```

It must print `403`. A browser still opens the page as usual.

This layer only catches bots that NAME themselves. A bot posing as Chrome still only sees the login screen, so the password and 2FA remain the main protection. If a service you use is blocked by mistake because its name is on the list, set `JAVIS_BLOCK_BOTS=0` and restart: only the 403 layer turns off, the `noindex` header and `robots.txt` stay.

## API tokens, the door for CLI and scripts

The login cookie only suits a browser. When you want [the Javis CLI](24-cli.md) or a script to call Javis, you need a different credential: an **API token**, created at **Integrations > API token (for the CLI)** (Work group, the same page as webhooks: both are doors for another program to call Javis).

The most important point: **no token exists by default**. Until you click create yourself, no token exists and there is no door in except the browser. Opening another door to the Internet has to be a deliberate act.

How Javis keeps tokens:

| Rule | Why |
|---|---|
| Two scopes: **chat only** and **full power** | The chat-only level follows a WHITELIST (`/chat`, `/version`, `/health`, `/sessions`). Whitelisting rather than blacklisting, because a blacklist means every new endpoint added to Javis is automatically exposed to the narrow token. |
| Only a SHA-256 hash is on disk | Whoever can read the server's config file still cannot obtain the token. The raw string is shown exactly once, at creation. |
| Comparison with `compare_digest` | Ordinary string comparison exits early at the first differing character, and that timing difference is enough to guess a token character by character. |
| The token travels in the `Authorization` header, never in the query string | Query strings end up in the logs of every proxy along the way. |
| **A token cannot create a token** | Creating a token requires a browser session. Without this rail, one leaked token lets whoever holds it mint more tokens forever, and revoking the leaked one becomes meaningless. |
| But a token **can revoke itself** | Losing a laptop with no way to open a browser still has to let you take the credential down immediately. |
| More than 10 failures in 5 minutes blocks that IP for 15 minutes | Recorded in `auth_audit.jsonl`, only the first 12 characters (log files are often attached to bug reports). A token-guessing run becomes visible instead of running silently for months. |

The token list shows each token's **last used** time. If you see a token you do not recognise being used regularly, revoke it at once; revocation takes effect immediately and cannot be undone.

## Secrets in settings.json are encrypted

Sensitive fields in `settings.json` are not stored in plain text. Javis encrypts them with Fernet (AES-128-CBC + HMAC) before writing to disk and decrypts them on read. An encrypted value carries the `enc:` prefix.

The encrypted fields:

| Field | What it is |
|---|---|
| `model.openrouter_key` | OpenRouter API key |
| `model.anthropic_api_key` | Anthropic API key |
| `model.openai_api_key` | OpenAI API key |
| `model.gemini_api_key` | Google Gemini API key |
| `model.openai_oauth.access_token` / `refresh_token` / `id_token` | ChatGPT sign-in tokens |
| `telegram.token` | Telegram bot token |
| `backup.token` | The GitHub PAT used for brain backup |
| `voice.elevenlabs_key` | ElevenLabs API key |

The encryption key lives in the **`.secret_key`** file in the state folder (`JAVIS_STATE_DIR`, Docker: `/data/state/.secret_key`). The file is generated once and never goes into git.

Operational consequences worth remembering:

- **Copying `settings.json` to another machine while forgetting `.secret_key` loses every key.** Javis sees `enc:` but cannot decrypt it, so it returns an empty string and you must re-enter every key. This is a deliberate trade-off: better to force re-entry than to leave keys exposed.
- **Back up the pair together**, `settings.json` + `.secret_key`, and keep them equally private.
- If the machine lacks the `cryptography` library, Javis cannot encrypt: secrets fall back to the `plain:` prefix and the server prints a warning to the log. Install it with `pip install cryptography` and restart to bring encryption back.
- Older values without a prefix (saved before encryption existed) still read normally and are wrapped in `enc:` on the next write.

## How the security works (for those who want the depth)

| Mechanism | What actually happens |
|---|---|
| Password storage | The raw password is never stored. Javis hashes it with PBKDF2-HMAC-SHA256 (120,000 rounds) with a random salt. |
| Login session | Granted through the `javis_session` cookie, marked `httponly` (JavaScript cannot read it) and `samesite=lax`. |
| Session expiry | Each session lives at most **30 days** then expires and requires signing in again. |
| Sessions across restarts | Sessions are written to a file, so **restarting the server does not sign you out**. |
| Brute-force protection | Failure counts are kept per IP. Enough consecutive failures (8) locks that IP for about 5 minutes; every failure is slowed by half a second. When locked, Javis reports too many failed attempts and asks you to retry in a few minutes. |
| Secure cookie on HTTPS | When you use a **custom domain** with HTTPS on (Caddy On-Demand TLS), the cookie is marked `secure` (only sent over HTTPS). |
| CORS | Only open to `localhost` / `127.0.0.1` / `::1` (convenient during development). Other web pages cannot read the API from a browser. |
| The CSRF gate | Blocks cross-origin write requests, and blocks unknown Hosts while login is off (see the dedicated section above). |
| Bot blocking | `noindex` on every answer, `/robots.txt`, and 403 for self-declared AI bots, search engines, SEO tools and scanners (see the dedicated section above). |
| Secrets on disk | API keys and tokens in `settings.json` are Fernet-encrypted with `.secret_key` in the state folder. |

About the `secure` cookie: by default Javis does **not** force it, so it runs over both HTTP and HTTPS (avoiding a login loop behind an HTTP proxy such as a path-style `http://host/PORT/`). If you are certain you run HTTPS end to end, set `JAVIS_SECURE_COOKIE=1` in the environment (see [.env configuration](16-env-configuration.md)). Accessing through the proper custom domain makes Javis enable `secure` on its own without that variable (based on the Host matching the domain, not inferred from `X-Forwarded-Proto`).

## Quick reference of buttons and states

| Button / message | Where | What happens |
|---|---|---|
| **Set password** | Account → Login account (when no password exists) | Creates the admin account and grants you a session right away |
| **Change password** | Same place, once a password exists | Changes the password and/or username. The current password is required; afterwards every other session is signed out |
| **Sign out** | Account → Login account | Deletes this browser's session and reloads the page |
| **Turn login off** | Account → Login account | Deletes the password and signs out every session (asks for confirmation first) |
| **Save** | Account → Workspace | Renames the displayed workspace |
| 🔒 Password set · account: ... | Login account | An admin exists, the username appears right after the colon |
| No password set, anyone opening the dashboard can use it. Set a password before putting it on a VPS. | Login account | No admin yet |
| ✅ Account saved. | Login account | The password was set successfully |
| ⚠ Password must be at least 8 characters. | Login account | The interface blocks before sending, at the same threshold as the server |
| ⚠ Current password is wrong. | Login account | The **Current password** field was typed wrong, nothing was changed |
| **Forgot your password?** | Sign-in screen | Clicking it explains how to delete the `"auth"` block in `server/settings.json` and restart |

## Tips

- **Always set the admin before going public.** The surest way is setting `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` at deploy time, so the server is never without an admin.
- **Use a long enough password.** At least 8 characters; a long, hard to guess phrase is better.
- **Run over HTTPS for remote access.** Use a custom domain (a Hostinger `*.hstgr.cloud` name, say) or Cloudflare Tunnel rather than exposing raw port 7777 to the Internet. How to point a domain and enable HTTPS: [Branding and custom domains](15-branding-and-domains.md).
- **Localhost plus a tunnel you run yourself means setting `JAVIS_REQUIRE_LOGIN=1`.** When the machine only listens on localhost but you run a tunnel (cloudflared, ngrok...) outside Javis, Javis cannot tell it is public, so force login manually. The **Remote access** section in Settings does not need this: Javis knows its tunnel is on, forces login and only runs it once a password is set.
- **Turn on two-factor (2FA) right after the first sign-in.** If the password leaks, a stranger still lacks the TOTP code on your phone.
- **Back up `.secret_key` alongside `settings.json`.** Missing either one means re-entering every API key.

## Common problems

**Clicking Change password reports "an account already exists, please sign in".**
A bug in versions before 0.28.3, now fixed. If the open page still holds the old build in the browser cache, reload with Ctrl+F5 (Cmd+Shift+R on a Mac) and repeat section C.

**After changing the password, the phone (or another machine) asks to sign in again.**
By design. Changing the password destroys every old session so someone borrowing your machine cannot keep using it; sign in again with the new password and you are done.

**The correct user and password still bounce back to the sign-in screen (a login loop).**
Usually the `secure` cookie is on while you access over HTTP (many proxies serve HTTP as a path-style `http://host/PORT/`). Do not set `JAVIS_SECURE_COOKIE` unless you are certain of end-to-end HTTPS. If you already did, remove the variable and restart the server.

**You get "too many failed attempts, try again in a few minutes".**
You (or someone on the same IP) got the password wrong too many times. Wait about 5 minutes and try again. Restarting the server also clears the counter.

**Everything returns 403 "host not allowed".**
You are reaching Javis through a domain it does not know, while no password is set. Add that domain to `JAVIS_ALLOWED_HOSTS`, or enter it under **Settings → Domain and SSL**, or simply set a password.

**Everything returns 403 "cross-origin request blocked".**
You are calling the Javis API from another page (a script, an extension, a third-party iframe). This is the CSRF layer doing its job. If it is your own tool, add its hostname to `JAVIS_ALLOWED_HOSTS`.

**You forgot the password.**
On Docker or Hostinger (since 0.77.1): change `JAVIS_ADMIN_PASSWORD` (and `JAVIS_ADMIN_USER` if you like) in the Environment box and redeploy. At startup Javis sees the env value differs from last time and resets the admin to it; 2FA stays on and every old session is signed out. Leaving the env unchanged changes nothing, so a password you set in the dashboard is not overwritten on every restart.

On Windows the repo ships a **`reset-auth.bat`** script in the project root: running it clears the account and password in `server/settings.json` and returns the app to setup (it prints an OK line then tells you to restart). If the script is not usable: edit or delete the `auth` section of `settings.json` in the state folder (Docker: `/data/state`) then restart; or set the admin again with `JAVIS_ADMIN_PASSWORD` after deleting the old `auth` section.

**After changing machines or restoring a backup, every API key is empty.**
You copied `settings.json` without `.secret_key`. There is no recovery: re-enter the keys on the Models page, the Admin channels page and Settings. Next time bring both files.

**Login is turned off but it still asks for an account.**
Because the server is still public (or `JAVIS_REQUIRE_LOGIN=1`). In that mode Javis does not allow login to be turned off entirely, it forces the account to be recreated. To run without a password the server must listen purely on localhost.

## Related

- [Getting started and first setup](01-getting-started.md) - standing Javis up and creating the first admin.
- [Branding and custom domains](15-branding-and-domains.md) - pointing a domain and enabling automatic HTTPS.
- [.env configuration](16-env-configuration.md) - the list of security environment variables (`JAVIS_HOST`, `JAVIS_REQUIRE_LOGIN`, `JAVIS_ADMIN_USER/PASSWORD`, `JAVIS_SECURE_COOKIE`, `JAVIS_ALLOWED_HOSTS`, `JAVIS_STATE_DIR`).
- [Plugins](20-plugins.md) - why plugins you install yourself must be enabled through an environment variable.
- [The Javis CLI (terminal)](24-cli.md) - using an API token to call Javis from another machine.
- [Troubleshooting and FAQ](17-troubleshooting.md) - other common errors.
