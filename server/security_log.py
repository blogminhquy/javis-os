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
def client_ip(request) -> str:
    """The sender's address. Behind a proxy on this machine or the private network (Caddy, Traefik, Docker) the address
    the proxy appended to X-Forwarded-For is used; a request straight from a public address cannot pick its own."""
    host = request.client.host if getattr(request, "client", None) else ""
    try:
        direct = ipaddress.ip_address(host)
        behind = direct.is_loopback or direct.is_private
    except ValueError:
        behind = False
    if behind:
        for h in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
            raw = request.headers.get(h, "") or ""
            last = raw.split(",")[-1].strip()
            if last:
                try:
                    return str(ipaddress.ip_address(last))
                except ValueError:
                    pass
    return host


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
