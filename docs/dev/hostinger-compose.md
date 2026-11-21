# Why docker-compose.hostinger.yml looks the way it does

The comments inside `docker-compose.hostinger.yml` are short on purpose. hPanel's compose editor
refuses to Deploy a file over 32,768 characters (owner report 2026-11-14), and Hostinger does not
say how it counts: plain characters, bytes, or the text once it is encoded for transport. In the
encoded form every non-ASCII letter costs six characters, so Vietnamese comments made the file far
larger than it looked: 28,386 characters on disk, but 35,485 once encoded (2026-11-21, after the
owner reported that the Hostinger link failed again while `docker-compose.yml` deployed fine).

Rules for that file:

- Comments are short, in English, ASCII only. `tests/python/test_hostinger_compose_size.py` fails
  when a non-ASCII character appears or when any way of counting goes over the budget.
- The reasons live here. Add to this page, not to the compose file.
- Never shorten the settings themselves to save space.
- The `guard` service carries a compact copy of `docker/guard.py`, written by `tools/sync_guard.py`.
  Edit `docker/guard.py`, then run the tool.

## Service `javis`

**Names come from `JAVIS_NAME`.** The container name and the Traefik router and service names all
use `${JAVIS_NAME:-javis}`. A second instance on the same VPS needs another name (for example
`javis-shop`): otherwise Docker reports the container name as taken, and Traefik, whose router
names are machine-wide, keeps only one of two routers with the same name, so one domain dies.

**The Hostinger target is set inside `command`.** `JAVIS_DEPLOY_TARGET=hostinger` is part of the
command line instead of `environment`, so it does not become a useless field in Docker Manager's
Environment form. For the same reason the environment block lists only what an installer needs:
port, paths, state and brain already have the right defaults in the image.

**`WATCHTOWER_TOKEN` is hard-coded.** Every `${...}` in the file adds a field to the Environment
form, and nobody needs to change this token: Watchtower's port 8080 is not published, only
containers of the same stack can reach it. An installer who wants their own token uses
`docker-compose.yml`, which reads `WATCHTOWER_TOKEN` from the environment.

**The published port (security incident 2026-11-09).** `7777` is the fallback entry: hPanel's Open
button and `http://<ip>:7777`. Once `DOMAIN_NAME` is set, the port listens on `127.0.0.1` only.
Traefik reaches Javis over the Docker network and the Caddy gateway over `127.0.0.1`, so HTTPS
keeps working, while the unencrypted `http://<ip>:7777` path, where the password travels in the
clear, is closed. With `DOMAIN_NAME` empty the port stays open to the outside, because it is the
only way in. If the domain has no HTTPS yet and access is urgent: clear `DOMAIN_NAME` and Redeploy,
and the port opens again. A second instance must use another host port (`JAVIS_HOST_PORT=7778`).

**Traefik labels and the Open button (0.302.0).** hPanel's Open button follows the concrete
`Host(...)` rule in the labels. Older versions wrote `Host(`localhost`)` when `DOMAIN_NAME` was
empty, so Open led to localhost on the visitor's own machine (owner report 2026-10-24). Now, with
`DOMAIN_NAME` empty, `traefik.enable` and the router rule are both empty: Traefik skips the
container, no route exists for "localhost", and hPanel falls back to the published port, that is
`http://<vps-ip>:7777`. The compose syntax `${VAR:+text}` prints the text only when the variable
has a value.

## Service `watchtower`

It makes the in-app **Update now** button work, and has shipped in this file since 0.55.56.

History, because it explains why the block was once missing: the 2026-07-18 version tried it and
removed it again, since on Docker Manager the Watchtower container kept restarting and the stack
showed "Partially running". The guess at the time, "it cannot reach the Docker socket", was wrong.
The real log, measured again on a Hostinger VPS on 2026-10-01, was:

```
client version 1.25 is too old. Minimum supported API version is 1.40
```

The old image `containrrr/watchtower` speaks Docker API 1.25 by default and current Docker Engine
refuses it. That repository has been archived (read-only since 12/2025), so it will never be fixed
there. The file now uses the maintained fork `nicholas-fedor/watchtower`, which negotiates the API
version with Docker and keeps the same port 8080 and the same `POST /v1/update` with a Bearer token
that the app calls. It is pinned to major `:1` so that a v2, which drops the old HTTP API
variables, cannot arrive on its own and kill the button again. Do not patch the old image with
`DOCKER_API_VERSION=1.40`: Docker keeps raising its minimum.

