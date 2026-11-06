"""share_stats.py - view counter for public share links (/s/<token>).

Owner, 2026-11-06: "làm cho anh bộ đếm thống kê view của các link". What it counts, and why each rule exists:

1. ONE VIEW PER VISIT, not per request. A reader who reloads, or whose .html app fetches its data, is still one view:
   the same visitor inside VISIT_WINDOW seconds is not counted again. Assets, sibling files and /raw never count.
2. NO BOTS. Link previews (Facebook, Telegram, Zalo, Slack, Discord...) fetch the page the moment a link is pasted
   into a chat; counting them would make every link look read. Browser prefetches are skipped for the same reason.
3. NOT THE OWNER. A request carrying a valid dashboard session is the owner checking their own link.
4. NO RAW IP STORED. A visitor is a salted hash of address + browser, used only to tell "the same person again" from
   "someone new". The salt is random per install, so the hash means nothing outside this machine.

Stored apart from share_links.json on purpose: that file sits on the path of every public request and is rewritten
whole, so a counter there would rewrite it on every view. Here counts live in memory and are written at most once
every FLUSH_DELAY seconds (plus at exit); a crash loses a few seconds of counts, never a link.
"""
import atexit
import hashlib
import json
import os
import re
import secrets
import threading
import time

from config import STATE_DIR

STORE = STATE_DIR / "share_stats.json"
VISIT_WINDOW = 30 * 60      # same visitor within 30 minutes = same visit
KEEP_DAYS = 60              # per-day counts kept for the chart
MAX_SEEN = 500              # visitor hashes remembered per link (oldest dropped): unique count is approximate past it
FLUSH_DELAY = 3.0
CHART_DAYS = 14

_LOCK = threading.RLock()
_data = None                # {"salt": str, "links": {token: {...}}}
_dirty = False
_timer = None

_BOT_RE = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|preview|facebookexternalhit|facebot|whatsapp|embedly|vkshare|pinterest"
    r"|headless|lighthouse|pagespeed|curl/|wget|python-|httpx|go-http|okhttp|java/|libwww|scrapy|uptime|monitor",
    re.I)


def is_bot(user_agent: str) -> bool:
    ua = str(user_agent or "").strip()
    return not ua or bool(_BOT_RE.search(ua))


def _load() -> dict:
    global _data
    if _data is None:
        try:
            d = json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        if not isinstance(d, dict):
            d = {}
        if not isinstance(d.get("links"), dict):
            d["links"] = {}
        if not d.get("salt"):
            d["salt"] = secrets.token_hex(16)
        _data = d
    return _data


def _flush() -> None:
    global _dirty, _timer
    with _LOCK:
        _timer = None
        if not _dirty or _data is None:
            return
        body = json.dumps(_data, ensure_ascii=False, separators=(",", ":"))
        _dirty = False
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".json.tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, STORE)
    except OSError:
        with _LOCK:
            _dirty = True


def _mark_dirty() -> None:
    global _dirty, _timer
    _dirty = True
    if _timer is None:
        _timer = threading.Timer(FLUSH_DELAY, _flush)
        _timer.daemon = True
        _timer.start()


atexit.register(_flush)


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def visitor_key(ip: str, user_agent: str) -> str:
    """Salted hash of who is reading. Never stored raw."""
    with _LOCK:
        salt = _load()["salt"]
    return hashlib.sha256((salt + "|" + str(ip or "") + "|" + str(user_agent or "")).encode()).hexdigest()[:16]


def record_view(token: str, visitor: str, now: float = None) -> bool:
    """Count one view of `token` by `visitor` (from visitor_key). False when it was the same visit again."""
    tok = str(token or "").strip()
    if not tok:
        return False
    now = time.time() if now is None else now
    with _LOCK:
        links = _load()["links"]
        st = links.get(tok)
        if not isinstance(st, dict):
            st = links[tok] = {"views": 0, "visitors": 0, "first": now, "last": 0, "days": {}, "seen": {}}
        seen = st.setdefault("seen", {})
        prev = seen.get(visitor)
        seen[visitor] = now
        if prev is not None and now - prev < VISIT_WINDOW:
            _mark_dirty()
            return False
        if prev is None:
            st["visitors"] = int(st.get("visitors") or 0) + 1
        st["views"] = int(st.get("views") or 0) + 1
        st["last"] = now
        days = st.setdefault("days", {})
        k = _day(now)
        days[k] = int(days.get(k) or 0) + 1
        cut = _day(now - KEEP_DAYS * 86400)
        for old in [x for x in days if x < cut]:
            days.pop(old, None)
        if len(seen) > MAX_SEEN:
            for old in sorted(seen, key=seen.get)[:len(seen) - MAX_SEEN]:
                seen.pop(old, None)
        _mark_dirty()
        return True


def summary(token: str, now: float = None) -> dict:
    """What the Share links page shows for one link. `days` is CHART_DAYS counts, oldest first, ending today."""
    now = time.time() if now is None else now
    with _LOCK:
        st = _load()["links"].get(str(token or ""))
        st = st if isinstance(st, dict) else {}
        days = dict(st.get("days") or {})
    chart = [int(days.get(_day(now - i * 86400)) or 0) for i in range(CHART_DAYS - 1, -1, -1)]
    return {"views": int(st.get("views") or 0), "visitors": int(st.get("visitors") or 0),
            "last": st.get("last") or 0, "week": sum(chart[-7:]), "days": chart}


def forget(token: str) -> None:
    """Drop the counts of a revoked link."""
    with _LOCK:
        if _load()["links"].pop(str(token or ""), None) is not None:
            _mark_dirty()
