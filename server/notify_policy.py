"""Javis Core as the notification commander (0.403.0; owner, 2026-10-29).

Spec: docs/dev/2026-10-javis-core-chi-huy-thong-bao.md sections 3 to 6.

Every notice that reaches the bell has a GROUP (what it is about) and a LEVEL (info, important, urgent). Each group has
a MODE, the lowest level that still rings (all, important, urgent, off). The owner's default is "urgent": only urgent
notices ring, the rest are kept in the bell as already read and marked `filtered`. Javis Core's judge tunes the modes
and the per-kind rules from the owner's emoji feedback (the Resonance set, `reaction_values.REACTION_EMOJI`) and stops
a notice that repeats itself. Javis Core never silences an urgent notice; only the owner can (mode "off", or "Not
needed" on that very kind).

`decide` is the one place that turns (group, level, title) into loud / quiet / drop. The host (main.py) calls it from
`_notify_owner` and `_bo_vao_hom_thu` and does the delivery; this module only keeps the rules and the history, in
`STATE_DIR/notify_policy.json`, under one lock.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from config import STATE_DIR

STORE = STATE_DIR / "notify_policy.json"
_LOCK = threading.RLock()

GROUPS = ("job", "reminder", "question", "agent", "team", "incident", "connection", "chatbot", "cost", "update", "other")
LEVELS = ("info", "important", "urgent")
RANK = {"info": 0, "important": 1, "urgent": 2}
MODES = ("all", "important", "urgent", "off")
THRESHOLD = {"all": 0, "important": 1, "urgent": 2}
DEFAULT_MODE = "urgent"            # owner, 2026-10-29: "mặc định chỉ tin khẩn"

# Group names as shown (vi, en). The dashboard has its own i18n keys; these are for the chat tool and Core's messages.
GROUP_NAMES = {
    "job": ("Kết quả việc", "Job results"), "reminder": ("Nhắc lịch", "Reminders"),
    "question": ("Câu hỏi chờ bạn", "Questions for you"), "agent": ("Trợ lý chủ động", "Assistants reaching out"),
    "team": ("Nhóm làm việc", "Teams"), "incident": ("Sự cố", "Incidents"),
    "connection": ("Kết nối và đăng nhập", "Connections and sign-in"), "chatbot": ("Chatbot và khách", "Chatbot and customers"),
    "cost": ("Chi phí", "Costs"), "update": ("Cập nhật", "Updates"), "other": ("Khác", "Other"),
}
MODE_NAMES = {"all": ("Tất cả", "Everything"), "important": ("Đáng chú ý trở lên", "Important and up"),
              "urgent": ("Chỉ tin khẩn", "Urgent only"), "off": ("Tắt", "Off")}

# `source` of a notice -> its group (when the producer passes no group).
SOURCE_GROUP = {
    "reminder": "reminder", "job": "job", "webhook": "job", "github": "job", "goal": "job", "loop": "job",
    "watch": "connection", "engine": "connection", "connections": "connection", "zalo": "connection",
    "pulse": "agent", "team": "team", "resonance": "agent", "incident": "incident",
    "chatbot": "chatbot", "reply-policy": "chatbot", "zalo-group": "chatbot",
    "cost": "cost", "store": "update",
}

REPEAT_N = 3                  # the same kind rings this many times ...
REPEAT_WINDOW_S = 6 * 3600    # ... within this window, then is filtered for the rest of it (never an urgent one)
SCORE_WINDOW_S = 30 * 86400
GROUP_STEP = 4                # group score at which Core moves a group one notch
FEEDBACK_KEEP = 500
CHANGES_KEEP = 100
LOUD_KEEP = 20

# Points of one reaction (Resonance emoji set) and of the two axis buttons ("Nên báo" / "Không cần báo").
EMOJI_SCORE = {"like": 1, "love": 1, "wow": 1, "haha": 0, "sad": -1, "angry": -1}
AXES = {"needed": 2, "not_needed": -2}


def _now() -> float:
    return time.time()


def _blank() -> dict:
    return {"version": 1, "groups": {}, "signatures": {}, "feedback": [], "loud": {}, "changes": [], "dropped": {}}


def _load() -> dict:
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except OSError:
        return _blank()
    except ValueError as e:
        print(f"[notify policy] broken {STORE.name}: {e}", file=sys.stderr)
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
        print(f"[notify policy] cannot save: {e}", file=sys.stderr)


def _vi() -> bool:
    try:
        import localefmt
        return localefmt.chu("vi", "en") == "vi"
    except Exception:
        return True


def group_name(g: str) -> str:
    vi, en = GROUP_NAMES.get(g, GROUP_NAMES["other"])
    return vi if _vi() else en


def mode_name(m: str) -> str:
    vi, en = MODE_NAMES.get(m, MODE_NAMES[DEFAULT_MODE])
    return vi if _vi() else en


# ── classification ──────────────────────────────────────────────────────────────────────────────────────────────────
def group_of(source: str = "", kind: str = "", viec: Optional[dict] = None, dedup: str = "", group: str = "") -> str:
    """The group of a notice. An explicit `group` wins; a job asking the owner something is a question; else the source."""
    g = str(group or "").strip()
    if g in GROUPS:
        return g
    v = viec if isinstance(viec, dict) else {}
    if str(v.get("status") or "") == "hoi" or str(dedup or "").startswith("ask:"):
        return "question"
    s = str(source or "").strip()
    if s in SOURCE_GROUP:
        return SOURCE_GROUP[s]
    if v.get("kind") == "task" or str(kind or "") in ("answer", "report"):
        return "job"
    return "other"


def level_of(level: str = "", quiet: bool = False, group: str = "") -> str:
    """The level of a notice. An explicit `level` wins; a reminder or a question is urgent (the owner set it up, or
    someone waits on them); a quiet notice is info; anything else is important."""
    lv = str(level or "").strip()
    if lv in LEVELS:
        return lv
    if group in ("reminder", "question"):
        return "urgent"
    return "info" if quiet else "important"


_URL = re.compile(r"https?://\S+")
_NUM = re.compile(r"\d+")
_HEX = re.compile(r"\b[0-9a-f]{6,}\b")
_PUNCT = re.compile(r"[^\w#' ]+")


def signature(title: str) -> str:
    """What makes two notices "the same kind": the title without numbers, ids, times and links, so "Job 'X' failed,
    try 3" and "try 4" match while two different jobs (their quoted names) do not."""
    t = str(title or "").lower()
    t = _URL.sub(" ", t)
    t = _HEX.sub("#", t)
    t = _NUM.sub("#", t)
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())[:100]


