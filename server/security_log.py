"""Security log of the owner account: who signed in, from where, and every change to the account.

Owner incident 2026-11-09: the username, password and 2FA of a VPS Javis were changed by someone who edited
settings.json on the server. Nothing recorded when it happened or from where: container logs are lost on every update
and the only log Javis kept (auth_audit.jsonl) covered API token probes. This module is the missing record.

- One JSON line per event in STATE_DIR/security_log.jsonl. STATE_DIR is a volume on Docker/Hostinger, so the log
  survives updates and redeploys. Rotated at MAX_BYTES into security_log.1.jsonl (one old file kept).
- Never records a secret: no password, no token, no session id, no 2FA code.
- Events of level "alert" are also queued for the owner (Telegram, bell, web push), drained by main.py.
- Sign-ins from a network not seen before (IPv4 /24, IPv6 /64) are flagged, so a login from a stranger stands out.

The state directory is read from config lazily: config imports this module, so a top-level import would be circular.
"""
from __future__ import annotations

import ipaddress
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

MAX_BYTES = 1_000_000
LOG_NAME = "security_log.jsonl"
OLD_NAME = "security_log.1.jsonl"
NETWORKS_NAME = ".login_networks.json"
MAX_NETWORKS = 200

# event -> level. "alert" = the owner is told right away; "warn" = shown in red in the list; "info" = plain record.
EVENTS: Dict[str, str] = {
    "login_ok": "info",
    "login_new_network": "alert",
    "login_fail": "warn",
    "login_2fa_fail": "warn",
    "login_recovery_code": "alert",
    "login_locked": "warn",
    "logout": "info",
    "setup": "alert",
    "username_changed": "alert",
    "password_changed": "alert",
    "2fa_enabled": "alert",
    "2fa_disabled": "alert",
    "2fa_recovery_regenerated": "alert",
    "token_created": "alert",
    "token_revoked": "info",
    "sessions_revoked": "info",
    "login_disabled": "alert",
    "env_account_created": "alert",
    "env_account_reset": "alert",
    "env_2fa_reset": "alert",
    "auth_changed_outside": "alert",
    "agent_secret_blocked": "warn",
    # 2026-11-22: someone tried to create an account after the owner's password vanished (main.auth_setup), and a save
    # that would have dropped the owner's password was refused (config.write_settings).
    "setup_blocked": "alert",
    "account_clear_blocked": "alert",
}

_LOCK = threading.Lock()
_PENDING: List[dict] = []


def state_dir() -> Path:
    try:
        import config
        return Path(config.STATE_DIR)
    except Exception:  # noqa: BLE001 - config failing to import must not stop a security record
        return Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))


def _log_path() -> Path:
    return state_dir() / LOG_NAME


def _clip(v, n: int) -> str:
    return str(v or "").replace("\n", " ").replace("\r", " ")[:n]


def level_of(event: str) -> str:
    return EVENTS.get(event, "info")


def record(event: str, *, ip: str = "", ua: str = "", user: str = "", detail: str = "",
           source: str = "", alert: Optional[bool] = None) -> dict:
    """Append one event. Never raises: a full disk must not turn a login into an error page."""
    item = {"ts": round(time.time(), 3), "event": _clip(event, 40), "level": level_of(event),
            "ip": _clip(ip, 64), "ua": _clip(ua, 200), "user": _clip(user, 80),
            "detail": _clip(detail, 300), "source": _clip(source, 40)}
    item = {k: v for k, v in item.items() if v not in ("", None)}
    path = _log_path()
    with _LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if path.stat().st_size > MAX_BYTES:
                    os.replace(path, path.with_name(OLD_NAME))
            except FileNotFoundError:
                pass
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001
            print(f"[security_log] cannot write {event}: {type(e).__name__}: {e}", file=__import__("sys").stderr)
        if alert if alert is not None else item["level"] == "alert":
            _PENDING.append(item)
            del _PENDING[:-50]
    return item


