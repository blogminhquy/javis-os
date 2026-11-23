"""Which chat the owner is reading right now, on ANY device (owner, 2026-11-23).

The owner reported: "every answer buzzes the phone while I am reading it on the computer; talking and chatting at the
same time, it buzzes non-stop". The quiet check in dashboard/sw.js only sees the tabs of its OWN device, so the phone,
with no Javis tab in front, showed every "Javis has answered" notice the computer was already displaying.

So each dashboard tab reports here which chat it shows and whether the owner is in front of it (tab visible, and the
window focused or touched in the last two minutes; dashboard/push.js). A push about a chat (`quiet_if_visible` plus
`session_id`, webpush.gui_het) is then skipped on EVERY device while a fresh report says that chat is being read.

Memory only, no file: a restart forgets every tab, which only means the next answer may ring once. A report counts for
`FRESH_S` seconds; a tab heartbeats while active and says "inactive" the moment it is hidden, so a phone in a pocket
starts ringing again within that window at worst.
"""
from __future__ import annotations

import threading
import time

FRESH_S = 75          # the tab heartbeats every 30 s while active; two missed beats and it no longer counts
MAX_TABS = 200        # a bound on the table: a flood of fake tab ids cannot grow memory without end

_LOCK = threading.Lock()
_TABS: dict = {}      # tab id -> {"sid": chat id, "active": bool, "ts": time}


def _clean(now: float) -> None:
    for k in [k for k, v in _TABS.items() if now - v["ts"] > FRESH_S]:
        del _TABS[k]
    if len(_TABS) > MAX_TABS:
        for k in sorted(_TABS, key=lambda k: _TABS[k]["ts"])[:len(_TABS) - MAX_TABS]:
            del _TABS[k]


def report(tab: str, session_id: str, active: bool, now: float = None) -> bool:
    """One tab says which chat it shows and whether the owner is in front of it. False when the tab id is empty."""
    tab = str(tab or "").strip()[:64]
    if not tab:
        return False
    now = time.time() if now is None else now
    with _LOCK:
        _TABS[tab] = {"sid": str(session_id or "")[:128], "active": bool(active), "ts": now}
        _clean(now)
    return True


def watching(session_id: str, now: float = None) -> bool:
    """True while some tab on some device shows this chat with the owner in front of it."""
    sid = str(session_id or "")
    if not sid:
        return False
    now = time.time() if now is None else now
    with _LOCK:
        return any(v["active"] and v["sid"] == sid and now - v["ts"] <= FRESH_S for v in _TABS.values())


def reset() -> None:
    """Forget every tab (tests)."""
    with _LOCK:
        _TABS.clear()
