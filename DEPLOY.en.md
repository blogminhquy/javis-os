# Installing Javis OS on a server / VPS

*[Tiếng Việt](DEPLOY.md) · **English***

Javis OS is a personal AI agent plus a Second Brain. Its "brain" is the **Claude Code CLI**
(sign in once, no API key needed). There are 3 ways to run it, pick one.

> ⚠️ **Safety:** Javis runs Claude with full power on the machine. When running public
> (Docker/VPS/Hostinger), Javis **turns forced login on by itself**, so opening the app gives the
> **create admin / sign in** screen and nobody can drive it before a password exists. (To turn that
> off for internal use: `JAVIS_REQUIRE_LOGIN=0`.)

---

## Way 1 - Hostinger Docker Manager (1-click, the fastest) ⚡

On the Hostinger VPS go to **Docker Manager → Compose → URL**, paste the link and **Deploy**:
```
https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml
```
Hostinger pulls the image and runs it. Open the app at `http://<vps-ip>:7777` (the IP is in
hPanel → VPS) and you get the **create admin account** screen.

> 🌐 **Want a PRIVATE LINK with HTTPS (dropping `:7777` so the mic and voice work) WITHOUT buying a
> domain?** Use `docker-compose.hostinger.yml` and set `DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud`;
> see **"The default link + HTTPS on Hostinger"** in the HTTPS section below. This base compose file
> is only reachable by IP:7777.

**3 things to do once:**
1. **Set the GHCR image to Public:** GitHub → the `javis-os` repo → **Packages** → `javis-os`
   → *Package settings* → Visibility = **Public** (so Hostinger can pull without a registry login).
   The image is built by CI on every push to `main` (see the Updates section).
2. **Create the admin account safely** (Claude runs at full power, so account creation must not be
   open to everyone):
   - **Way A (recommended):** in the Hostinger compose, fill the two existing fields
     `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD`, and the admin is created at startup so opening
     the app takes you **straight to sign-in**.
   - **Way B:** leave them empty and the app asks for a **SETUP TOKEN**. Get it in the **App
     terminal** (which is INSIDE the container so it has NO `docker` command): run
     `cat /data/state/.setup_token`, copy the string and paste it into the create-account screen.
     (Only someone who can see the file or the log can create the admin, so whoever merely has the
     URL is stuck.)
3. **Sign Claude in (the brain) once:** open the **App terminal** and run:
   `claude auth login --claudeai`, open the link, paste the code. (The token lives in a volume and
   survives updates.)

---

## Way 2 - Docker on any VPS (pull the image, no source clone needed)

Docker is required. Do not have it? `curl -fsSL https://get.docker.com | sh`
```bash
mkdir javis && cd javis
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml

docker compose run --rm javis claude auth login --claudeai   # SIGN CLAUDE IN ONCE (link + code)
docker compose up -d                                          # pull the GHCR image and run
```
Open `http://<vps-ip>:7777` (or through a tunnel, below) and you get the create-admin screen.
To build from source instead of pulling: `curl -O .../docker-compose.build.yml` then
`docker compose -f docker-compose.build.yml up -d --build`.

Everyday commands:
```bash
docker compose logs -f     # see what Javis is doing
docker compose restart     # restart
docker compose down        # stop
docker compose build --pull && docker compose up -d   # update
```

Every note, vault and setting lives in Docker volumes (`javis-data`, `claude-auth`), so
**nothing is lost** on a restart or an update.

### 🔒 Automatic HTTPS

> ⚠️ **Voice and the mic REQUIRE HTTPS.** Browsers only grant microphone and camera permission over
> `https://` (or on localhost), so opening `http://<ip>:7777` always blocks the mic with no manual
> override. **No HTTPS certificate is issued for a bare IP**, so making the mic work means one of the
> ways below (a domain or a tunnel).
>
> **The fastest (no domain needed), a Cloudflare Tunnel:**
> ```bash
> docker compose --profile tunnel up -d
> docker compose logs tunnel | grep trycloudflare
> ```
> then open the `https://...trycloudflare.com` URL and the mic and voice work. (The URL changes on
> every restart; for a stable one use a *named tunnel* plus `TUNNEL_TOKEN`, see the Cloudflare Tunnel
> section below.)

#### 🌐 A domain + HTTPS on Hostinger (NO domain purchase needed)