def _key(group: str, sig: str) -> str:
    return f"{group}|{sig}"


def mode_of(group: str, d: Optional[dict] = None) -> dict:
    d = d if d is not None else _load()
    m = d["groups"].get(group) or {}
    mode = m.get("mode") if m.get("mode") in MODES else DEFAULT_MODE
    return {"mode": mode, "set_by": m.get("set_by") or "default", "since": float(m.get("since") or 0)}


# ── the decision ────────────────────────────────────────────────────────────────────────────────────────────────────
def decide(group: str, level: str, title: str, now: Optional[float] = None, record: bool = True) -> dict:
    """{"group", "level", "sig", "verdict": "loud"|"quiet"|"drop", "why"} for one notice.

    `why`: "mode" (below the group's mode), "off" (group off by the owner: dropped), "muted" / "always" (a per-kind rule),
    "repeat" (the same kind rang REPEAT_N times in REPEAT_WINDOW_S), "" (loud on its level). `record` keeps the time of a
    loud one for the repeat rule."""
    now = _now() if now is None else float(now)
    g = group if group in GROUPS else "other"
    lv = level if level in LEVELS else "important"
    sig = signature(title)
    out = {"group": g, "level": lv, "sig": sig, "verdict": "loud", "why": ""}
    with _LOCK:
        d = _load()
        m = mode_of(g, d)
        rule = (d["signatures"].get(_key(g, sig)) or {})
        if m["mode"] == "off" and m["set_by"] != "core":
            out.update(verdict="drop", why="off")
            d["dropped"][g] = int(d["dropped"].get(g) or 0) + 1
            _save(d)
            return out
        if rule.get("rule") == "mute" and (lv != "urgent" or rule.get("set_by") == "owner"):
            out.update(verdict="quiet", why="muted")
            return out
        if rule.get("rule") == "always":
            out["why"] = "always"
        else:
            threshold = THRESHOLD.get(m["mode"], 2) if m["mode"] != "off" else 2   # Core's "off" never hides urgent
            if RANK[lv] < threshold:
                out.update(verdict="quiet", why="mode")
                return out
        key = _key(g, sig)
        times = [t for t in (d["loud"].get(key) or []) if now - float(t) < REPEAT_WINDOW_S]
        if lv != "urgent" and len(times) >= REPEAT_N:
            out.update(verdict="quiet", why="repeat")
            return out
        if record:
            d["loud"][key] = (times + [now])[-LOUD_KEEP:]
            if len(d["loud"]) > 1000:
                for k in sorted(d["loud"], key=lambda k: max(d["loud"][k] or [0]))[:500]:
                    d["loud"].pop(k, None)
            _save(d)
    return out