What does not change: Javis runs normally even when Watchtower is broken. It is a separate
container, so a failure costs only the button. On "Partially running", read the log of the
`javis-watchtower` container; if it cannot be fixed, update with Redeploy as before. The Updates
page in the app says the same.

Settings worth knowing:

- `WATCHTOWER_HTTP_API_PERIODIC_POLLS: ${JAVIS_AUTO_UPDATE:-false}` is the fourth Environment
  field and the only `${...}` added for Watchtower. It is an installer's choice, not a technical
  default: when on, Javis restarts whenever a new version exists, cutting background work and open
  chats. Empty means off, and updates happen through the button.
- `WATCHTOWER_HTTP_API_UPDATE_TIMEOUT: 30m`: the default 10 minutes ran out on a slow disk.
- No `traefik.*` routing labels: it is an internal container with nothing to expose.
- `command: ${JAVIS_NAME:-javis}`: it watches this instance's container only. With a fixed
  `javis`, the Watchtower of one instance would update and restart the container of another.

## Service `gateway` (0.300.0)

Owner question 2026-10-24: Hostinger's "Ubuntu 24 + Docker" template ships Traefik on ports 80 and
443 and issues SSL through the `traefik.*` labels, while the plain Ubuntu 26 template has no
Traefik at all. Before 0.300.0, pasting the compose link on Ubuntu 26 gave a running Javis whose
`DOMAIN_NAME` never got HTTPS, since nothing read the labels, and the installer had to know how to
add a Caddy file by hand. Now one link serves both:

- Another proxy holds 80/443 (Hostinger's Traefik): the gateway stays idle and Traefik issues SSL.
- Ports 80/443 are free (Ubuntu 26, an empty VPS): the gateway runs Caddy, which requests and
  renews a Let's Encrypt certificate for `DOMAIN_NAME` and forwards to Javis on the instance's
  host port.
- `DOMAIN_NAME` is empty: the gateway uses the VPS's own name (`srv<id>.hstgr.cloud`) when there
  is one, otherwise it stays idle and Javis is reached at `http://<ip>:7777`.

**Why `network_mode: host` and not published ports.** Publishing `80:80` and `443:443` while
Traefik holds them makes Docker report "port is already allocated" and the whole stack fails to
deploy on Ubuntu 24. On the host network Docker claims no port. The script inspects the ports
first and starts Caddy only when both are free. While they are busy it looks again every 10
minutes, so removing Traefik lets the gateway take over without a Redeploy.

**Certificates.** Caddy requests a certificate for exactly `DOMAIN_NAME`, never on demand, so
someone pointing random DNS names at the IP cannot make it request certificates. The
`gateway-data` volume keeps issued certificates across Redeploy, which avoids new requests and the
Let's Encrypt rate limit.

**No new Environment field.** The gateway only reads `DOMAIN_NAME`, `JAVIS_HOST_PORT` and
`JAVIS_NAME`, which already exist.

**The status volume (0.304.0).** The gateway writes what it is doing (idle, busy or serving, plus
the names it serves) into `gateway-status`. Javis mounts it read-only, so the page opened by IP
can redirect to a name Caddy really holds a certificate for, and Settings, Domain can say which
step the gateway is at. The notes inside the gateway script explain why it stopped guessing the
name through DNS in 0.304.0.

**Several instances on a VPS without Traefik.** The gateway of the first instance holds 80/443 and
later gateways stay idle, so later instances use the shared proxy `docker-compose.proxy.yml`. See
`DEPLOY.md`.

## Several instances on one Hostinger VPS

Deploy the compose once more as a new stack in Docker Manager and change all three values:

| | `DOMAIN_NAME` | `JAVIS_NAME` | `JAVIS_HOST_PORT` |
| --- | --- | --- | --- |
| Stack 1 | `shop.srv1782015.hstgr.cloud` | empty | empty |
| Stack 2 | `home.srv1782015.hstgr.cloud` | `javis-home` | `7778` |

All three must differ between stacks. The same `JAVIS_NAME` makes Docker report the container name
as in use, the same `JAVIS_HOST_PORT` reports the port as taken, and the same `DOMAIN_NAME` makes
two instances fight over one link. Hostinger's wildcard DNS `*.hstgr.cloud` already exists, so any
subdomain resolves at once.

Each stack has its own volumes, so state, brain, admin account and the Claude sign-in token are
separate. Signing in to Claude is done once per instance, in that stack's App terminal.
