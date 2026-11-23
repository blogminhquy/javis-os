"""What earns a buzz on the owner's phone (owner, 2026-11-23: "bỏ thông báo rác, giữ thông báo hữu ích").

The bell's commander (notify_policy.py) decides whether a notice is loud. This module adds what it could not see:

- A. Learning from behaviour. Every push carries an id; dashboard/sw.js reports a tap ("open") or a swipe ("close").
  A push untouched for a day counts as ignored. A kind of notice the owner ignored `STREAK` times in a row, or opened
  less than `LOW_RATE` of the time over `MIN_RESOLVED` pushes, is handed back as a mute candidate; main.py turns it
  into a notify_policy rule set by Javis Core, which the owner can undo in the bell's filter. Urgent kinds never are.
- C. A daily budget (`push.daily_budget`, default 8, 0 = no limit): past it, a notice that is not urgent stops ringing
  and waits for the next digest.
- D. A digest at `DIGEST_TIMES`: the important notices that did not ring are counted in one push ("5 notices worth a
  look: Job results 3, Assistant suggestions 2"). `push.digest` = "off" turns it off.
- E. An "urgent" claim with no valid reason, or from a job that claims it on most runs, is lowered to important.
- Chat answers: one buzz per chat per `CHAT_GAP_S`, so talking and chatting does not ring at every turn.

State in STATE_DIR/push_policy.json, under one lock. main.py does the sending; this module never sends anything.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Callable, List, Optional

from config import STATE_DIR

STORE = STATE_DIR / "push_policy.json"
_LOCK = threading.RLock()

DEFAULT_BUDGET = 8
BUDGET_MAX = 50
CHAT_GAP_S = 600               # one buzz per chat per 10 minutes
IGNORE_AFTER_S = 24 * 3600     # a push nobody touched for a day counts as ignored
STREAK = 5                     # ignored this many times in a row -> mute candidate
MIN_RESOLVED = 10              # ... or this many resolved pushes ...
LOW_RATE = 0.2                 # ... opened less than this share of the time
SENT_KEEP = 800
DIGEST_TIMES = ("11:30", "17:30")
DIGEST_KEEP_S = 24 * 3600
DIGEST_MAX = 200
URGENT_WHY = ("error", "money", "customer", "question", "deadline")
ACT_WINDOW = 8                 # the last runs looked at for a job's urgent claims
ACT_MIN = 6                    # runs needed before the share counts
ACT_SHARE = 0.5                # claiming urgent on more than half of them is crying wolf

ANSWER_KEY = "answer|chat answer"   # notify_policy key of the chat-answer kind (group "answer")
DIGEST_KEY = "digest"
NO_LEARN = ("digest", "test")


def _now() -> float:
    return time.time()


def _blank() -> dict:
    return {"version": 1, "day": {"date": "", "count": 0}, "sent": [], "chat_last": {},
            "digest": {"queue": [], "last_slot": ""}, "act": {}, "learned": {}}


def _load() -> dict:
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except OSError:
        return _blank()
    except ValueError as e:
        print(f"[push policy] broken {STORE.name}: {e}", file=sys.stderr)
        return _blank()
    if not isinstance(d, dict):
        return _blank()
    for k, v in _blank().items():
        if not isinstance(d.get(k), type(v)):
            d[k] = v
    return d


def _save(d: dict) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STORE)
    except OSError as e:
        print(f"[push policy] cannot save: {e}", file=sys.stderr)


def _date(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _vi() -> bool:
    try:
        import localefmt
        return localefmt.chu("vi", "en") == "vi"
    except Exception:
        return True


# ── settings ────────────────────────────────────────────────────────────────────────────────────────────────────────
def budget(settings: Optional[dict]) -> int:
    """Pushes a day before notices that are not urgent stop ringing. 0 = no limit."""
    raw = ((settings or {}).get("push") or {}).get("daily_budget")
    if raw is None or raw == "":
        return DEFAULT_BUDGET
    try:
        return max(0, min(BUDGET_MAX, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def digest_on(settings: Optional[dict]) -> bool:
    return str(((settings or {}).get("push") or {}).get("digest") or "on") != "off"


# ── C. the daily budget ─────────────────────────────────────────────────────────────────────────────────────────────
def _today(d: dict, now: float) -> int:
    if d["day"].get("date") != _date(now):
        d["day"] = {"date": _date(now), "count": 0}
    return int(d["day"].get("count") or 0)


def count_today(now: Optional[float] = None) -> int:
    now = _now() if now is None else now
    with _LOCK:
        return _today(_load(), now)


def over_budget(level: str, settings: Optional[dict], now: Optional[float] = None) -> bool:
    """True when a notice of this level must not ring any more today. Urgent never is."""
    if level == "urgent":
        return False
    b = budget(settings)
    return bool(b) and count_today(now) >= b


# ── chat answers: one buzz per chat per CHAT_GAP_S ──────────────────────────────────────────────────────────────────
def chat_throttled(sid: str, now: Optional[float] = None) -> bool:
    now = _now() if now is None else now
    with _LOCK:
        last = float(_load()["chat_last"].get(str(sid or "")) or 0)
    return now - last < CHAT_GAP_S


# ── A. every push, and what the owner did with it ───────────────────────────────────────────────────────────────────
def record_push(key: str, kind: str, label: str = "", sid: str = "", level: str = "",
                now: Optional[float] = None) -> str:
    """Count one push against today's budget and remember it for learning. Returns its id (carried to sw.js)."""
    now = _now() if now is None else now
    nid = uuid.uuid4().hex[:12]
    with _LOCK:
        d = _load()
        d["day"]["count"] = _today(d, now) + 1
        d["sent"].append({"id": nid, "ts": now, "key": str(key or "")[:140], "kind": str(kind or "")[:12],
                          "label": str(label or "")[:120], "sid": str(sid or "")[:64], "level": str(level or "")[:12],
                          "ev": ""})
        d["sent"] = d["sent"][-SENT_KEEP:]
        if kind == "answer" and sid:
            d["chat_last"][str(sid)] = now
            if len(d["chat_last"]) > 300:
                for k in sorted(d["chat_last"], key=lambda k: d["chat_last"][k])[:100]:
                    d["chat_last"].pop(k, None)
        _save(d)
    return nid