Hostinger provides **wildcard DNS** `*.<vps-hostname>.hstgr.cloud` plus **Traefik** issuing SSL
automatically. So you get a private link on HTTPS without buying a domain. **Note (verified):** Hostinger
does **NOT** provide the `TRAEFIK_HOST` variable for a hand-pasted compose (only for Catalog apps), so
you **must set a `DOMAIN_NAME` variable**:

1. Find the **VPS hostname** in hPanel → VPS (for example `srv1782015.hstgr.cloud`).
2. Docker Manager → Compose → URL:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. The new template's **Environment** box has only 3 meaningful fields:
   - `DOMAIN_NAME`: set `javis.<vps-hostname>.hstgr.cloud`
     (for example `javis.srv1782015.hstgr.cloud`), or your own domain with an A record pointed at the
     VPS IP.
   - `JAVIS_ADMIN_USER`: the username, `admin` by default.
   - `JAVIS_ADMIN_PASSWORD`: a strong password you choose; leaving it empty means using the SETUP
     TOKEN the first time.

   The older technical fields such as `JAVIS_HOST`, `JAVIS_PORT`, the state and brain paths and
   `CLAUDE_CWD` have been cleared from the form; the Docker image still uses the right defaults.
4. **Deploy**, wait 1-3 minutes for Traefik to issue SSL, then open `https://<DOMAIN_NAME>`.

> Without `DOMAIN_NAME` it still deploys (running temporarily on `:7777` with no HTTPS). No Environment
> box? Click **Manage → edit the .yaml** and change the `Host(...)` line directly to
> `Host(\`javis.srv1782015.hstgr.cloud\`)`.
> **The key point:** the Traefik labels attach straight to the service, with **NO
> `networks:` / `external: traefik-proxy` declaration** (that is what used to make the deploy report
> "network not found").
> **Caddy (`docker-compose.https.yml`) is NOT used on Hostinger** because ports 80/443 are already held
> by their Traefik.
> Not confident? Use a **Cloudflare Tunnel** (below), which gives an HTTPS URL without touching
> Hostinger's proxy at all.

**A VPS with your own domain, automatic Let's Encrypt, configured RIGHT IN THE APP (recommended):**

You no longer set `DOMAIN` at run time; enable Caddy once then declare the domain in the interface.
1. Enable Caddy (On-Demand TLS): `docker compose -f docker-compose.yml -f docker-compose.https.yml up -d`
   *(needs Docker Compose v2.23.1+, check with `docker compose version`)*
2. Open `http://<vps-ip>:7777` → **Settings → Voice, branding and access → Domain and SSL** → enter
   `javis.yourname.com` → **Save and check**.
3. The wizard shows the exact DNS record to create (A: `javis.yourname.com → <vps-ip>`) with a copy
   button. Point the DNS then wait for propagation.
4. Open `https://javis.yourname.com` and Caddy **obtains and renews** the certificate on the first
   visit, with the Secure cookie turned on automatically. Done.

