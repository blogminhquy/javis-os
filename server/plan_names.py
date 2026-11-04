"""Plan-name catalog (2026-11-04): the name a vendor sells a plan under today, kept in javis-store.

Why
---
Only Claude Code sends the plan's selling name (`planDisplayName`, see `plan_limits.ten_goi_claude`).
Codex sends a CODE that no longer matches the name: `prolite` is the $100 tier, `pro` the renamed
$200 one. Grok and Antigravity send little or nothing. A table in Javis's code would need a new
release every time a vendor renames a plan (owner, 2026-11-04), so the table lives in javis-store
(`plan-names.json`, next to `index.json`). A weekly cloud check opens a Pull Request there when a
vendor renames something; the owner approves it, and every machine picks it up here.

Cost: one ~2 KB file every 6 hours, fetched on a background thread. Reads never wait on the network:
they answer from the cached copy (or nothing) and, when it is old, start one refresh for next time.
A failed fetch keeps the old copy and waits 30 minutes before trying again.

Order a caller applies (`plan_limits.ten_goi`): the vendor's own name, then this catalog, then the
tidied code.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from urllib.parse import urljoin

from config import STATE_DIR

CACHE = STATE_DIR / "plan-names-cache.json"
TTL = 6 * 3600
RETRY = 30 * 60
FORMAT = "javis-plan-names"
FORMAT_VERSION = 1
NHA = ("claude", "codex", "grok", "agy")
MAX_BYTES = 64 * 1024

_LOCK = threading.Lock()
_STATE = {"mem": None, "running": False, "fail_at": 0.0}


def ten_hop_le(v) -> bool:
    """1-40 characters of letters, digits, spaces and `.+-`, starting and ending on a letter or digit
    (`+` may end it). The rule Claude Code applies to `plan_display_name`, and javis-store's checker."""
    if not isinstance(v, str) or not 1 <= len(v) <= 40 or not v[0].isalnum():
        return False
    if len(v) > 1 and not (v[-1].isalnum() or v[-1] == "+"):
        return False
    return all(c.isalnum() or c in " .+-" for c in v)


def lam_sach(d) -> dict:
    """Keep only valid `{provider: {code: name}}` entries. Anything else is dropped, never shown."""
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        return {}
    if int(d.get("format_version") or 0) > FORMAT_VERSION:
        return {}
    pv = d.get("providers")
    if not isinstance(pv, dict):
        return {}
    ra = {}
    for nha in NHA:
        bang = pv.get(nha)
        if not isinstance(bang, dict):
            continue
        sach = {}
        for ma, ten in list(bang.items())[:200]:
            k = str(ma or "").strip().lower()
            if k and len(k) <= 64 and all(c.isalnum() or c == "_" for c in k) and ten_hop_le(ten):
                sach[k] = ten.strip()
        if sach:
            ra[nha] = sach
    return ra


def url_danh_ba() -> str:
    """`plan-names.json` next to the pack catalog the machine uses. `JAVIS_PLAN_NAMES_URL` overrides it;
    an empty value turns the catalog off."""
    env = os.environ.get("JAVIS_PLAN_NAMES_URL")
    if env is not None:
        return env.strip()
    try:
        import packs_store
        return urljoin(packs_store.url_kho(), "plan-names.json")
    except Exception:  # noqa: BLE001
        return ""


def _doc_cache() -> dict:
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _ghi_cache(d: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE)
    except OSError:
        pass


def lam_moi(u: str = "") -> bool:
    """Fetch the catalog now (blocking). True when a valid copy was saved."""
    u = u or url_danh_ba()
    if not u:
        return False
    try:
        import packs_fetch
        raw = asyncio.run(packs_fetch.tai(u, tran=MAX_BYTES))
        bang = lam_sach(json.loads(raw.decode("utf-8")))
    except Exception:  # noqa: BLE001
        _STATE["fail_at"] = time.time()
        return False
    d = {"fetched_at": time.time(), "url": u, "providers": bang}
    _ghi_cache(d)
    _STATE["mem"] = d
    return True


def _lam_moi_nen(u: str) -> None:
    with _LOCK:
        if _STATE["running"]:
            return
        _STATE["running"] = True

    def chay():
        try:
            lam_moi(u)
        finally:
            _STATE["running"] = False

    threading.Thread(target=chay, name="plan-names", daemon=True).start()


def bang(now: float = None) -> dict:
    """The cached `{provider: {code: name}}`, never waiting on the network. Old or missing: one
    background refresh starts, and this call answers with what it has."""
    now = time.time() if now is None else now
    u = url_danh_ba()
    if not u:
        return {}
    d = _STATE["mem"]
    if d is None or d.get("url") != u:
        d = _doc_cache()
        if d.get("url") != u:
            d = {}
        _STATE["mem"] = d
    cu = now - float(d.get("fetched_at") or 0) >= TTL
    if cu and now - _STATE["fail_at"] >= RETRY:
        _lam_moi_nen(u)
    return d.get("providers") or {}


def ten(nha: str, ma: str) -> str:
    """The catalog's name for one provider's plan code, or ""."""
    k = str(ma or "").strip().lower()
    if not k or nha not in NHA:
        return ""
    return (bang().get(nha) or {}).get(k, "")