def engage(nid: str, ev: str) -> Optional[dict]:
    """The owner tapped ("open") or swiped away ("close") one push. A tap is never overwritten by a later swipe."""
    if ev not in ("open", "close") or not nid:
        return None
    with _LOCK:
        d = _load()
        for s in reversed(d["sent"]):
            if s.get("id") == nid:
                if s.get("ev") != "open":
                    s["ev"] = ev
                    s["ev_ts"] = _now()
                    _save(d)
                return dict(s)
    return None


def _outcome(s: dict, now: float, seen: Optional[Callable[[dict], bool]]) -> str:
    """"open" | "close" | "ignore" | "neutral" (read elsewhere: neither good nor bad) | "" (too early to say)."""
    ev = s.get("ev") or ""
    if ev in ("open", "close"):
        return ev
    if now - float(s.get("ts") or 0) < IGNORE_AFTER_S:
        return ""
    try:
        if seen and seen(s):
            return "neutral"
    except Exception:  # noqa: BLE001
        pass
    return "ignore"


def learn(now: Optional[float] = None, seen: Optional[Callable[[dict], bool]] = None) -> List[dict]:
    """Kinds the owner keeps ignoring: [{"key", "label", "reason"}]. Only pushes after the last decision on a kind
    count, so an undone mute needs a fresh streak before it comes back. Urgent pushes never count."""
    now = _now() if now is None else now
    with _LOCK:
        d = _load()
    by: dict = {}
    for s in d["sent"]:
        k = s.get("key") or ""
        if not k or k in NO_LEARN or s.get("level") == "urgent":
            continue
        if float(s.get("ts") or 0) <= float(d["learned"].get(k) or 0):
            continue
        o = _outcome(s, now, seen)
        if o in ("open", "close", "ignore"):
            by.setdefault(k, []).append((o, s.get("label") or ""))
    vi = _vi()
    out = []
    for k, rows in by.items():
        outs = [o for o, _ in rows]
        label = rows[-1][1]
        opened = outs.count("open")
        if len(outs) >= STREAK and all(o != "open" for o in outs[-STREAK:]):
            reason = (f"{STREAK} lần gần nhất tin này báo lên điện thoại, bạn đều không mở." if vi else
                      f"You did not open the last {STREAK} of these on your phone.")
        elif len(outs) >= MIN_RESOLVED and opened / len(outs) < LOW_RATE:
            reason = (f"Bạn chỉ mở {opened}/{len(outs)} lần tin này báo lên điện thoại." if vi else
                      f"You opened only {opened} of {len(outs)} of these on your phone.")
        else:
            continue
        out.append({"key": k, "label": label, "reason": reason})
    return out


def mark_learned(key: str, now: Optional[float] = None) -> None:
    now = _now() if now is None else now
    with _LOCK:
        d = _load()
        d["learned"][str(key)] = now
        _save(d)