# ── changes (owner or Core) ─────────────────────────────────────────────────────────────────────────────────────────
def _change(d: dict, kind: str, target: str, frm: Any, to: Any, reason: str, set_by: str, label: str = "") -> dict:
    c = {"id": uuid.uuid4().hex[:10], "ts": _now(), "kind": kind, "target": target, "from": frm, "to": to,
         "reason": str(reason or "")[:300], "set_by": set_by, "label": str(label or "")[:120], "undone": False}
    d["changes"].append(c)
    d["changes"] = d["changes"][-CHANGES_KEEP:]
    return c


def set_mode(group: str, mode: str, set_by: str = "owner", reason: str = "") -> Optional[dict]:
    """Set a group's mode. Returns the change, or None when nothing changed or the input is not valid."""
    if group not in GROUPS or mode not in MODES:
        return None
    with _LOCK:
        d = _load()
        cur = mode_of(group, d)
        if cur["mode"] == mode and cur["set_by"] == set_by:
            return None
        d["groups"][group] = {"mode": mode, "set_by": set_by, "since": _now()}
        c = _change(d, "group", group, cur["mode"], mode, reason, set_by, group_name(group))
        _save(d)
        return c


def set_rule(group: str, sig: str, rule: Optional[str], set_by: str = "owner", label: str = "", reason: str = "") -> Optional[dict]:
    """Per-kind rule: "mute" (filtered), "always" (always rings unless the owner turned the group off), None (removed)."""
    if group not in GROUPS or not sig or rule not in ("mute", "always", None):
        return None
    with _LOCK:
        d = _load()
        k = _key(group, sig)
        cur = (d["signatures"].get(k) or {}).get("rule")
        if cur == rule:
            return None
        if rule is None:
            d["signatures"].pop(k, None)
        else:
            d["signatures"][k] = {"rule": rule, "set_by": set_by, "label": str(label or sig)[:120], "at": _now()}
        c = _change(d, "kind", k, cur, rule, reason, set_by, label or sig)
        _save(d)
        return c


def undo(change_id: str) -> Optional[dict]:
    """Put back what one change replaced. Returns the undone change, or None."""
    with _LOCK:
        d = _load()
        c = next((x for x in d["changes"] if x.get("id") == change_id and not x.get("undone")), None)
        if c is None:
            return None
        if c["kind"] == "group":
            d["groups"][c["target"]] = {"mode": c["from"] if c["from"] in MODES else DEFAULT_MODE, "set_by": "owner",
                                        "since": _now()}
        else:
            if c["from"] in ("mute", "always"):
                old = d["signatures"].get(c["target"]) or {}
                d["signatures"][c["target"]] = {"rule": c["from"], "set_by": "owner", "label": old.get("label") or c.get("label"),
                                                "at": _now()}
            else:
                d["signatures"].pop(c["target"], None)
        c["undone"] = True
        _save(d)
        return c


# ── Javis Core's judge: learn from the owner's reactions ───────────────────────────────────────────────────────────
def score_of(value: str = "", axis: str = "") -> int:
    return int(EMOJI_SCORE.get(str(value or ""), 0)) + int(AXES.get(str(axis or ""), 0))


