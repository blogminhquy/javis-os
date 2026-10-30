"""Accept incoming friend requests on a personal Zalo account and keep the introduction they carry (0.172.0).

Why this exists. The MTM owner asked (2026-10-15) for the bot to read the message that comes with a friend request
("I am Lan, mother of An, class 2K10") and keep it: someone who already introduced themselves must not be asked again,
someone who did not must be asked. That message only exists while the request is pending. Once the request is accepted
(on the phone or anywhere else) Zalo drops it, and the chat starts with a bare "you are now friends" line, so neither
the inbox nor the bot ever saw what the person wrote.

What it does, for each account whose bot on duty has `nhan_ket_ban` switched on (off by default, see chatbot_store):
  1. ask Zalo for received requests (`friend recommendations`, items with recommType 2) once every `POLL_SECONDS`
     (one hour: at most 24 calls a day per account, the owner's choice on 2026-10-15);
  2. accept the oldest ones (`friend accept`), at most `MAX_PER_ROUND` per round, `ACCEPT_GAP` seconds apart;
  3. write the introduction into the inbox as that person's first message (a fixed message id per request, so a
     repeat never writes twice), then hand it to the bot exactly like a message the person sent. The bot's own rules
     then decide: a complete introduction is acknowledged and not asked again; a partial one or none at all makes the
     bot ask for what is missing.

Rules that keep it from hurting the rest of the account (maintainer review of PR #657):
  - A round runs as its OWN task, one per account at a time (`start_round`), never inside the read loop: the loop also
    flushes the 5-second customer wait and the owner-silence hold for every account, so a slow Zalo must not pause it.
    Each CLI call gets `CLI_TIMEOUT` seconds and the whole round `ROUND_TIMEOUT`.
  - Nothing is accepted outside the bot's active hours (the bot would stay silent and the event would age past
    `TUOI_TOI_DA`, so the promised turn never comes) or when the bot answers only chosen people (accepting a stranger
    under the owner's name only to park them in the approval queue). Requests simply stay pending until then.
  - A failed accept stops the round, and that person is skipped for a while (`FAIL_BACKOFF`, doubling); after
    `MAX_FAILS` failures they are skipped until Javis restarts. Skipped people do not count toward `MAX_PER_ROUND`,
    so one refused request never starves the newer ones or makes Zalo calls every round forever.
  - The CLI commands used here exist in every javis-zalo release (v1.0.0 and later; Javis pins v1.9.0, see
    `zalo_cli.CLI_PACKAGE`). A CLI that answers "unknown command" anyway pauses intake for `UNSUPPORTED_WAIT`.

Everything goes through the same session as the rest of the account (`zalo_cli.run_cli` with the connection's HOME).
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import conversations
import localefmt
import zalo_cli

POLL_SECONDS = 3600        # one check per account per hour: 24 calls a day at most (owner's choice, 2026-10-15)
CLI_TIMEOUT = 20           # seconds for one CLI call (run_cli defaults to 120, made for file uploads)
ROUND_TIMEOUT = 120        # hard cap on one whole round
MAX_PER_ROUND = 10         # requests accepted per round; the rest wait for the next one
ACCEPT_GAP = 3             # seconds between two accepts, so a burst of requests does not look like a script
FAIL_BACKOFF = 600         # a refused accept skips that person this long, doubling per failure
MAX_FAILS = 3              # after this many failures the person is skipped until restart
UNSUPPORTED_WAIT = 6 * 3600  # the CLI does not know the command: try again this much later
MAX_INTRO = 500            # characters kept from the request message (untrusted text from a stranger)
MAX_NAME = 100             # characters kept from the display name
RECEIVED_REQUEST = 2       # zca-js FriendRecommendationsType.ReceivedFriendRequest

_poll: Dict[str, Dict[str, float]] = {}            # conn_id -> {"next": ts, "gap": seconds}
_fails: Dict[Tuple[str, str], Dict[str, float]] = {}  # (conn_id, uid) -> {"n": failures, "until": ts}
_tasks: Dict[str, "asyncio.Task"] = {}              # conn_id -> running round


def _bot_cfg(conn_id: str) -> Optional[dict]:
    import zalo_personal_channel as zc
    tb = zc._BOTS.get(str(conn_id))
    fn = getattr(tb, "cfg_fn", None)
    if not callable(fn):
        return None
    return fn() or {}


def why_not(conn_id: str, luc=None) -> str:
    """Why intake does NOT run for this account right now; "" means it may. Codes: no_bot, off, chosen_only, high_level,
    off_hours."""
    import chatbot_store
    try:
        cfg = _bot_cfg(conn_id)
    except Exception:      # noqa: BLE001 - a broken bot config must not break the read loop
        return "no_bot"
    if cfg is None:
        return "no_bot"
    if not chatbot_store.clean_bat(cfg.get("nhan_ket_ban")):
        return "off"
    # Same rule as chatbot_runtime._audience_cua: missing key = default, a broken value = the narrowest.
    aud = cfg.get("audience") if "audience" in cfg else chatbot_store.AUDIENCE_DEFAULT
    if aud not in chatbot_store.AUDIENCE:
        aud = chatbot_store.AUDIENCE_HEP_NHAT
    if aud == "chon":
        return "chosen_only"
    # Accepting a request lets a stranger reach this bot. At Can write or Full power (real outside actions) that is a
    # stranger driving those tools, so intake stays off there (review of #657, 0.172.0): lower the bot first.
    if str(cfg.get("muc_quyen") or "") in chatbot_store.MUC_NANG:
        return "high_level"
    if not chatbot_store.trong_gio_truc(cfg.get("gio_truc"), luc):
        return "off_hours"
    return ""


def enabled_for(conn_id: str, luc=None) -> bool:
    """May intake run for this account now (switched on, not 'only chosen people', inside active hours)?"""
    return not why_not(conn_id, luc)


def due(conn_id: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    return now >= float((_poll.get(str(conn_id)) or {}).get("next") or 0)


def _schedule(conn_id: str, found: bool, now: float, wait: Optional[float] = None) -> None:
    """Next check of this account: `POLL_SECONDS` from now, or `wait` when given. `found` is kept for callers and logs;
    the interval is the same either way (an hour is already as quiet as the owner wants)."""
    st = _poll.setdefault(str(conn_id), {"gap": POLL_SECONDS, "next": 0.0})
    st["gap"] = POLL_SECONDS
    st["next"] = now + (POLL_SECONDS if wait is None else wait)


def skipped(conn_id: str, uid: str, now: Optional[float] = None) -> bool:
    """Is this person backed off after failed accepts?"""
    f = _fails.get((str(conn_id), str(uid)))
    if not f:
        return False
    if f["n"] >= MAX_FAILS:
        return True
    return (time.time() if now is None else now) < f["until"]


def _note_failure(conn_id: str, uid: str, now: float) -> None:
    f = _fails.setdefault((str(conn_id), str(uid)), {"n": 0, "until": 0.0})
    f["n"] += 1
    f["until"] = now + FAIL_BACKOFF * (2 ** (f["n"] - 1))


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
        try:
            t = float(d.get("recommTime") or 0)
        except (TypeError, ValueError):
            t = 0.0
        out.append({
            "uid": uid,
            "name": str(d.get("displayName") or d.get("zaloName") or "").strip()[:MAX_NAME],
            "message": str(info.get("message") or "").strip()[:MAX_INTRO],
            "time": t,
        })
    out.sort(key=lambda r: r["time"])
    return out


def intro_text(message: str) -> str:
    """What lands in the Inbox (and reaches the bot) for one accepted request, in the owner's interface language."""
    message = str(message or "").strip()[:MAX_INTRO]
    if message:
        return localefmt.chu("[Lời nhắn kèm lời mời kết bạn, nick vừa chấp nhận] {msg}",
                             "[Message sent with the friend request, just accepted] {msg}", msg=message)
    return localefmt.chu("[Vừa kết bạn, người này không kèm lời nhắn giới thiệu]",
                         "[Just became friends, this person sent no introduction]")


