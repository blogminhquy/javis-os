"""Tell the owner in the bell when an installed Store pack has a newer version (0.335.0).

Owner request 2026-10-26: "những bản plugin có phiên bản mới trong store thì phải báo về thông báo nhé". The Store page
already shows a banner with the packs that can be updated, but only to someone who opens it. This module checks in the
background and puts ONE notice in the bell (the inbox) listing what can be updated; pressing it opens the Store, where
the banner and the "Có bản mới" filter take it from there.

No background scan (0.340.0, owner 2026-10-26: "khi có bản mới thì mới báo chứ lại tự quét như này anh thấy không
ổn, tốn tài nguyên"). 0.335.0 ran a timer on the 30-second scheduler loop that fetched the catalog every six hours
whether anyone used Javis or not. Now nothing runs on its own: the check rides on the dashboard opening (the
`/version` call it already makes for the version label), at most once per `INTERVAL`, and reads the catalog through
`packs_store.lay`, whose cache answers without any network for six hours. A Javis nobody opens does no work at all.

Rules:
  - Only packs installed from the Store or a zip (they have a row in the install ledger, `pack_install.doc_so`); the
    connectors that ship with the app update with the app.
  - Each version is announced once: `STATE` remembers the last version told per pack, so the bell does not ring every
    six hours for the same update, and the next version rings again.
  - Javis never updates anything on its own: an update installs new code and goes through the same confirm screen as
    a first install.
  - A stale catalog (the last fetch failed) is not used: better one notice late than a notice built from old data.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Dict, List, Optional

from config import STATE_DIR
import localefmt

STATE = STATE_DIR / "pack-update-notices.json"
INTERVAL = 6 * 3600         # at most one check per six hours, the same as the catalog cache (`packs_store.TTL`)
CHANNEL = "store:updates"   # the dashboard opens the Store for a bell item on this channel (notifications.js)
MAX_LINES = 8

_LAST = [0.0]
_BUSY = [False]


def _name(g: dict) -> str:
    names = g.get("name") or {}
    if not isinstance(names, dict):
        return str(names or g.get("id") or "")
    lang = localefmt.ngon_ngu_giao_dien()
    return str(names.get(lang) or names.get("en") or next(iter(names.values()), "") or g.get("id") or "")


def find_updates(store_packs, installed: dict) -> List[dict]:
    """Installed packs whose Store version is newer: [{id, name, from, to}]. Version compare is numeric
    (`packs._ver`), so 1.10.0 is newer than 1.9.0 and a Store entry with an older number is never an "update"."""
    import packs
    out = []
    for g in store_packs or []:
        if not isinstance(g, dict):
            continue
        row = (installed or {}).get(g.get("id"))
        cur, new = str((row or {}).get("version") or ""), str(g.get("version") or "")
        if not row or not cur or not new:
            continue
        if packs._ver(new) > packs._ver(cur):
            out.append({"id": str(g["id"]), "name": _name(g), "from": cur, "to": new})
    return out


def _load() -> Dict[str, str]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: Dict[str, str]) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    except OSError as e:
        print(f"[pack updates] could not save {STATE}: {e}", file=sys.stderr)


def notify(updates: List[dict]) -> Optional[dict]:
    """Put one bell notice for the updates not announced yet. Returns the inbox item, or None when nothing is new."""
    told = _load()
    fresh = [u for u in updates or [] if told.get(u["id"]) != u["to"]]
    if not fresh:
        return None
    import inbox
    n = len(fresh)
    title = localefmt.chu(f"Store có bản mới cho {n} gói đã cài", f"Store has updates for {n} installed packs") \
        if n > 1 else localefmt.chu(f"Store có bản mới: {fresh[0]['name']} {fresh[0]['to']}",
                                    f"Store update: {fresh[0]['name']} {fresh[0]['to']}")
    lines = [f"- {u['name']}: {u['from']} → {u['to']}" for u in fresh[:MAX_LINES]]
    if n > MAX_LINES:
        lines.append(localefmt.chu(f"- và {n - MAX_LINES} gói khác", f"- and {n - MAX_LINES} more"))
    body = "\n".join(lines) + "\n\n" + localefmt.chu(
        "Bấm để mở Javis Store và cập nhật. Javis không tự cập nhật: mỗi bản mới vẫn qua màn hình xác nhận.",
        "Press to open the Javis Store and update. Javis never updates on its own: each new version still goes "
        "through the confirm screen.")
    # 0.403.0: an update is an "info" notice of the group "update"; Javis Core's rules decide if it rings.
    import notify_policy
    dec = notify_policy.decide("update", "info", title)
    if dec["verdict"] == "drop":
        told.update({u["id"]: u["to"] for u in fresh})
        _save(told)
        return None
    item = inbox.add(body, kind="system", title=title, label="Javis Store", source="store", channel=CHANNEL,
                     dedup="pack-updates:" + ",".join(sorted(f"{u['id']}@{u['to']}" for u in fresh)),
                     group=dec["group"], level=dec["level"], sig=dec["sig"], filtered=dec["verdict"] != "loud",
                     why=dec["why"])
    told.update({u["id"]: u["to"] for u in fresh})
    _save(told)
    return item


async def check() -> Optional[dict]:
    """One check: the Store catalog (cached for `INTERVAL`) against the install ledger."""
    import pack_install
    import packs_store
    d = await packs_store.lay()
    if not d.get("ok") or d.get("stale"):
        return None
    return notify(find_updates(d.get("packs") or [], pack_install.doc_so()))


async def on_open(now: Optional[float] = None) -> None:
    """Called when the owner opens the dashboard (main's `/version`, as a background task). Checks at most once per
    `INTERVAL`; any other call returns at once. A failed check only logs: the next open after six hours tries again."""
    now = time.time() if now is None else now
    if _BUSY[0] or (_LAST[0] and now - _LAST[0] < INTERVAL):
        return
    _BUSY[0], _LAST[0] = True, now
    try:
        await check()
    except Exception as e:      # noqa: BLE001 - a broken check must never stop the scheduler
        print(f"[pack updates] {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        _BUSY[0] = False
