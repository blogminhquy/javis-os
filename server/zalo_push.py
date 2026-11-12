"""Live push from javis-zalo: read a personal Zalo account when a message arrives, not on a timer (2026-11-10).

Owner, 10/11/2026: "when a message arrives, send it over; do not scan on a timer, some days there is no message at
all." javis-zalo receives a message from Zalo in real time, but Javis only learned about it by calling
`zalo_get_messages` every 20 seconds, per account, all day.

How it works (javis-zalo 1.10.0, `src/mcp/live-push.js`):
  - `mcp_store.resolved()` gives every stdio `zalo` connection two environment variables: the URL of
    `POST /zalo/push?conn=<id>` on this machine and a bearer token.
  - javis-zalo POSTs a wake-up there when its live buffer changes or its Zalo connection goes up or down. No message
    content travels this way: the read loop still fetches messages through the MCP tool.
  - The read loop (`zalo_personal_channel._vong`) reads an account at once when a wake-up is pending, and makes NO
    call to javis-zalo for an account that pushes and has nothing pending. When every account pushes and no turn
    is on hold the loop does not tick either: it sleeps until `zalo_personal_channel.wake()` (a wake-up, a
    javis-zalo process that ended, a turn put on hold, a bot or connection change).

What makes an account "pushing" is proof, not configuration: a wake-up that arrived from the MCP session that is
alive right now (`note` stores that session's epoch). An older javis-zalo ignores the variables and never calls, a
process that died no longer matches the live session, a Javis bound to an address 127.0.0.1 cannot reach never gets
the first call: in each case the account simply keeps the timer it has today.

The token is made per server process. A javis-zalo left over from an earlier lifetime carries the old one and is
refused, so it can never mark the new session as pushing.
"""
from __future__ import annotations

import hmac
import os
import secrets
import time
from typing import Dict, Optional

PATH = "/zalo/push"
EVENTS = ("ready", "messages", "connected", "disconnected")

_TOKEN = secrets.token_urlsafe(32)
# conn_id -> {"epoch": int, "at": float, "seq": int, "pending": bool, "connected": bool | None, "version": str}
_STATE: Dict[str, dict] = {}


def enabled() -> bool:
    """`JAVIS_ZALO_PUSH=0` turns live push off for the whole machine: nothing is given to javis-zalo and every
    account is read on the timer as before."""
    return os.environ.get("JAVIS_ZALO_PUSH", "").strip() != "0"


def _port() -> int:
    # Same source as mcp_hub.hub_port, read here so this module imports nothing of Javis (mcp_store imports it).
    try:
        return int(os.getenv("JAVIS_PORT", "7777"))
    except ValueError:
        return 7777


def env_for(conn_id: str) -> dict:
    """The two variables for one connection's javis-zalo process, {} when live push is off. The values are the same
    for the whole life of this server, so they never change the MCP session's identity between two callers."""
    cid = str(conn_id or "").strip()
    if not cid or not enabled():
        return {}
    from urllib.parse import quote
    return {"JAVIS_ZALO_PUSH_URL": f"http://127.0.0.1:{_port()}{PATH}?conn={quote(cid, safe='')}",
            "JAVIS_ZALO_PUSH_TOKEN": _TOKEN}


def token_ok(authorization: str) -> bool:
    """The Authorization header of a wake-up carries this process's token."""
    given = str(authorization or "").strip()
    if given[:7].lower() != "bearer ":
        return False
    return hmac.compare_digest(given[7:].strip().encode("utf-8"), _TOKEN.encode("utf-8"))


def note(conn_id: str, body: dict, epoch: int, now: Optional[float] = None) -> dict:
    """Record one wake-up. `epoch`: the MCP session of this connection that is alive now (0 = none). Returns the
    connection's state."""
    cid = str(conn_id or "").strip()
    now = time.time() if now is None else float(now)
    body = body if isinstance(body, dict) else {}
    events = [e for e in (body.get("events") or []) if e in EVENTS]
    st = _STATE.setdefault(cid, {"seq": 0, "connected": None, "version": ""})
    st["epoch"] = int(epoch or 0)
    st["at"] = now
    st["seq"] = int(st.get("seq") or 0) + 1
    st["pending"] = True
    st["events"] = events
    st["version"] = str(body.get("version") or st.get("version") or "")[:40]
    if isinstance(body.get("connected"), bool):
        st["connected"] = body["connected"]
    return dict(st)


def active(conn_id: str, epoch: int) -> bool:
    """This connection's javis-zalo pushes: a wake-up came from the MCP session that is alive now."""
    st = _STATE.get(str(conn_id or "").strip())
    return bool(enabled() and st and epoch and int(st.get("epoch") or 0) == int(epoch))


def pending(conn_id: str) -> bool:
    return bool((_STATE.get(str(conn_id or "").strip()) or {}).get("pending"))


def take(conn_id: str) -> bool:
    """True when a wake-up is waiting, and marks it taken. Called right BEFORE a read, so a wake-up that arrives
    while that read runs is pending again when it ends."""
    st = _STATE.get(str(conn_id or "").strip())
    if not st or not st.get("pending"):
        return False
    st["pending"] = False
    return True


def state(conn_id: str) -> dict:
    return dict(_STATE.get(str(conn_id or "").strip()) or {})


def forget(conn_id: str = "") -> None:
    """Drop what is known about one connection, or about all of them (tests, a connection that was removed)."""
    if conn_id:
        _STATE.pop(str(conn_id).strip(), None)
    else:
        _STATE.clear()
