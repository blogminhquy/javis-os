"""Read back the BILL PHOTOS sent to tuition groups while the machine was off (10/11/2026).

Why: javis-zalo keeps what it recovers after a gap in its history file, but a photo that reaches the bot later than
`TUOI_TOI_DA` seconds is dropped by `Transport.xu_ly`, so a bill sent at 20:57 and read at 11:26 next morning was never
recorded. This module finds those photos once the first read after a restart succeeded and hands each one to the bot
through the normal bill path, one at a time, oldest first.

Hard rails (each has a test in tests/python/test_zalo_group_catchup.py):
  G1  only PHOTOS from other people that have an image link. Text never enters the catch-up queue.
  G2  only groups in `catchup_group_images.group_ids` AND in the bot's own groups; bot and connection on.
  G3  the window is bounded by `max_hours`; with no baseline nothing is read (no guessing).
  G4  no photo is given twice: `zalo_catchup_done`, the live "delivered to the bot" book, then Sunny's own idempotency.
  G5  `max_per_run` photos per run, the rest is reported.
  G6  sequential, oldest first, a pause between photos.
  G7  free text or images the bot wants to send in a catch-up turn are NOT sent (`Transport.xu_ly`); only the tool sends.
  G8  the age gate opens only for a (connection, message) registered here in RAM, never for a metadata flag.
  G9  kill switches: the bot field and the env var `JAVIS_ZALO_GROUP_CATCHUP=0`.
  G10 a run stops when the bot or the connection goes off.
  G11 one summary in the bell (never Zalo).

Persistent state lives in `conversations.sync_state` (no new table):
  zalo_alive:<conn>          epoch seconds of the last heartbeat
  zalo_catchup_done:<conn>   JSON {msg_id: epoch} of photos already given to the bot (newest 2000, 7 days)
  zalo_catchup_last:<conn>   JSON of the last run's statistics
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import conversations
import localefmt

KENH = "zalo_personal"
HEARTBEAT_EVERY = 60
ALIVE_MARGIN = 120          # seconds taken off the last heartbeat: the machine was alive a bit before the last write
FIRST_SCAN_DELAY = 90       # let Zalo replay its backlog into the live buffer first
SECOND_SCAN_DELAY = 300     # catches a replay that arrives late; shares the book of done messages
PAUSE_BETWEEN = 2.0
TURN_TIMEOUT = 240
DONE_KEEP = 2000
DONE_DAYS = 7
DELIVERED_CAP = 5000
FLUSH_EVERY = 10
QUICK_RESTART_S = 30        # a gap shorter than this skips the history file (route B)
HISTORY_FILE = (".zalo-agent-cli", "history.jsonl")
STATE_FILE = (".zalo-agent-cli", "sync-state.json")
_PHOTO_URL = re.compile(r"^https://photo[^\s]*\.zdn\.vn/\S+$")

_REG: set = set()                       # (conn, msg_id) being read back right now (G8)
_OUTCOME: Dict[tuple, dict] = {}        # (conn, msg_id) -> what `Transport.xu_ly` did with it
_DELIVERED: Dict[tuple, float] = {}     # (conn, msg_id) -> time the bot was handed the photo (live path too)
_PENDING_FLUSH: Dict[str, Dict[str, float]] = {}
_LAST_FLUSH: Dict[str, float] = {}
_LAST_HB: Dict[str, float] = {}
_JOBS: Dict[str, dict] = {}             # conn -> {"epoch": float, "tasks": [Task]}
_RUNNING: set = set()


# ============================================================
# Settings
# ============================================================
def killed() -> bool:
    return os.environ.get("JAVIS_ZALO_GROUP_CATCHUP", "").strip() == "0"


def _tb(conn_id: str) -> Any:
    import zalo_personal_channel as zc
    return zc._BOTS.get(str(conn_id))


def settings(conn_id: str) -> Optional[dict]:
    """The catch-up settings of the bot standing on this connection, with the groups to scan, or None when it must not run
    (G2, G9): no bot, bot off, kill switch, `on` false, no group left after intersecting with the bot's groups."""
    if killed():
        return None
    tb = _tb(conn_id)
    cfg_fn = getattr(tb, "cfg_fn", None)
    if tb is None or cfg_fn is None:
        return None
    try:
        import chatbot_store
        bot = cfg_fn() or {}
        if bot.get("enabled") is False:
            return None
        cu = chatbot_store.clean_catchup(bot.get("catchup_group_images"))
        if not cu["on"] or not bot.get("accept_group_images"):
            return None
        own = {str(g) for g in (bot.get("groups") or [])}
        chats = [g for g in cu["group_ids"] if g in own]
        if not chats:
            return None
        return dict(cu, chats=chats, skipped_groups=[g for g in cu["group_ids"] if g not in own],
                    bot_id=str(bot.get("id") or ""), bot_name=str(bot.get("name") or ""))
    except Exception as e:      # noqa: BLE001
        print(f"[zalo-catchup] settings: {type(e).__name__}: {e}", file=sys.stderr)
        return None


