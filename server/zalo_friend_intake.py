"""Accept incoming friend requests on a personal Zalo account and keep the introduction they carry (0.149.0).

Why this exists. The MTM owner asked (2026-10-15) for the bot to read the message that comes with a friend request
("I am Lan, mother of An, class 2K10") and keep it: someone who already introduced themselves must not be asked again,
someone who did not must be asked. That message only exists while the request is pending. Once the request is accepted
(on the phone or anywhere else) Zalo drops it, and the chat starts with a bare "you are now friends" line, so neither
the inbox nor the bot ever saw what the person wrote.

What it does, for each account whose bot on duty has `nhan_ket_ban` switched on (off by default, see chatbot_store):
  1. every `POLL_SECONDS`, ask Zalo for received requests (`friend recommendations`, items with recommType 2);
  2. accept each one (`friend accept`), at most `MAX_PER_ROUND` per round, `ACCEPT_GAP` seconds apart;
  3. write the introduction into the inbox as that person's first message (a fixed message id per request, so a
     repeat never writes twice), then hand it to the bot exactly like a message the person sent. The bot's own rules
     then decide: a complete introduction is acknowledged and not asked again; a partial one or none at all makes the
     bot ask for what is missing.

A request that cannot be accepted is left alone and tried again next round; nothing is written for it. Everything goes
through the same session as the rest of the account (`zalo_cli.run_cli` with the connection's HOME).
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Dict, List, Optional

import conversations
import zalo_cli

POLL_SECONDS = 60          # how often an account's pending requests are checked
MAX_PER_ROUND = 10         # requests accepted per round; the rest wait for the next one
ACCEPT_GAP = 3             # seconds between two accepts, so a burst of requests does not look like a script
RECEIVED_REQUEST = 2       # zca-js FriendRecommendationsType.ReceivedFriendRequest

_last_check: Dict[str, float] = {}

INTRO_WITH_MESSAGE = "[Lời nhắn kèm lời mời kết bạn, nick vừa chấp nhận] {msg}"
INTRO_WITHOUT_MESSAGE = "[Vừa kết bạn, người này không kèm lời nhắn giới thiệu]"


def enabled_for(conn_id: str) -> bool:
    """Is friend-request intake switched on for the bot on duty on this account?"""
    import zalo_personal_channel as zc
    tb = zc._BOTS.get(str(conn_id))
    fn = getattr(tb, "nhan_ket_ban", None)
    try:
        return bool(callable(fn) and fn())
    except Exception:      # noqa: BLE001 - a broken bot config must not break the read loop
        return False


def due(conn_id: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    return now - _last_check.get(str(conn_id), 0.0) >= POLL_SECONDS


def received_requests(data: Any) -> List[dict]:
    """Pending requests sent TO this account, as [{uid, name, message, time}], oldest first."""
    items = (data or {}).get("recommItems") if isinstance(data, dict) else None
    out = []
    for it in items or []:
        d = (it or {}).get("dataInfo") or {}
        if d.get("recommType") != RECEIVED_REQUEST:
            continue        # type 1 is Zalo suggesting a friend, not a request
        uid = str(d.get("userId") or "").strip()
        if not uid:
            continue
        info = d.get("recommInfo") or {}
        out.append({
            "uid": uid,
            "name": str(d.get("displayName") or d.get("zaloName") or "").strip(),
            "message": str(info.get("message") or "").strip(),
            "time": float(d.get("recommTime") or 0),
        })
    out.sort(key=lambda r: r["time"])
    return out


def intro_text(message: str) -> str:
    return INTRO_WITH_MESSAGE.format(msg=message) if message else INTRO_WITHOUT_MESSAGE


def intro_event(conn: dict, req: dict, now: Optional[float] = None) -> dict:
    """The introduction as an inbox event, same shape as `zalo_personal_channel.chuan_hoa_tin`."""
    import zalo_personal_channel as zc
    now = time.time() if now is None else now
    stamp = int(req.get("time") or 0) or int(now)
    return {
        "channel": zc.KENH,
        "account_id": conn["id"],
        "account_name": conn.get("label") or "Zalo",
        "bot_id": "",
        "external_chat_id": req["uid"],
        "chat_type": "private",
        "chat_title": "",
        "sender_type": "customer",
        "sender_id": req["uid"],
        "sender_name": req.get("name") or "",
        "message_type": "text",
        "text": intro_text(req.get("message") or ""),
        # One id per request: running twice (a retry, a restart) finds the message already there.
        "external_message_id": f"friendreq-{req['uid']}-{stamp}",
        "created_at": now,
        "metadata": {"friend_request": True, "intro": req.get("message") or ""},
    }


async def run_once(conn: dict, now: Optional[float] = None) -> Dict[str, Any]:
    """One round for one account. Returns counts (and `error` when Zalo could not be read)."""
    import zalo_personal_channel as zc
    _last_check[str(conn["id"])] = time.time() if now is None else now
    home = zalo_cli.home_of(conn)
    if not home:
        return {"error": "no session folder"}
    sess = {"home": home}
    ok, data, err = await zalo_cli.run_cli(sess, ["friend", "recommendations"], [])
    if not ok:
        return {"error": err}
    reqs = received_requests(data)
    done = {"pending": len(reqs), "accepted": 0, "recorded": 0, "failed": 0}
    for i, req in enumerate(reqs[:MAX_PER_ROUND]):
        if i:
            await asyncio.sleep(ACCEPT_GAP)
        ok, _d, err = await zalo_cli.run_cli(sess, ["friend", "accept"], [req["uid"]])
        if not ok:
            done["failed"] += 1
            print(f"[zalo-friend {conn.get('label')}] accept {req['uid']} failed: {err}", file=sys.stderr)
            continue
        done["accepted"] += 1
        ev = intro_event(conn, req)
        kq = conversations.ghi_su_kien(ev)
        if kq.get("ok") and not kq.get("trung"):
            done["recorded"] += 1
            zc._giao_cho_bot(conn, ev)
    return done