def intro_event(conn: dict, req: dict, now: Optional[float] = None) -> dict:
    """The introduction as an inbox event, same shape as `zalo_personal_channel.chuan_hoa_tin`."""
    import zalo_personal_channel as zc
    now = time.time() if now is None else now
    stamp = int(req.get("time") or 0) or int(now)
    msg = str(req.get("message") or "")[:MAX_INTRO]
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
        "sender_name": str(req.get("name") or "")[:MAX_NAME],
        "message_type": "text",
        "text": intro_text(msg),
        # One id per request: running twice (a retry, a restart) finds the message already there.
        "external_message_id": f"friendreq-{req['uid']}-{stamp}",
        "created_at": now,
        "metadata": {"friend_request": True, "intro": msg},
    }


def _unsupported(err: str) -> bool:
    w = str(err or "").lower()
    return "unknown command" in w or "unknown option" in w


async def run_once(conn: dict, now: Optional[float] = None) -> Dict[str, Any]:
    """One round for one account. Returns counts (and `error` when Zalo could not be read). Schedules the next round."""
    import zalo_personal_channel as zc
    cid = str(conn["id"])
    now = time.time() if now is None else now
    _schedule(cid, False, now, wait=POLL_SECONDS)      # provisional: a round that dies midway is not retried at once
    home = zalo_cli.home_of(conn)
    if not home:
        _schedule(cid, False, now)
        return {"error": "no session folder"}
    sess = {"home": home}
    ok, data, err = await zalo_cli.run_cli(sess, ["friend", "recommendations"], [], timeout=CLI_TIMEOUT)
    if not ok:
        if _unsupported(err):
            _schedule(cid, False, now, wait=UNSUPPORTED_WAIT)
            return {"error": err, "unsupported": True}
        _schedule(cid, False, now)
        return {"error": err}
    reqs = received_requests(data)
    todo = [r for r in reqs if not skipped(cid, r["uid"], now)]
    done = {"pending": len(reqs), "skipped": len(reqs) - len(todo), "accepted": 0, "recorded": 0, "failed": 0}
    started = time.monotonic()
    for i, req in enumerate(todo[:MAX_PER_ROUND]):
        if i:
            if time.monotonic() - started > ROUND_TIMEOUT / 2:
                break       # leave the rest for the next round rather than run into the hard cap
            await asyncio.sleep(ACCEPT_GAP)
        # The owner may switch it off, or active hours may end, while a round is running.
        if not enabled_for(cid):
            break
        ok, _d, err = await zalo_cli.run_cli(sess, ["friend", "accept"], [req["uid"]], timeout=CLI_TIMEOUT)
        if not ok:
            # Stop at the first refusal: a blocked or rate-limited account fails every accept, and hammering it
            # ten times a round only makes that worse. This person waits; the others get their turn next round.
            # A timeout lands here too. If Zalo did accept despite it, the request is gone next round and its
            # message with it, the same as an accept made on the phone.
            _note_failure(cid, req["uid"], time.time())
            done["failed"] += 1
            print(f"[zalo-friend {conn.get('label')}] accept {req['uid']} failed: {err}", file=sys.stderr)
            break
        _fails.pop((cid, req["uid"]), None)
        done["accepted"] += 1
        ev = intro_event(conn, req)
        kq = conversations.ghi_su_kien(ev)
        if kq.get("ok") and not kq.get("trung"):
            done["recorded"] += 1
            zc._giao_cho_bot(conn, ev)
    _schedule(cid, bool(todo), now)
    return done