def stats(days: int = 7, now: Optional[float] = None, settings: Optional[dict] = None) -> dict:
    """The week in numbers for the bell's filter: pushes, opened, and the kinds opened least."""
    now = _now() if now is None else now
    with _LOCK:
        d = _load()
        today = _today(d, now)
    since = now - days * 86400
    rows = [s for s in d["sent"] if float(s.get("ts") or 0) >= since and s.get("key") != "test"]
    opened = sum(1 for s in rows if s.get("ev") == "open")
    kinds: dict = {}
    for s in rows:
        k = s.get("key") or ""
        e = kinds.setdefault(k, {"key": k, "label": s.get("label") or k, "sent": 0, "opened": 0})
        e["sent"] += 1
        e["opened"] += 1 if s.get("ev") == "open" else 0
        e["label"] = s.get("label") or e["label"]
    worst = sorted((v for v in kinds.values() if v["sent"] >= 3 and v["key"] != DIGEST_KEY),
                   key=lambda v: (v["opened"] / v["sent"], -v["sent"]))[:3]
    return {"days": days, "sent": len(rows), "opened": opened,
            "open_rate": round(opened / len(rows), 2) if rows else 0.0,
            "today": today, "budget": budget(settings), "digest": digest_on(settings),
            "digest_times": list(DIGEST_TIMES), "least_opened": worst}


# ── D. the digest ───────────────────────────────────────────────────────────────────────────────────────────────────
def queue_digest(item_id: str, group: str, title: str, now: Optional[float] = None) -> None:
    now = _now() if now is None else now
    with _LOCK:
        d = _load()
        q = [x for x in d["digest"]["queue"] if now - float(x.get("ts") or 0) < DIGEST_KEEP_S]
        if not any(x.get("id") == item_id for x in q):
            q.append({"id": str(item_id or ""), "group": str(group or "other"), "title": str(title or "")[:90], "ts": now})
        d["digest"]["queue"] = q[-DIGEST_MAX:]
        _save(d)


def digest_due(now: Optional[float] = None) -> str:
    """The digest slot ("YYYY-MM-DD HH:MM") due now and not sent yet, or ""."""
    now = _now() if now is None else now
    dt = datetime.fromtimestamp(now)
    hhmm = dt.strftime("%H:%M")
    past = [t for t in DIGEST_TIMES if t <= hhmm]
    if not past:
        return ""
    slot = f"{dt.strftime('%Y-%m-%d')} {past[-1]}"
    with _LOCK:
        return "" if _load()["digest"].get("last_slot") == slot else slot


def take_digest(slot: str, now: Optional[float] = None) -> List[dict]:
    """Close the slot and hand back what waited in it (fresher than a day)."""
    now = _now() if now is None else now
    with _LOCK:
        d = _load()
        items = [x for x in d["digest"]["queue"] if now - float(x.get("ts") or 0) < DIGEST_KEEP_S]
        d["digest"] = {"queue": [], "last_slot": slot}
        _save(d)
    return items


def digest_text(items: List[dict]) -> tuple:
    """(title, body) of one digest push, two short lines: how many, then how many of each group."""
    import notify_policy
    n = len(items)
    counts: dict = {}
    for x in items:
        counts[x.get("group") or "other"] = counts.get(x.get("group") or "other", 0) + 1
    parts = [f"{notify_policy.group_name(g)} {c}" for g, c in sorted(counts.items(), key=lambda kv: -kv[1])]
    if _vi():
        return f"{n} tin đáng xem trong chuông", ", ".join(parts)
    return f"{n} notice{'s' if n != 1 else ''} worth a look in the bell", ", ".join(parts)


# ── E. urgent needs a reason, and a job that always claims it loses it ──────────────────────────────────────────────
def act_check(key: str, claimed: bool, why: str = "") -> bool:
    """Record one run's urgent claim. True when the claim stands: a reason from URGENT_WHY, and the job does not claim
    urgent on more than ACT_SHARE of its last ACT_WINDOW runs (once it has ACT_MIN of them)."""
    k = str(key or "")[:140]
    with _LOCK:
        d = _load()
        runs = (d["act"].get(k) or []) + [1 if claimed else 0]
        d["act"][k] = runs[-ACT_WINDOW:]
        if len(d["act"]) > 500:
            for old in list(d["act"])[:100]:
                d["act"].pop(old, None)
        _save(d)
    if not claimed or str(why or "") not in URGENT_WHY:
        return False
    recent = runs[-ACT_WINDOW:]
    return len(recent) < ACT_MIN or sum(recent) / len(recent) <= ACT_SHARE


def reset() -> None:
    """Forget everything (tests)."""
    with _LOCK:
        _save(_blank())