# ============================================================
# Books: heartbeat, registered, delivered, done
# ============================================================
def heartbeat(conn_id: str, now: Optional[float] = None) -> None:
    now = time.time() if now is None else float(now)
    cid = str(conn_id)
    if now - _LAST_HB.get(cid, 0.0) < HEARTBEAT_EVERY:
        return
    _LAST_HB[cid] = now
    conversations.ghi_trang_thai("zalo_alive:" + cid, str(int(now)))


def is_registered(conn_id: str, msg_id: str) -> bool:
    return (str(conn_id), str(msg_id)) in _REG


def register(conn_id: str, msg_id: str) -> None:
    _REG.add((str(conn_id), str(msg_id)))


def consume(conn_id: str, msg_id: str) -> None:
    _REG.discard((str(conn_id), str(msg_id)))
    _OUTCOME.pop((str(conn_id), str(msg_id)), None)


def note(conn_id: str, msg_id: str, **kv: Any) -> None:
    """`Transport.xu_ly` reports what it did with a registered message (reason it stopped, text it was stopped from sending)."""
    k = (str(conn_id), str(msg_id))
    if k in _REG:
        _OUTCOME.setdefault(k, {}).update(kv)


def outcome(conn_id: str, msg_id: str) -> dict:
    return dict(_OUTCOME.get((str(conn_id), str(msg_id))) or {})


def _load_done(conn_id: str) -> Dict[str, float]:
    try:
        d = json.loads(conversations.doc_trang_thai("zalo_catchup_done:" + str(conn_id), "{}") or "{}")
    except ValueError:
        return {}
    return {str(k): float(v) for k, v in d.items()} if isinstance(d, dict) else {}


def _save_done(conn_id: str, d: Dict[str, float], now: float) -> None:
    keep = {k: v for k, v in d.items() if now - float(v) < DONE_DAYS * 86400}
    if len(keep) > DONE_KEEP:
        keep = dict(sorted(keep.items(), key=lambda kv: kv[1])[-DONE_KEEP:])
    conversations.ghi_trang_thai("zalo_catchup_done:" + str(conn_id), json.dumps(keep))


