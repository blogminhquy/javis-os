"""Which dedicated chatbot made a job (0.429.0).

Owner, 31/10/2026: the Tasks page listed every reminder, loop and Kanban job under Javis Core, while most of them
were made by the owner's Zalo assistant bot. A job made in a chatbot's turn now carries that bot:

  - a reminder: `bot_id` in reminders.json (javis_schedule reads the bot from turn_context);
  - a loop: `bot_id:` in its frontmatter;
  - a Kanban job: `created_by = "bot:<id>"` (javis_task).

Jobs made before this version carry nothing, so this module guesses them from the bot's own turn log
(chatbot_log.py: one line per answered turn, written when the turn ends). A job belongs to a bot when it was created
during one of that bot's turns (at most WINDOW_S before the turn's line) and, when the job names a chat, in that
same chat. Two bots answering at that moment is no answer: the job stays with Javis Core rather than with a guess.
A guess, once made, is kept in <brain>/Javis/bot-jobs.json, because the turn log is trimmed and the proof would go.

`GET /tasks/bots?brain=` hands the page the brain's bots and the job -> bot map. task_stats uses the same map.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from fastapi import APIRouter, Query

WINDOW_S = 900            # a turn that ran tools for up to 15 minutes still claims the jobs it made
SIDECAR = "bot-jobs.json"
MAX_SIDECAR = 5000
_BOT_ID = re.compile(r"^bot_[A-Za-z0-9_-]{1,64}$")
_lock = threading.Lock()


@dataclass
class BotJobsDeps:
    brain_root: Callable[[str], str]
    list_bots: Callable[[], list]                    # chatbot_store.list_bots
    turns: Callable[[str], list]                     # chatbot_log._nap: the bot's logged turns, oldest first
    task_store: Optional[Callable[[], Any]] = None   # the Kanban TaskStore
    loops: Optional[Callable[[str], list]] = None    # brain root -> parsed loops (self_improve.list_loops)


def bot_of(created_by: str) -> str:
    """"bot:<id>" -> "<id>", anything else -> ""."""
    s = str(created_by or "")
    return s[4:] if s.startswith("bot:") and _BOT_ID.match(s[4:]) else ""


def _root(deps: BotJobsDeps, brain: str) -> str:
    try:
        return str(Path(deps.brain_root(brain)).resolve())
    except Exception:
        return ""


def bots_for(deps: BotJobsDeps, root: str) -> list:
    """The chatbots whose brain is this brain: {id, name, icon, agent}."""
    out = []
    for b in deps.list_bots() or []:
        if not isinstance(b, dict) or not _BOT_ID.match(str(b.get("id") or "")):
            continue
        br = str(b.get("brain") or "").strip()
        if not br or _root(deps, br) != root:
            continue
        out.append({"id": b["id"], "name": str(b.get("name") or b.get("slug") or b["id"]),
                    "icon": str(b.get("icon") or ""), "agent": str((b.get("agent") or {}).get("slug") or "")})
    return out


def answered_turns(rows: Iterable[dict]) -> list:
    """(ts, chat_id) of the turns a bot really answered: skipped messages and broken turns ran no tools."""
    out = []
    for r in rows or []:
        try:
            if r.get("bo_qua") or (r.get("loi") and not r.get("dap")):
                continue
            out.append((float(r.get("ts") or 0), str(r.get("chat_id") or "")))
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def _chat(c) -> str:
    """A chat id without its channel prefix ("zalo:123" and "123" are the same chat)."""
    return re.sub(r"^[a-z_]+:", "", str(c or "").strip())


def guess(created_at: float, chat_id: str, turns: dict) -> str:
    """The one bot whose turn was running when a job was created, "" when none or more than one.
    `turns`: {bot_id: [(ts, chat_id), ...]}. `chat_id` "" (a job that names no chat) matches any chat."""
    try:
        t0 = float(created_at or 0)
    except (TypeError, ValueError):
        return ""
    if t0 <= 0:
        return ""
    cid = _chat(chat_id)
    hit = set()
    for bid, rows in (turns or {}).items():
        for ts, c in rows:
            if 0 <= ts - t0 <= WINDOW_S and (not cid or _chat(c) == cid):
                hit.add(bid)
                break
    return hit.pop() if len(hit) == 1 else ""


def guess_loop(owner_chat: str, day: str, turns: dict, tz=None) -> str:
    """A loop has no creation time, only the day it was last saved (`updated`). It belongs to a bot when it names a
    chat and exactly one bot answered that chat that day. A loop naming no chat stays with Javis Core."""
    from datetime import datetime
    cid, day = _chat(owner_chat), str(day or "").strip()
    if not cid or not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return ""
    hit = {bid for bid, rows in (turns or {}).items()
           if any(_chat(c) == cid and datetime.fromtimestamp(ts, tz).date().isoformat() == day for ts, c in rows)}
    return hit.pop() if len(hit) == 1 else ""


def _sidecar(root: str) -> Path:
    return Path(root) / "Javis" / SIDECAR


def _load_sidecar(root: str) -> dict:
    try:
        d = json.loads(_sidecar(root).read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in (d.get("jobs") or {}).items() if _BOT_ID.match(str(v))}
    except Exception:
        return {}


def _save_sidecar(root: str, jobs: dict) -> None:
    p = _sidecar(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        items = list(jobs.items())[-MAX_SIDECAR:]
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"jobs": dict(items)}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except Exception as e:  # noqa: BLE001 - attribution is a nicety, never break the page for it
        print(f"[bot-jobs] {type(e).__name__}: {e}")


def _reminders(root: str) -> list:
    try:
        return json.loads((Path(root) / "Javis" / "reminders.json").read_text(encoding="utf-8")).get("reminders") or []
    except Exception:
        return []


def _kanban(store, root: str) -> list:
    if store is None:
        return []
    try:
        with store._lock:
            return [dict(r) for r in store._db.execute(
                "SELECT id, created_by, chat_id, created_at FROM tasks WHERE brain_root = ? AND COALESCE(lane, '') <> 'team'",
                (root,)).fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"[bot-jobs] kanban unreadable: {type(e).__name__}: {e}")
        return []


def job_map(deps: BotJobsDeps, brain: str, tz=None) -> dict:
    """{"bots": [...], "jobs": {"r:<id>" | "l:<slug>" | "k:<id>": bot id}} for one brain."""
    root = _root(deps, brain)
    bots = bots_for(deps, root) if root else []
    if not bots:
        return {"bots": [], "jobs": {}}
    ids = {b["id"] for b in bots}
    turns = {}
    for b in bots:
        try:
            turns[b["id"]] = answered_turns(deps.turns(b["id"]))
        except Exception:
            turns[b["id"]] = []
    with _lock:
        kept = _load_sidecar(root)
        jobs, fresh = {}, False
        for r in _reminders(root):
            key = "r:" + str(r.get("id") or "")
            bid = str(r.get("bot_id") or "")
            if not bid and key in kept:
                bid = kept[key]
            elif not bid and str(r.get("created_by") or "") not in ("dashboard",):
                bid = guess(r.get("created_at"), r.get("chat_id"), turns)
                if bid:
                    kept[key], fresh = bid, True
            if bid in ids:
                jobs[key] = bid
        loops = []
        if deps.loops:
            try:
                loops = deps.loops(root) or []
            except Exception:
                loops = []
        for lp in loops:
            key = "l:" + str(lp.get("slug") or "")
            bid = str(lp.get("bot_id") or "")
            if not bid and key in kept:
                bid = kept[key]
            elif not bid:
                bid = guess_loop(lp.get("owner_chat"), lp.get("updated"), turns, tz)
                if bid:
                    kept[key], fresh = bid, True
            if bid in ids:
                jobs[key] = bid
        for t in _kanban(deps.task_store() if deps.task_store else None, root):
            key = "k:" + str(t.get("id") or "")
            cb = str(t.get("created_by") or "")
            bid = bot_of(cb)
            if not bid and key in kept:
                bid = kept[key]
            elif not bid and cb == "chat":
                bid = guess(t.get("created_at"), t.get("chat_id"), turns)
                if bid:
                    kept[key], fresh = bid, True
            if bid in ids:
                jobs[key] = bid
        if fresh:
            _save_sidecar(root, kept)
    return {"bots": bots, "jobs": jobs}


class BotJobs:
    CACHE_S = 20   # the page polls every few seconds; the turn logs need not be read that often

    def __init__(self, deps: BotJobsDeps, tz: Optional[Callable[[], Any]] = None):
        self.deps = deps
        self._tz = tz
        self._cache: dict = {}
        self.router = APIRouter()

        @self.router.get("/tasks/bots")
        async def tasks_bots(brain: str = Query("brain")):
            return {"ok": True, **self.map(brain)}

    def map(self, brain: str) -> dict:
        hit = self._cache.get(brain)
        if hit and time.time() - hit[0] < self.CACHE_S:
            return hit[1]
        out = job_map(self.deps, brain, self._tz() if self._tz else None)
        self._cache[brain] = (time.time(), out)
        return out


def register(app, deps: BotJobsDeps, tz: Optional[Callable[[], Any]] = None) -> BotJobs:
    feat = BotJobs(deps, tz)
    app.include_router(feat.router)
    return feat