> Safety: Caddy asks the backend (`/tls-check`) before requesting a certificate, so it **only** issues
> for the domain you entered in the app. Someone pointing arbitrary DNS at the IP cannot force the
> server into requesting random certificates (which would exhaust the Let's Encrypt rate limit).
> Changing or removing the domain: edit it in ⚙ Settings, with **no** compose command to rerun.

**No domain:** use the Cloudflare Tunnel right below (which also gives an HTTPS URL).

---

## 🏢 Running SEVERAL Javis instances on one VPS (each with its own link)

One VPS can run any number of Javis instances, each on its own subdomain with its own data store,
and no instance sees another's brain or accounts.

**Three things must DIFFER between instances.** Whichever one collides is what breaks:

| Variable | Why it must differ | What a collision causes |
|---|---|---|
| `JAVIS_NAME` | Docker names containers machine-wide | `name is already in use`, the second instance never starts |
| `JAVIS_HOST_PORT` | One host port can only be held by one container | `port is already allocated` |
| `DOMAIN_NAME` | Each link must point at exactly one instance | Two instances fighting over one link |

Leaving all three empty gives `javis` plus port `7777`, which is **exactly the old install**, so
running a single instance needs no change at all.

### On Hostinger Docker Manager

Deploy `docker-compose.hostinger.yml` **once more** as a new stack, filling in the Environment:

```
Stack 1:  DOMAIN_NAME=shop.srv1782015.hstgr.cloud     (JAVIS_NAME, JAVIS_HOST_PORT left empty)
Stack 2:  DOMAIN_NAME=canhan.srv1782015.hstgr.cloud   JAVIS_NAME=javis-canhan   JAVIS_HOST_PORT=7778
```

The wildcard DNS `*.hstgr.cloud` is already there so any subdomain resolves immediately, and Traefik
issues SSL itself.

### On a self-managed VPS (Docker plus a shared proxy)

A machine has only **one port 443**, so Caddy must live OUTSIDE every instance. Run the proxy **once
for the whole machine**:

```bash
docker network create javis-web
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.proxy.yml
docker compose -f docker-compose.proxy.yml -p javis-proxy up -d
```

Then give each instance **its own folder**:

```bash
mkdir -p ~/javis-shop && cd ~/javis-shop
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.multi.yml
cat > .env <<'EOF'
JAVIS_NAME=javis-shop
JAVIS_HOST_PORT=7777
JAVIS_BIND=127.0.0.1
DOMAIN_NAME=shop.yourname.com
JAVIS_ADMIN_USER=admin
JAVIS_ADMIN_PASSWORD=your-strong-password
EOF
chmod 600 .env

CF="-f docker-compose.yml -f docker-compose.multi.yml"
docker compose $CF run --rm javis claude auth login --claudeai   # sign Claude in for THIS instance
docker compose $CF up -d
```

Do the same for the second instance in `~/javis-canhan`, changing `.env` to `javis-canhan` / `7778` /
`canhan.yourname.com`. Point an A record for each subdomain at the VPS IP and you are done: the proxy
**discovers new instances through Docker labels**, so nothing on the proxy needs editing and it does
not need restarting.

> Each instance has its own admin account, so set `JAVIS_ADMIN_*` in **each** `.env` (with different
> passwords). Leaving them empty drops that instance back to the old route: reading the SETUP TOKEN
> from `docker compose logs`.

> `JAVIS_BIND=127.0.0.1` pulls the port back to loopback because the proxy handles HTTPS. You can
> still get in to debug with `ssh -L 7777:localhost:7777 user@<vps-ip>` while DNS has not propagated.

**Updating** is still `./update.sh` in each folder; the script reads the `.env` of the folder you are
standing in so it only touches that instance. If the first instance runs `docker-compose.https.yml`
(with Caddy inside the project), move it to `docker-compose.multi.yml` before standing up the second
one, or two Caddys will fight over port 443.

### A native install (no Docker)

Clone into a different folder then set two variables before running:

```bash
JAVIS_NAME=javis-shop JAVIS_PORT=7778 ./install.sh
```

The systemd service becomes `javis-shop.service` (`journalctl -u javis-shop -f`) rather than
overwriting the previous instance's `javis.service`. HTTPS is handled by whichever nginx or Caddy the
machine already runs.

### What is shared and what is private

**Private to each instance:** the brain, the notes, the settings, the admin account, the MCP
connections, the background work, and **the Claude/ChatGPT login token** (each instance needs its own
`claude auth login`).

**Shared:** nothing. To have two instances share one Claude login, point them at the same
`claude-auth` volume; that works but is at your own risk, because both will burn the same quota.

---

### 🌐 Remote access (Hostinger / any VPS) with a Cloudflare Tunnel

Open the Javis interface from another machine with NO open ports and NO domain:

1. **Set a password FIRST (mandatory):** open Javis (through the SSH tunnel in step 5) → Dashboard →
   **Account** → set the admin password. Javis runs Claude with full power on the machine, so it must
   NEVER be exposed to the Internet without a password. (The server also prints a warning when running
   public without one.)
2. Start the tunnel: `docker compose --profile tunnel up -d`
3. Get the URL: `docker compose logs tunnel | grep trycloudflare`, then open
   `https://<random>.trycloudflare.com` in any browser and sign in with the password. Now you can view
   and drive Javis remotely.

**A stable URL (your own domain, `*.hstgr.cloud` style):** create a *named tunnel* in Cloudflare Zero
Trust (free), take the token, put `TUNNEL_TOKEN=...` into `.env`, change the `tunnel` service's
`command` line to the `run --token` variant (commented out in `docker-compose.yml`), and point it at
`http://javis:7777`. A quick tunnel changes its URL on every restart; a named tunnel gives a stable one.

---

## Way 2 - Installing directly on Linux/macOS (no Docker)

```bash
git clone https://github.com/blogminhquy/javis-os.git javis && cd javis
chmod +x install.sh && ./install.sh
```

The script installs Python, Node and the Claude CLI, creates a venv, installs dependencies, registers
a service to start at boot (systemd) and prints the address. If it reports that Claude is not signed
in, run once:
```bash
claude auth login --claudeai
```
Managing the service: `journalctl -u javis -f` · `sudo systemctl restart javis`

---

## Way 3 - Windows (a personal machine)

Double-click `setup.bat` (which shows a window) or `start-javis.vbs` (which runs in the background).
Stop it with `stop-javis.bat`. Open http://localhost:7777

---

## Environment variables (`.env`)

| Variable | Meaning | Default |
|---|---|---|
| `JAVIS_HOST` | The listening address. `127.0.0.1` = this machine only; `0.0.0.0` = everywhere (Docker sets this itself) | `127.0.0.1` |
| `JAVIS_PORT` | The port | `7777` |
| `JAVIS_STATE_DIR` | Where Javis writes state (settings, sessions, loop configuration) | `server/` (Docker: `/data/state`) |
| `OBSIDIAN_VAULT_PATH` | The main Second Brain vault | `vault/` in the repo (Docker: `/data/vault`) |
| `BRAIN_PATH` | The brain folder | `brain/` in the repo (Docker: `/data/brain`) |
| `CLAUDE_CWD` | The Claude CLI's working folder | the repo root |

---

## 🔄 Updating when new code lands

> **The fastest, right in the app:** open **Updates** (the left rail) and the **Javis OS** panel shows
> the running version and checks GitHub for a newer one. When there is one, click **⬆ Update now** and
> the app pulls the new version and restarts (~20-40s), with no terminal needed.
> - **Docker/VPS:** the **watchtower** service is required. It IS in `docker-compose.yml` but sits
>   under `profiles: ["update"]`, meaning **`docker compose up -d` does not start it**. That is the most
>   common reason one machine has the button and another does not. Start it once:
>   ```bash
>   docker compose --profile update up -d
>   ```
>   Only Watchtower is granted Docker access (the socket); the Javis app is NOT, which is what makes it
>   safe. Not starting it is fine too, and the panel then only *reports a new version* and explains how
>   to update by hand.
> - **Native/Windows:** the button runs `update.sh` (git pull plus restart) for you.

The repo and the GHCR image are both **Public**, so `git clone`/`pull` and `docker pull` need no login.

Whenever you push new code, on the VPS all you need is:

```bash
cd javis && ./update.sh
```

The script runs `git pull` then:
- **Docker**: `docker compose build && docker compose up -d`, and data in the volumes is NOT lost.
- **Native (systemd)**: `pip install -r requirements.txt` plus `systemctl restart javis`.

To force a mode: `./update.sh docker` or `./update.sh native`. The manual equivalent:
```bash
git pull && docker compose build && docker compose up -d          # Docker
git pull && ./.venv/bin/pip install -r requirements.txt && sudo systemctl restart javis   # Native
```

On your Windows machine, pushing code to GitHub: `git add -A && git commit -m "..." && git push`

Leaving variables empty uses the in-repo defaults, so an install on a new machine runs immediately with
nothing to edit.

---

## Signing Claude in is the only mandatory step

Javis's "brain" is the Claude Code CLI. The login token lives in `~/.claude`
(Docker: the `claude-auth` volume). Sign in once and it survives every restart and update.
If you already signed in on another machine, you can copy the `~/.claude` folder across.

## (Optional) Using ChatGPT (the Plus plan) in chat

The **OpenAI OAuth (ChatGPT)** provider chats through the **Codex CLI** (already installed in the
image). Sign in once: open the **App terminal** and run `codex login` (opening the link and signing
into ChatGPT). The token lives in `~/.codex` (Docker: the `codex-auth` volume) and survives every
update. Check it with `codex --version`. Then go to **Models → Change model → ChatGPT** and chat works.
(ChatGPT-through-codex is experimental; for something more stable or with more models, use
**OpenRouter**, one key for every model, or Claude.)