def mark_delivered(conn_id: str, msg_id: str, persist: bool = False, now: Optional[float] = None) -> None:
    """The bot is about to see this message (live path or catch-up). G4: a photo the bot already handled is not given again.
    `persist` (group photos) also goes to `zalo_catchup_done`, in batches, so it survives a restart."""
    now = time.time() if now is None else float(now)
    cid, mid = str(conn_id), str(msg_id or "")
    if not mid:
        return
    _DELIVERED[(cid, mid)] = now
    if len(_DELIVERED) > DELIVERED_CAP:
        for k in sorted(_DELIVERED, key=_DELIVERED.get)[:DELIVERED_CAP // 5]:
            _DELIVERED.pop(k, None)
    if persist:
        _PENDING_FLUSH.setdefault(cid, {})[mid] = now
        if now - _LAST_FLUSH.get(cid, 0.0) >= FLUSH_EVERY:
            flush(cid, now)


def flush(conn_id: str, now: Optional[float] = None) -> None:
    now = time.time() if now is None else float(now)
    cid = str(conn_id)
    pend = _PENDING_FLUSH.pop(cid, None)
    _LAST_FLUSH[cid] = now
    if not pend:
        return
    d = _load_done(cid)
    d.update(pend)
    _save_done(cid, d, now)


def already_done(conn_id: str, msg_id: str, done: Optional[Dict[str, float]] = None) -> bool:
    cid, mid = str(conn_id), str(msg_id)
    if (cid, mid) in _DELIVERED or mid in (_PENDING_FLUSH.get(cid) or {}):
        return True
    return mid in (done if done is not None else _load_done(cid))


# ============================================================
# Window
# ============================================================
def _home(conn: dict) -> str:
    return str(((conn or {}).get("env") or {}).get("HOME") or "") or os.path.expanduser("~")


def _read_gap_starts(conn: dict, since: float) -> List[float]:
    """Start (seconds) of every gap javis-zalo noted that ended after `since`. `recovered` is NOT a filter: it means javis-zalo
    put the gap's messages in ITS history file, which is exactly where this module reads them from."""
    try:
        with open(os.path.join(_home(conn), *STATE_FILE), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for g in (st.get("gaps") or []) if isinstance(st, dict) else []:
        try:
            a, b = float(g["from"]) / 1000.0, float(g["to"]) / 1000.0
        except (KeyError, TypeError, ValueError):
            continue
        if b >= since:
            out.append(a)
    return out


def compute_window(conn: dict, den: float, max_hours: int) -> Optional[tuple]:
    """`(tu, den)` in seconds, or None when there is no baseline (G3). `tu` is the earliest of the last heartbeat minus a margin
    and the start of any gap javis-zalo noted inside the allowed range, never older than `max_hours`."""
    floor = den - max_hours * 3600
    cands: List[float] = []
    try:
        alive = float(conversations.doc_trang_thai("zalo_alive:" + str(conn["id"]), "0") or 0)
    except ValueError:
        alive = 0.0
    if alive > 0:
        cands.append(alive - ALIVE_MARGIN)
    cands.extend(_read_gap_starts(conn, floor))
    cands = [c for c in cands if c < den]
    if not cands:
        return None
    return max(min(cands), floor), den


# ============================================================
# Candidates
# ============================================================
def _photo_event(conn: dict, row: dict) -> dict:
    return {
        "channel": KENH, "account_id": conn["id"], "account_name": conn.get("label") or "Zalo", "bot_id": "",
        "external_chat_id": str(row["external_chat_id"]), "chat_type": "group", "chat_title": str(row.get("chat_title") or ""),
        "sender_type": "customer", "sender_id": str(row.get("sender_id") or ""), "sender_name": str(row.get("sender_name") or ""),
        "message_type": "image", "text": str(row.get("text") or ""), "external_message_id": str(row["external_message_id"]),
        "created_at": float(row["created_at"]), "metadata": dict(row.get("metadata") or {}),
    }


def read_history(conn: dict, chats: set, tu: float, den: float) -> List[dict]:
    """Photo lines of javis-zalo's history file for these groups inside the window (read only)."""
    path = os.path.join(_home(conn), *HISTORY_FILE)
    out = []
    try:
        with open(path, "rb") as f:
            for line in f:
                if b"chat.photo" not in line:
                    continue
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(m, dict) or m.get("type") != "chat.photo" or m.get("isSelf"):
                    continue
                if str(m.get("threadId") or "") not in chats or str(m.get("threadType") or "").lower() not in ("group", "1"):
                    continue
                ts = float(m.get("timestamp") or 0) / 1000.0
                if tu <= ts <= den and m.get("msgId") not in (None, ""):
                    out.append(m)
    except OSError:
        return []
    return out


def gather(conn: dict, chats: List[str], tu: float, den: float, *, quick: bool = False,
           history_fn: Optional[Callable] = None) -> dict:
    """Route A (the conversation store) + route B (javis-zalo history), merged by message id, route A first (G1).
    Returns {"events": [...oldest first], "no_image": [{...}]} where `no_image` are captioned photos whose picture cannot be
    fetched again (history has the caption but no link)."""
    cid = str(conn["id"])
    by_id: Dict[str, dict] = {}
    for r in conversations.group_images_between(KENH, cid, chats, tu, den):
        ev = _photo_event(conn, r)
        if str((ev["metadata"] or {}).get("image_url") or "").startswith("https://"):
            by_id[ev["external_message_id"]] = ev
    no_image: List[dict] = []
    if not quick:
        import zalo_personal_channel as zc
        names = {c: {"name": "", "type": "group"} for c in chats}
        for m in (history_fn or read_history)(conn, set(chats), tu, den):
            mid = str(m["msgId"])
            if mid in by_id:
                continue
            txt = str(m.get("text") or "").strip()
            if txt and not _PHOTO_URL.match(txt):
                no_image.append({"chat": str(m.get("threadId") or ""), "sender": str(m.get("senderName") or ""),
                                 "at": float(m.get("timestamp") or 0) / 1000.0, "caption": txt[:120], "msg_id": mid})
                continue
            ev = zc.chuan_hoa_tin(conn, dict(m, threadType="group"), names)
            if (ev and ev.get("chat_type") == "group" and ev.get("message_type") == "image"
                    and str((ev.get("metadata") or {}).get("image_url") or "").startswith("https://")):
                ev["sender_type"] = "customer"
                by_id[mid] = ev
    events = sorted(by_id.values(), key=lambda e: float(e.get("created_at") or 0))
    return {"events": events, "no_image": no_image}


# ============================================================
# One run
# ============================================================
def _still_on(conn_id: str) -> bool:
    return settings(conn_id) is not None


async def run_once(conn_id: str, *, reason: str = "manual", now: Optional[float] = None, den: Optional[float] = None,
                   tu: Optional[float] = None, pause: float = PAUSE_BETWEEN, history_fn: Optional[Callable] = None,
                   notify: bool = True) -> dict:
    """Scan once and hand the missed bill photos to the bot. `tu`/`den` override the computed window (used for the one-off
    replay the owner asks for, still bounded by the same rails except the baseline). Returns the run's statistics."""
    import zalo_personal_channel as zc
    cid = str(conn_id)
    now = time.time() if now is None else float(now)
    stats: Dict[str, Any] = {"reason": reason, "at": now, "given": 0, "skipped": {}, "no_image": [], "blocked_text": [],
                             "errors": []}

    def skip(why: str) -> None:
        stats["skipped"][why] = stats["skipped"].get(why, 0) + 1

    if cid in _RUNNING:
        stats["skipped_run"] = "already_running"
        return stats
    st = settings(cid)
    conn = zc.ket_noi_theo_id(cid)
    if st is None or conn is None:
        stats["skipped_run"] = "off"
        return stats
    _RUNNING.add(cid)
    try:
        den = float((zc._TT.get(cid) or {}).get("first_read") or now) if den is None else float(den)
        if tu is None:
            w = compute_window(conn, den, st["max_hours"])
            if w is None:
                stats["skipped_run"] = "no_baseline"
                _save_last(cid, stats)
                return stats
            tu = w[0]
        tu = max(float(tu), den - st["max_hours"] * 3600)
        stats.update(window=[tu, den], groups=len(st["chats"]), skipped_groups=st["skipped_groups"])
        tb = _tb(cid)
        got = gather(conn, st["chats"], tu, den, quick=(den - tu) < QUICK_RESTART_S, history_fn=history_fn)
        stats["no_image"] = got["no_image"]
        done = _load_done(cid)
        todo = [e for e in got["events"] if not already_done(cid, e["external_message_id"], done)]
        stats["found"] = len(got["events"])
        stats["duplicate"] = len(got["events"]) - len(todo)
        if stats["duplicate"]:
            stats["skipped"]["duplicate"] = stats["duplicate"]
        over = todo[st["max_per_run"]:]
        todo = todo[:st["max_per_run"]]
        if over:
            stats["skipped"]["over_limit"] = len(over)
            stats["over_limit"] = [{"chat": e["external_chat_id"], "sender": e["sender_name"], "at": e["created_at"]}
                                   for e in over]
        for i, ev in enumerate(todo):
            if _stop_flag() or not _still_on(cid) or _tb(cid) is not tb:
                stats["skipped_run"] = "stopped_midway"      # G10
                break
            mid = ev["external_message_id"]
            ev["metadata"] = dict(ev.get("metadata") or {}, recovered=True,
                                  doc_bu={"sent_at": ev["created_at"], "run": reason})
            register(cid, mid)
            try:
                try:
                    conversations.ghi_su_kien(ev, dem_chua_doc=False, late=True)
                except Exception as e:      # noqa: BLE001 - the inbox row is a convenience, never a reason to stop
                    print(f"[zalo-catchup] inbox write: {type(e).__name__}: {e}", file=sys.stderr)
                mark_delivered(cid, mid)
                try:
                    await asyncio.wait_for(tb.xu_ly(ev), TURN_TIMEOUT)
                except asyncio.TimeoutError:
                    stats["errors"].append(f"{mid}: timeout")
                except Exception as e:      # noqa: BLE001
                    stats["errors"].append(f"{mid}: {type(e).__name__}")
                oc = outcome(cid, mid)
                if oc.get("blocked_text"):
                    stats["blocked_text"].append({"msg_id": mid, "text": str(oc["blocked_text"])[:300]})
                if oc.get("answered"):
                    stats["given"] += 1
                    mark_delivered(cid, mid, persist=True)      # a turn that did not finish (restart, error) is tried again
                else:
                    skip(str(oc.get("stopped") or "not_processed"))
            finally:
                consume(cid, mid)
            if i + 1 < len(todo) and pause:
                await asyncio.sleep(pause)
        flush(cid, now)
        _save_last(cid, stats)
        if notify and (stats["given"] or stats["skipped"] or stats["no_image"] or stats["errors"] or stats["blocked_text"]):
            send_summary(st, stats)
        return stats
    finally:
        _RUNNING.discard(cid)


def _stop_flag() -> bool:
    import zalo_personal_channel as zc
    return bool(getattr(zc, "_stop", False))


def _save_last(conn_id: str, stats: dict) -> None:
    conversations.ghi_trang_thai("zalo_catchup_last:" + str(conn_id), json.dumps(stats, ensure_ascii=False, default=str))


# ============================================================
# Summary for the owner (G11): the bell, never Zalo
# ============================================================
def _hm(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), localefmt.tz()).strftime("%H:%M %d/%m")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def summary_text(st: dict, stats: dict) -> str:
    w = stats.get("window") or [0, 0]
    lines = [localefmt.chu(
        f"Bot {st.get('bot_name') or st.get('bot_id')} vừa đọc bù ảnh bill trong nhóm học phí, quãng {_hm(w[0])} đến {_hm(w[1])}, "
        f"{stats.get('groups', 0)} nhóm.",
        f"Bot {st.get('bot_name') or st.get('bot_id')} read back bill photos in the tuition groups, {_hm(w[0])} to {_hm(w[1])}, "
        f"{stats.get('groups', 0)} groups.")]
    lines.append(localefmt.chu(f"Đã đưa vào quy trình bill: {stats.get('given', 0)} ảnh.",
                               f"Given to the bill flow: {stats.get('given', 0)} photo(s)."))
    if stats.get("skipped"):
        lines.append(localefmt.chu("Bỏ qua: ", "Skipped: ") + ", ".join(f"{k} {v}" for k, v in sorted(stats["skipped"].items())) + ".")
    if stats.get("no_image"):
        lines.append(localefmt.chu("Ảnh có chú thích nhưng không lấy lại được ảnh (anh xem tay):",
                                   "Captioned photos whose picture cannot be fetched again (check by hand):"))
        for x in stats["no_image"][:15]:
            lines.append(f"- {_hm(x['at'])} {x['sender']}: {x['caption']}")
    if stats.get("over_limit"):
        lines.append(localefmt.chu(f"Còn {len(stats['over_limit'])} ảnh vượt trần mỗi lượt, chưa xử lý.",
                                   f"{len(stats['over_limit'])} photo(s) over the per-run cap were left."))
    if stats.get("blocked_text"):
        lines.append(localefmt.chu("Bot định nói nhưng đã bị chặn (lượt đọc bù không nói tự do):",
                                   "The bot wanted to say this but it was blocked (catch-up turns never talk freely):"))
        for x in stats["blocked_text"][:5]:
            lines.append(f"- {x['text']}")
    if stats.get("errors"):
        lines.append(localefmt.chu("Lỗi: ", "Errors: ") + "; ".join(stats["errors"][:5]))
    return "\n".join(lines)


def send_summary(st: dict, stats: dict) -> bool:
    try:
        import chatbot_runtime
        fn = chatbot_runtime._deps.get("notify")
        if not fn:
            return False
        r = fn(summary_text(st, stats))
        if asyncio.iscoroutine(r):
            asyncio.ensure_future(r)
        return True
    except Exception as e:      # noqa: BLE001
        print(f"[zalo-catchup] summary: {type(e).__name__}: {e}", file=sys.stderr)
        return False


# ============================================================
# Scheduling (T5)
# ============================================================
async def _after(conn_id: str, delay: float, label: str) -> None:
    await asyncio.sleep(delay)
    try:
        await run_once(conn_id, reason=label)
    except Exception as e:      # noqa: BLE001
        print(f"[zalo-catchup] {label}: {type(e).__name__}: {e}", file=sys.stderr)


def on_first_read(conn_id: str, first_read_at: float, delays: tuple = (FIRST_SCAN_DELAY, SECOND_SCAN_DELAY)) -> bool:
    """Called by the read loop once per epoch after the first successful read. Creates the two timed scans, only when this
    connection has a bot with the catch-up on. A second call in the same epoch does nothing; a new epoch cancels the old tasks."""
    cid = str(conn_id)
    cur = _JOBS.get(cid)
    if cur and cur["epoch"] == first_read_at:
        return False
    cancel(cid)
    if settings(cid) is None:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    tasks = [loop.create_task(_after(cid, d, f"scan{i + 1}"), name=f"zalo-catchup-{cid}-{i + 1}")
             for i, d in enumerate(delays)]
    _JOBS[cid] = {"epoch": first_read_at, "tasks": tasks}
    return True


def cancel(conn_id: Optional[str] = None) -> None:
    for cid in ([str(conn_id)] if conn_id is not None else list(_JOBS)):
        job = _JOBS.pop(cid, None)
        for t in (job or {}).get("tasks") or []:
            t.cancel()