def recent(limit: int = 100, events: Optional[set] = None) -> List[dict]:
    """Newest first, from the current file and the rotated one."""
    out: List[dict] = []
    base = state_dir()
    for name in (LOG_NAME, OLD_NAME):
        try:
            lines = (base / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            if events and item.get("event") not in events:
                continue
            out.append(item)
            if len(out) >= limit:
                return out
    return out


def drain_alerts() -> List[dict]:
    with _LOCK:
        items = list(_PENDING)
        _PENDING.clear()
    return items


# ---- Where a request comes from ----
# Owner incident 2026-11-22: a stranger created an account on a VPS behind Cloudflare and Traefik, and the log named
# only the Cloudflare edge (172.71.219.14). The old rule took the LAST X-Forwarded-For entry, which behind Cloudflare is
# the edge, never the visitor; the sign-in lockout counted per edge too, so one stranger locked out the owner.
#
# The rule now: start at the address that connected, and step left through X-Forwarded-For only while the hop is one
# we trust to have written it (a proxy on this machine or the private network). The first hop that is neither a local
# proxy nor Cloudflare is the visitor. A Cloudflare hop names the visitor in CF-Connecting-IP, which only Cloudflare
# can set: on any other hop that header is the visitor's own words and is ignored.
#
# Cloudflare's published edge ranges, https://www.cloudflare.com/ips/ (checked 2026-11-22). They change rarely; an
# edge missing here is logged as itself, which is what happened before, never as an address the visitor picked.
CLOUDFLARE_NETS = tuple(ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29",
    "2c0f:f248::/32"))

# Where a reverse proxy of this machine connects from: loopback, the private ranges (Docker, LAN) and IPv6 ULA.
# Written out instead of `is_private`, which also counts the documentation ranges and would trust a visitor there.
PROXY_NETS = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7"))


def _addr(value):
    try:
        a = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return None
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a


def _in(a, nets) -> bool:
    return any(a.version == n.version and a in n for n in nets)


def is_cloudflare(value) -> bool:
    a = _addr(value)
    return a is not None and _in(a, CLOUDFLARE_NETS)


def client_ip(request) -> str:
    """The visitor's address, as far as hops we trust can tell. A request straight from a public address cannot pick
    its own; behind Cloudflare it is CF-Connecting-IP; behind a local proxy it is the entry that proxy appended."""
    host = request.client.host if getattr(request, "client", None) else ""
    cur = _addr(host)
    if cur is None:
        return host
    if not (_in(cur, PROXY_NETS) or _in(cur, CLOUDFLARE_NETS)):
        return str(cur)
    headers = request.headers
    hops = [h.strip() for h in (headers.get("x-forwarded-for", "") or "").split(",") if h.strip()]
    if not hops and headers.get("x-real-ip"):
        hops = [headers.get("x-real-ip")]
    for raw in reversed(hops):
        if _in(cur, CLOUDFLARE_NETS):
            break
        a = _addr(raw)
        if a is None:
            break        # an entry that is not an address: the last good hop is as far as anyone vouches
        cur = a
        if not (_in(a, PROXY_NETS) or _in(a, CLOUDFLARE_NETS)):
            return str(a)
    if _in(cur, CLOUDFLARE_NETS) or cur.is_loopback:
        # A Cloudflare hop, or cloudflared on this machine that passed no X-Forwarded-For.
        visitor = _addr(headers.get("cf-connecting-ip", ""))
        if visitor is not None:
            return str(visitor)
    return str(cur)


def request_meta(request) -> tuple:
    """(ip, user agent) of a request, for the log and the session list."""
    try:
        ua = request.headers.get("user-agent", "") or ""
    except Exception:  # noqa: BLE001
        ua = ""
    return client_ip(request), _clip(ua, 200)


def network_of(ip: str) -> str:
    """IPv4 /24 or IPv6 /64: a phone moving between cell towers mostly stays inside one."""
    try:
        a = ipaddress.ip_address(str(ip or "").strip())
    except ValueError:
        return ""
    if a.version == 4:
        return str(ipaddress.ip_network(f"{a}/24", strict=False))
    if a.ipv4_mapped:
        return str(ipaddress.ip_network(f"{a.ipv4_mapped}/24", strict=False))
    return str(ipaddress.ip_network(f"{a}/64", strict=False))


def _networks_path() -> Path:
    return state_dir() / NETWORKS_NAME


def _load_networks() -> Dict[str, float]:
    try:
        data = json.loads(_networks_path().read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def note_login_network(ip: str) -> bool:
    """Remember the network of a successful sign-in. True when it is new AND an earlier one was known: the very first
    sign-in of a machine is not news. Loopback (the owner on the machine itself) is never news."""
    net = network_of(ip)
    if not net:
        return False
    try:
        if ipaddress.ip_address(str(ip).strip()).is_loopback:
            return False
    except ValueError:
        return False
    with _LOCK:
        known = _load_networks()
        is_new = net not in known and bool(known)
        known[net] = time.time()
        if len(known) > MAX_NETWORKS:
            known = dict(sorted(known.items(), key=lambda kv: kv[1])[-MAX_NETWORKS:])
        try:
            _networks_path().write_text(json.dumps(known), encoding="utf-8")
        except OSError:
            pass
    return is_new


def forget_networks() -> None:
    """After an account takeover the attacker's network is "known"; resetting makes every next sign-in news."""
    try:
        _networks_path().unlink()
    except OSError:
        pass
