"""Find a customer in the bot inbox by phone number, asking Zalo when the inbox does not know the number yet (0.216.0).

Why this exists. The owner asked (2026-10-18) for the inbox search box to find people by phone number: "Zalo người ta có
sđt là tìm đc". A Zalo chat never carries the other person's phone number, so the inbox had nothing to match. Zalo
itself can answer "whose account is this number" (the same search as typing a number into the Zalo app), and the
answer is a user id, which is exactly the id of that person's private chat in the inbox.

What it does. When the search box holds a full Vietnamese mobile number and no customer in the inbox has it yet, the
inbox route calls `lookup()`. For each connected personal Zalo account (or only the one the inbox is filtered to) it
runs `friend find <84xxxxxxxxx>` in that account's session, stores the number on the matching customer
(`conversations.gan_sdt_khach`) and returns who the number belongs to, so the inbox can say "this is X's Zalo, no chat
yet" when that person never wrote.

Rules that keep it cheap and quiet:
  - Every answer is remembered in the inbox store (`sync_state`): a found number for `POS_TTL`, "no Zalo account" for
    `NEG_TTL`, any other failure for `ERR_TTL`. Typing the same number again never asks Zalo twice.
  - Zalo limits how many numbers one account may look up per day, so live lookups are capped at `MAX_LIVE_PER_HOUR`
    for the whole server. Past the cap the inbox says so instead of asking.
  - One lookup per account and number runs at a time; a second search for the same number waits for the first.
  - Only an explicit full number triggers it: `conversations.chuan_hoa_sdt` refuses a number still being typed.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import conversations
import localefmt
import zalo_cli

POS_TTL = 30 * 86400       # a number found on Zalo: owners rarely change, re-check monthly
NEG_TTL = 86400            # "no Zalo account for this number": people sign up, re-check daily
ERR_TTL = 600              # any other failure (rate limit, session down): do not hammer Zalo while the owner retypes
CLI_TIMEOUT = 20           # seconds for one CLI call
MAX_LIVE_PER_HOUR = 20     # live Zalo lookups per hour, all accounts together
_NOT_FOUND = "No Zalo user found"   # javis-zalo `friend find` prints this when Zalo has no account for the number

_live: List[float] = []
_running: Dict[str, "asyncio.Task"] = {}


def _key(conn_id: str, phone: str) -> str:
    return f"zalo_phone:{conn_id}:{phone}"


def _cached(conn_id: str, phone: str, now: float) -> Optional[dict]:
    raw = conversations.doc_trang_thai(_key(conn_id, phone))
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    ttl = POS_TTL if d.get("uid") else (ERR_TTL if d.get("error") else NEG_TTL)
    if now - float(d.get("ts") or 0) > ttl:
        return None
    return d


def parse_find(data: Any) -> Tuple[str, str]:
    """`(uid, name)` from what `friend find --json` prints: the user object itself or `{data: {...}}`."""
    u = data if isinstance(data, dict) else {}
    if not u.get("uid") and isinstance(u.get("data"), dict):
        u = u["data"]
    uid = str(u.get("uid") or "").strip()
    name = ""
    for k in ("display_name", "displayName", "zalo_name", "zaloName"):
        if str(u.get(k) or "").strip():
            name = str(u[k]).strip()
            break
    return uid, name


def _over_cap(now: float) -> bool:
    _live[:] = [t for t in _live if now - t < 3600]
    return len(_live) >= MAX_LIVE_PER_HOUR


async def _ask(conn: dict, phone: str, now: float) -> dict:
    """Ask Zalo once and remember the answer. Returns `{uid, name}`, `{}` (no account) or `{error}`."""
    cid = str(conn.get("id") or "")
    home = zalo_cli.home_of(conn)
    if not home:
        return {"error": localefmt.chu("kết nối Zalo này chưa có thư mục phiên",
                                       "this Zalo connection has no session folder")}
    if _over_cap(now):
        # Not remembered: the cap lifts within the hour and the owner should then get a real answer.
        return {"error": localefmt.chu("đã tra nhiều số trong một giờ qua, Zalo giới hạn số lần tra mỗi ngày. Thử lại sau",
                                       "many numbers were looked up in the last hour and Zalo caps lookups per day. "
                                       "Try again later")}
    _live.append(now)
    ok, data, err = await zalo_cli.run_cli({"home": home}, ["friend", "find"], [conversations.sdt_84(phone)],
                                           timeout=CLI_TIMEOUT)
    if ok:
        uid, name = parse_find(data)
        d = {"uid": uid, "name": name} if uid else {}
    elif _NOT_FOUND in str(err or ""):
        d = {}
    else:
        d = {"error": str(err or "")[:200]}
    conversations.ghi_trang_thai(_key(cid, phone), json.dumps({**d, "ts": now}, ensure_ascii=False))
    return d


async def _one(conn: dict, phone: str, now: float) -> dict:
    import zalo_personal_channel as zc
    cid = str(conn.get("id") or "")
    d = _cached(cid, phone, now)
    cached = d is not None
    if d is None:
        k = _key(cid, phone)
        t = _running.get(k)
        if t is None:
            t = asyncio.ensure_future(_ask(conn, phone, now))
            _running[k] = t
            t.add_done_callback(lambda _t, k=k: _running.pop(k, None))
        d = await asyncio.shield(t)
    if d.get("uid"):
        conversations.gan_sdt_khach(zc.KENH, cid, d["uid"], phone, d.get("name") or "")
    return {"account_id": f"{zc.KENH}:{cid}", "account_label": conn.get("label") or "Zalo",
            "uid": d.get("uid") or "", "name": d.get("name") or "", "error": d.get("error") or "", "cached": cached}


async def lookup(phone: str, account_id: str = "", now: Optional[float] = None) -> dict:
    """Who owns `phone` on each connected personal Zalo account. `account_id` (the inbox filter, `zalo_personal:<id>`)
    narrows it to one account; a filter on another channel means no Zalo account is asked.

    `{"phone": "0912345678", "results": [{account_id, account_label, uid, name, error, cached}]}`; `results` is empty
    when the text is not a full number or no personal Zalo account is connected."""
    import zalo_personal_channel as zc
    p = conversations.chuan_hoa_sdt(phone)
    if not p:
        return {"phone": "", "results": []}
    conns = zc._ket_noi()
    if account_id:
        conns = [c for c in conns if f"{zc.KENH}:{c.get('id')}" == account_id]
    now = time.time() if now is None else now
    results = await asyncio.gather(*(_one(c, p, now) for c in conns)) if conns else []
    return {"phone": p, "results": list(results)}