def react(item: dict, value: str = "", axis: str = "") -> List[dict]:
    """The owner reacted to one bell item. Records the feedback, then lets Core adjust. Returns Core's changes.

    - "Not needed" (`not_needed`) mutes that kind; on an urgent kind too, since the owner said it.
    - "Needed" (`needed`) on a filtered item makes that kind always ring.
    - The group's score since its last change, over 30 days: -GROUP_STEP or less lowers the group one notch;
      +GROUP_STEP or more, counted on filtered items, raises it one notch.
    """
    g = str(item.get("group") or "") or group_of(source=item.get("source") or "", kind=item.get("kind") or "")
    g = g if g in GROUPS else "other"
    sig = str(item.get("sig") or signature(item.get("title") or ""))
    filtered = bool(item.get("filtered"))
    pts = score_of(value, axis)
    label = str(item.get("title") or sig)[:120]
    changes: List[dict] = []
    with _LOCK:
        d = _load()
        d["feedback"].append({"ts": _now(), "group": g, "sig": sig, "score": pts, "filtered": filtered,
                              "value": str(value or ""), "axis": str(axis or "")})
        d["feedback"] = d["feedback"][-FEEDBACK_KEEP:]
        _save(d)
    vi = _vi()
    if axis == "not_needed":
        c = set_rule(g, sig, "mute", set_by="owner" if item.get("level") == "urgent" else "core", label=label,
                     reason=("Bạn bấm Không cần báo." if vi else "You pressed Not needed."))
        if c:
            changes.append(c)
    elif axis == "needed" and filtered:
        c = set_rule(g, sig, "always", set_by="core", label=label,
                     reason=("Bạn bấm Nên báo lên một tin đã lọc." if vi else "You pressed Needed on a filtered notice."))
        if c:
            changes.append(c)
    with _LOCK:
        d = _load()
        m = mode_of(g, d)
        since = max(m["since"], _now() - SCORE_WINDOW_S)
        fb = [f for f in d["feedback"] if f.get("group") == g and float(f.get("ts") or 0) >= since]
        total = sum(int(f.get("score") or 0) for f in fb)
        up = sum(int(f.get("score") or 0) for f in fb if f.get("filtered") and int(f.get("score") or 0) > 0)
    order = list(MODES)
    i = order.index(m["mode"])
    if total <= -GROUP_STEP and i < len(order) - 1:
        c = set_mode(g, order[i + 1], set_by="core",
                     reason=(f"Điểm phản hồi của nhóm là {total} (nhiều tin bạn thấy không cần)." if vi else
                             f"The group's feedback score is {total} (many notices you found unneeded)."))
        if c:
            changes.append(c)
    elif up >= GROUP_STEP and i > 0:
        c = set_mode(g, order[i - 1], set_by="core",
                     reason=(f"Bạn đánh giá tốt {up} điểm trên các tin đã lọc của nhóm." if vi else
                             f"You rated the group's filtered notices {up} points up."))
        if c:
            changes.append(c)
    return changes


def describe(c: dict, hint: bool = True) -> str:
    """One sentence about a change, for Javis Core's chat and the chat tool (`hint`: say where to undo it)."""
    vi = _vi()
    if c.get("kind") == "group":
        g = group_name(str(c.get("target")))
        s = (f"Em vừa chuyển nhóm {g} từ {mode_name(c.get('from'))} sang {mode_name(c.get('to'))}." if vi else
             f"I moved the group {g} from {mode_name(c.get('from'))} to {mode_name(c.get('to'))}.")
    else:
        lab = str(c.get("label") or "")
        to = c.get("to")
        if to == "mute":
            s = f"Em sẽ lọc các tin kiểu \"{lab}\"." if vi else f"I will filter notices like \"{lab}\"."
        elif to == "always":
            s = f"Em sẽ luôn báo các tin kiểu \"{lab}\"." if vi else f"I will always ring for notices like \"{lab}\"."
        else:
            s = f"Em bỏ luật riêng cho các tin kiểu \"{lab}\"." if vi else f"I removed the rule for notices like \"{lab}\"."
    if c.get("reason"):
        s += " " + str(c["reason"])
    if hint:
        s += (" Hoàn tác ở Bộ lọc thông báo của chuông." if vi else " Undo it in the bell's notification filter.")
    return s


def status(changes: int = 20) -> dict:
    """Modes of every group, the per-kind rules, recent changes and dropped counts (dashboard and chat tool)."""
    with _LOCK:
        d = _load()
    groups = [{"group": g, "name": group_name(g), **mode_of(g, d), "dropped": int(d["dropped"].get(g) or 0)} for g in GROUPS]
    rules = [{"key": k, "group": k.split("|", 1)[0], "sig": k.split("|", 1)[1] if "|" in k else "", **v}
             for k, v in d["signatures"].items()]
    rules.sort(key=lambda r: -float(r.get("at") or 0))
    recent = [dict(c, text=describe(c, hint=False)) for c in list(reversed(d["changes"]))[:max(1, int(changes))]]
    return {"groups": groups, "rules": rules, "changes": recent,
            "default": DEFAULT_MODE, "modes": list(MODES)}


def find_rules(query: str) -> List[dict]:
    """Per-kind rules whose label or signature contains `query` (chat tool, op=unmute)."""
    q = signature(query)
    return [r for r in status(0)["rules"] if q and (q in r.get("sig", "") or q in signature(r.get("label") or ""))]