async def _round(conn: dict) -> None:
    label = conn.get("label")
    try:
        kq = await asyncio.wait_for(run_once(conn), ROUND_TIMEOUT)
        if kq.get("error") or kq.get("accepted") or kq.get("failed"):
            print(f"[zalo-friend {label}] {kq}", file=sys.stderr)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        print(f"[zalo-friend {label}] round over {ROUND_TIMEOUT}s, stopped", file=sys.stderr)
    except Exception as e:      # noqa: BLE001 - a side job: log it, never take the read loop down with it
        print(f"[zalo-friend {label}] error: {type(e).__name__}: {e}", file=sys.stderr)


def running(conn_id: str) -> bool:
    t = _tasks.get(str(conn_id))
    return bool(t) and not t.done()


def start_round(conn: dict, now: Optional[float] = None) -> bool:
    """Called from the read loop after a successful read. Starts a round in its OWN task when one is due and none is
    running for this account; returns at once either way. True when a round was started."""
    cid = str(conn.get("id") or "")
    if not cid or running(cid) or not due(cid, now) or not enabled_for(cid):
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    _schedule(cid, False, time.time() if now is None else now, wait=POLL_SECONDS)   # the task sets the real next time
    t = loop.create_task(_round(dict(conn)))
    _tasks[cid] = t
    t.add_done_callback(lambda _t, c=cid: _tasks.pop(c, None) if _tasks.get(c) is _t else None)
    return True


def cancel_all() -> None:
    """Stop every running round (the read loop is stopping)."""
    for t in list(_tasks.values()):
        if not t.done():
            t.cancel()
    _tasks.clear()
