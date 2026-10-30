"""The owner's own tasks for the Tasks page, tab "Mine" (0.423.0). Spec: docs/dev/2026-10-nhiem-vu-spec.md 8.2.

One JSON store per brain at <brain>/Javis/my-tasks.json:

    {"tasks": [...], "projects": [...], "rev": n}

A repeating task is ONE record; each finished occurrence is a key of `done_dates` ("YYYY-MM-DD" ->
{"at": epoch, "by": "me" | "javis"}). The missed occurrence shown under Overdue, streaks and the like are
computed from the schedule and `done_dates` (the page does it, see dashboard/tasks.js), never stored.

Routes (all JSON bodies, `brain` like the other stores):
    GET  /my-tasks?brain                      -> {ok, tasks, projects, rev}
    POST /my-tasks                            create a task, -> {ok, task}
    POST /my-tasks/update   {id, ...fields}   -> {ok, task}
    POST /my-tasks/check    {id, date?, by?}  done (one occurrence of a repeating task when `date`)
    POST /my-tasks/uncheck  {id, date?}
    POST /my-tasks/delete   {id}
    POST /my-tasks/restore  {task}            put a deleted task back (undo)
    POST /my-tasks/move     {id, from_brain, to_brain, copy?}
    POST /my-tasks/project  {id?, name, color, pinned, order}   create or update
    POST /my-tasks/project/delete {id}        its tasks keep living, without a project
"""
from __future__ import annotations

import asyncio
import calendar
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Query

import localefmt

STORE = "my-tasks.json"
MAX_TASKS = 2000
MAX_DONE_DATES = 800            # per repeating task: a bit over two years of daily ticks
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^\d{2}:\d{2}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
KINDS = ("task", "appt")
UNITS = ("day", "week", "month", "year")
REMINDS = ("auto", "time", "off")


@dataclass
class MyTasksDeps:
    brain_root: Callable[[str], str]
    atomic_write_text: Callable[[str, str], None]
    # Habit reminders (0.424.0): the brains the scheduler visits, how to reach the owner, and the local time zone.
    scheduler_brains: Optional[Callable[[], list]] = None
    notify: Optional[Callable[..., Any]] = None
    tz: Optional[Callable[[], Any]] = None


def _now() -> float:
    return time.time()


def _err(vi: str, en: str) -> dict:
    return {"ok": False, "error": localefmt.chu(vi, en)}


def _clean_date(v) -> Optional[str]:
    v = str(v or "").strip()
    return v if _DATE.match(v) else None


def _clean_time(v) -> str:
    v = str(v or "").strip()
    return v if _TIME.match(v) and int(v[:2]) < 24 and int(v[3:]) < 60 else ""


def clean_repeat(r) -> Optional[dict]:
    """{unit, n, days} or None. `days` are weekdays 0 (Sunday) .. 6, used by a weekly repeat."""
    if not isinstance(r, dict):
        return None
    unit = str(r.get("unit") or "")
    if unit not in UNITS:
        return None
    try:
        n = max(1, min(365, int(r.get("n") or 1)))
    except (TypeError, ValueError):
        n = 1
    out = {"unit": unit, "n": n}
    if unit == "week":
        days = sorted({int(d) for d in (r.get("days") or []) if str(d).lstrip("-").isdigit() and 0 <= int(d) <= 6})
        out["days"] = days
    return out


def clean_habit(h) -> Optional[dict]:
    if not isinstance(h, dict):
        return None
    out = {"start": _clean_date(h.get("start")) or time.strftime("%Y-%m-%d"),
           "remind": h.get("remind") if h.get("remind") in REMINDS else "auto",
           "at": _clean_time(h.get("at")) or "21:00"}
    if h.get("off"):
        out["off"] = True
    return out


def _apply(task: dict, p: dict) -> None:
    """Copy the editable fields of payload `p` onto `task`, cleaned. Missing keys are left as they are."""
    if "title" in p:
        task["title"] = str(p.get("title") or "").strip()[:300]
    if "notes" in p:
        task["notes"] = str(p.get("notes") or "")[:5000]
    if "kind" in p and p.get("kind") in KINDS:
        task["kind"] = p["kind"]
    if "date" in p:
        task["date"] = _clean_date(p.get("date"))
    if "time" in p:
        task["time"] = _clean_time(p.get("time"))
    if "end" in p:
        task["end"] = _clean_time(p.get("end"))
    if "repeat" in p:
        task["repeat"] = clean_repeat(p.get("repeat"))
    if "project" in p:
        task["project"] = str(p.get("project") or "")[:40]
    if "remind" in p:
        task["remind"] = str(p.get("remind") or "")[:8]
    if "location" in p:
        task["location"] = str(p.get("location") or "")[:300]
    if "subs" in p and isinstance(p.get("subs"), list):
        task["subs"] = [{"t": str(x.get("t") or "")[:300], "done": bool(x.get("done"))}
                        for x in p["subs"][:50] if isinstance(x, dict) and str(x.get("t") or "").strip()]
    if "habit" in p:
        task["habit"] = clean_habit(p.get("habit"))
    if "from_javis" in p:
        task["from_javis"] = bool(p.get("from_javis"))
    if "prep" in p:
        task["prep"] = str(p.get("prep") or "")[:500]


# ---------------------------------------------------------------- habits (0.424.0)
# Mirror of the page's habit maths (dashboard/tasks.js occursOn / habitCalc) for the server-side nudge.
def _dnum(iso: str) -> int:
    return date.fromisoformat(iso).toordinal()


def occurs_on(rep: Optional[dict], anchor: str, iso: str) -> bool:
    """Whether a repeat rule anchored on `anchor` falls on `iso` (weeks start on Monday, like the page)."""
    if not rep or not anchor or iso < anchor:
        return False
    n = max(1, int(rep.get("n") or 1))
    d0, d = _dnum(anchor), _dnum(iso)
    unit = rep.get("unit")
    if unit == "day":
        return (d - d0) % n == 0
    if unit == "week":
        days = rep.get("days") or [(date.fromisoformat(anchor).weekday() + 1) % 7]
        if (date.fromisoformat(iso).weekday() + 1) % 7 not in days:
            return False
        return ((d - date.fromisoformat(iso).weekday()) // 7 - (d0 - date.fromisoformat(anchor).weekday()) // 7) % n == 0
    s, x = date.fromisoformat(anchor), date.fromisoformat(iso)
    last = calendar.monthrange(x.year, x.month)[1]
    day_ok = s.day == x.day or (s.day > last and x.day == last)
    if unit == "month":
        return day_ok and ((x.year - s.year) * 12 + (x.month - s.month)) % n == 0
    if unit == "year":
        return s.month == x.month and day_ok and (x.year - s.year) % n == 0
    return False


def habit_state(task: dict, today: str) -> dict:
    """cur, frozen, done_today, rest for one habit (same rules as the page: scheduled days only, one miss freezes,
    two in a row lose the streak)."""
    rep, hb = task.get("repeat"), task.get("habit") or {}
    anchor = task.get("date") or hb.get("start") or today
    start = max(anchor, hb.get("start") or anchor)
    dd = task.get("done_dates") or {}
    cur, miss, prev, days = 0, 0, None, {}
    d = date.fromisoformat(start)
    end = date.fromisoformat(today)
    while d <= end:
        iso = d.isoformat()
        if not occurs_on(rep, anchor, iso):
            days[iso] = "r"
        elif iso == today and iso not in dd:
            days[iso] = "todo"
            break
        elif iso in dd:
            cur, miss, days[iso] = cur + 1, 0, "f"
        else:
            miss += 1
            if miss == 1:
                days[iso] = "i"
            else:
                days[iso] = "x"
                if prev and days.get(prev) == "i":
                    days[prev] = "x"
                cur = 0
        if days[iso] != "r":
            prev = iso
        d += timedelta(days=1)
    last = prev if prev and prev != today else None
    rest = days.get(today) == "r"
    return {"cur": cur, "rest": rest, "done_today": days.get(today) == "f",
            "frozen": bool(last and days.get(last) == "i" and (days.get(today) == "todo" or rest))}


def usual_time(task: dict, tz=None) -> str:
    """Median time of the last 30 ticks, "" with fewer than 3."""
    dd = task.get("done_dates") or {}
    mins = sorted(
        (lambda t: t.hour * 60 + t.minute)(datetime.fromtimestamp(float(v.get("at") or 0), tz))
        for k, v in sorted(dd.items())[-30:] if isinstance(v, dict) and float(v.get("at") or 0) > 0)
    if len(mins) < 3:
        return ""
    m = mins[len(mins) // 2]
    return f"{m // 60:02d}:{m % 60:02d}"


def nudge_time(task: dict, state: dict, tz=None) -> str:
    """When today's reminder goes out: the set time, or for "Javis reminds" half an hour after the usual time
    (earlier while frozen, so there is room to thaw it)."""
    hb = task.get("habit") or {}
    if hb.get("remind") == "time":
        return hb.get("at") or "21:00"
    base = usual_time(task, tz) or task.get("time") or hb.get("at") or "21:00"
    m = int(base[:2]) * 60 + int(base[3:5])
    m = max(6 * 60, m - 30) if state.get("frozen") else min(23 * 60, m + 30)
    return f"{m // 60:02d}:{m % 60:02d}"


def nudge_text(task: dict, state: dict) -> str:
    title = task.get("title") or ""
    if state.get("frozen"):
        return localefmt.chu(
            f"Nhắc giữ lửa: {title}. Lần trước bạn đã bỏ, làm hôm nay là gỡ băng, bỏ nữa là mất chuỗi {state['cur']} ngày.",
            f"Habit reminder: {title}. You skipped last time; do it today to thaw it, skip again and the {state['cur']}-day streak is gone.")
    if state.get("cur"):
        return localefmt.chu(f"Nhắc giữ lửa: {title}. Chuỗi đang {state['cur']} ngày, làm nốt hôm nay nhé.",
                             f"Habit reminder: {title}. The streak is at {state['cur']} days, do today's one.")
    return localefmt.chu(f"Nhắc thói quen: {title}. Làm hôm nay để bắt đầu chuỗi giữ lửa.",
                         f"Habit reminder: {title}. Do it today to start the streak.")


class MyTasks:
    def __init__(self, deps: MyTasksDeps):
        self.deps = deps
        self._io = asyncio.Lock()
        self.router = self._make_router()

    # ---- store ----
    def _path(self, brain: str) -> Path:
        return Path(self.deps.brain_root(brain)) / "Javis" / STORE

    def load(self, brain: str) -> dict:
        p = self._path(brain)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                d.setdefault("tasks", [])
                d.setdefault("projects", [])
                d.setdefault("rev", 0)
                return d
        except FileNotFoundError:
            pass
        except Exception as e:   # a broken file is kept aside, never silently overwritten
            try:
                p.rename(p.with_suffix(".broken-%d.json" % int(_now())))
            except Exception:
                pass
            print(f"[my-tasks] unreadable store {p}: {type(e).__name__}: {e}")
        return {"tasks": [], "projects": [], "rev": 0}

    def save(self, brain: str, data: dict) -> None:
        data["rev"] = int(data.get("rev") or 0) + 1
        data["tasks"] = data.get("tasks", [])[-MAX_TASKS:]
        p = self._path(brain)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.deps.atomic_write_text(str(p), json.dumps(data, ensure_ascii=False, indent=1))

    @staticmethod
    def _find(data: dict, tid: str) -> Optional[dict]:
        return next((t for t in data.get("tasks", []) if t.get("id") == tid), None)

    # ---- operations (sync, call under self._io) ----
    def create(self, brain: str, p: dict) -> dict:
        title = str(p.get("title") or "").strip()
        if not title:
            return _err("thiếu tên việc", "the task needs a title")
        now = _now()
        task = {"id": "m_" + uuid.uuid4().hex[:10], "kind": "task", "title": title, "notes": "", "date": None,
                "time": "", "end": "", "repeat": None, "project": "", "status": "open", "done_at": 0,
                "done_dates": {}, "subs": [], "remind": "", "location": "", "habit": None,
                "created_at": now, "updated_at": now}
        _apply(task, p)
        if task.get("habit") and not task.get("repeat"):
            task["repeat"] = {"unit": "day", "n": 1}
        data = self.load(brain)
        data["tasks"].append(task)
        self.save(brain, data)
        return {"ok": True, "task": task, "rev": data["rev"]}

    def update(self, brain: str, p: dict) -> dict:
        data = self.load(brain)
        task = self._find(data, str(p.get("id") or ""))
        if task is None:
            return _err("không thấy việc này", "task not found")
        _apply(task, p)
        if not task.get("title"):
            return _err("thiếu tên việc", "the task needs a title")
        task["updated_at"] = _now()
        self.save(brain, data)
        return {"ok": True, "task": task, "rev": data["rev"]}

    def check(self, brain: str, tid: str, date: str = "", by: str = "me", done: bool = True) -> dict:
        data = self.load(brain)
        task = self._find(data, tid)
        if task is None:
            return _err("không thấy việc này", "task not found")
        by = "javis" if by == "javis" else "me"
        if task.get("repeat"):
            d = _clean_date(date) or time.strftime("%Y-%m-%d")
            dd = task.setdefault("done_dates", {})
            if done:
                dd[d] = {"at": _now(), "by": by}
                if len(dd) > MAX_DONE_DATES:
                    for k in sorted(dd)[:len(dd) - MAX_DONE_DATES]:
                        dd.pop(k, None)
            else:
                dd.pop(d, None)
        else:
            task["status"] = "done" if done else "open"
            task["done_at"] = _now() if done else 0
            if done:
                task["done_by"] = by
        task["updated_at"] = _now()
        self.save(brain, data)
        return {"ok": True, "task": task, "rev": data["rev"]}

    def delete(self, brain: str, tid: str) -> dict:
        data = self.load(brain)
        task = self._find(data, tid)
        if task is None:
            return _err("không thấy việc này", "task not found")
        data["tasks"] = [t for t in data["tasks"] if t.get("id") != tid]
        self.save(brain, data)
        return {"ok": True, "task": task, "rev": data["rev"]}

    def restore(self, brain: str, task: dict) -> dict:
        if not isinstance(task, dict) or not str(task.get("id") or "").startswith("m_"):
            return _err("dữ liệu việc không hợp lệ", "invalid task data")
        data = self.load(brain)
        if self._find(data, task["id"]) is None:
            data["tasks"].append(task)
            self.save(brain, data)
        return {"ok": True, "rev": data["rev"]}

    def move(self, from_brain: str, to_brain: str, tid: str, copy: bool = False) -> dict:
        try:
            if Path(self.deps.brain_root(from_brain)).resolve() == Path(self.deps.brain_root(to_brain)).resolve():
                return _err("brain nguồn và đích trùng nhau", "source and target brain are the same")
        except Exception:
            return _err("brain không hợp lệ", "invalid brain")
        src = self.load(from_brain)
        task = self._find(src, tid)
        if task is None:
            return _err("không thấy việc này", "task not found")
        item = json.loads(json.dumps(task))
        if copy:
            item["id"] = "m_" + uuid.uuid4().hex[:10]
            item["created_at"] = item["updated_at"] = _now()
        item["project"] = ""   # projects belong to a brain
        dst = self.load(to_brain)
        dst["tasks"].append(item)
        self.save(to_brain, dst)          # target first: a crash in between leaves a duplicate, not a loss
        if not copy:
            src["tasks"] = [t for t in src["tasks"] if t.get("id") != tid]
            self.save(from_brain, src)
        return {"ok": True, "task": item}

    def project(self, brain: str, p: dict) -> dict:
        data = self.load(brain)
        pid = str(p.get("id") or "")
        cur = next((x for x in data["projects"] if x.get("id") == pid), None) if pid else None
        if cur is None:
            name = str(p.get("name") or "").strip()
            if not name:
                return _err("thiếu tên dự án", "the project needs a name")
            cur = {"id": "p_" + uuid.uuid4().hex[:8], "name": name[:80], "color": "#3b82f6", "pinned": False,
                   "order": len(data["projects"])}
            data["projects"].append(cur)
        if str(p.get("name") or "").strip():
            cur["name"] = str(p["name"]).strip()[:80]
        if _COLOR.match(str(p.get("color") or "")):
            cur["color"] = str(p["color"]).lower()
        if "pinned" in p:
            cur["pinned"] = bool(p.get("pinned"))
        if "order" in p:
            try:
                cur["order"] = int(p.get("order"))
            except (TypeError, ValueError):
                pass
        self.save(brain, data)
        return {"ok": True, "project": cur, "rev": data["rev"]}

    def project_delete(self, brain: str, pid: str) -> dict:
        data = self.load(brain)
        cur = next((x for x in data["projects"] if x.get("id") == pid), None)
        if cur is None:
            return _err("không thấy dự án này", "project not found")
        data["projects"] = [x for x in data["projects"] if x.get("id") != pid]
        moved = [t["id"] for t in data["tasks"] if t.get("project") == pid]
        for t in data["tasks"]:
            if t.get("project") == pid:
                t["project"] = ""
        self.save(brain, data)
        return {"ok": True, "project": cur, "tasks": moved, "rev": data["rev"]}

    # ---- habit reminders (0.424.0) ----
    async def tick(self) -> int:
        """Send today's habit reminders that are due: once a day per habit, only on a scheduled day that is not done
        yet, at the set time or (Javis reminds) half an hour after the usual time. Returns how many went out."""
        if not self.deps.notify:
            return 0
        tz = self.deps.tz() if self.deps.tz else None
        now = datetime.now(tz)
        today, hm = now.date().isoformat(), now.strftime("%H:%M")
        try:
            brains = list(self.deps.scheduler_brains() or []) if self.deps.scheduler_brains else []
        except Exception:
            brains = []
        sent, seen = 0, set()
        for brain in brains + ["brain"]:
            try:
                root = str(Path(self.deps.brain_root(brain)).resolve())
            except Exception:
                continue
            if root in seen or not self._path(brain).exists():
                continue
            seen.add(root)
            due = []
            async with self._io:
                data = self.load(brain)
                for t in data.get("tasks", []):
                    hb = t.get("habit") or {}
                    if not t.get("repeat") or not hb or hb.get("off") or hb.get("remind") == "off" or hb.get("nudged") == today:
                        continue
                    st = habit_state(t, today)
                    if st["rest"] or st["done_today"] or hm < nudge_time(t, st, tz):
                        continue
                    hb["nudged"] = today
                    due.append((t, st))
                if due:
                    self.save(brain, data)
            for t, st in due:
                try:
                    await self.deps.notify("", nudge_text(t, st), brain=brain, dedup=f"habit:{t.get('id')}:{today}")
                    sent += 1
                except Exception as e:
                    print(f"[my-tasks] habit reminder not sent: {type(e).__name__}: {e}")
        return sent

    # ---- routes ----
    def _make_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/my-tasks")
        async def my_tasks_list(brain: str = Query("brain")):
            async with self._io:
                d = self.load(brain)
            return {"ok": True, "tasks": d["tasks"], "projects": d["projects"], "rev": d["rev"]}

        @router.post("/my-tasks")
        async def my_tasks_create(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.create(str(p.get("brain") or "brain"), p)

        @router.post("/my-tasks/update")
        async def my_tasks_update(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.update(str(p.get("brain") or "brain"), p)

        @router.post("/my-tasks/check")
        async def my_tasks_check(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.check(str(p.get("brain") or "brain"), str(p.get("id") or ""), str(p.get("date") or ""),
                                  str(p.get("by") or "me"), True)

        @router.post("/my-tasks/uncheck")
        async def my_tasks_uncheck(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.check(str(p.get("brain") or "brain"), str(p.get("id") or ""), str(p.get("date") or ""),
                                  "me", False)

        @router.post("/my-tasks/delete")
        async def my_tasks_delete(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.delete(str(p.get("brain") or "brain"), str(p.get("id") or ""))

        @router.post("/my-tasks/restore")
        async def my_tasks_restore(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.restore(str(p.get("brain") or "brain"), p.get("task"))

        @router.post("/my-tasks/move")
        async def my_tasks_move(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.move(str(p.get("from_brain") or "brain"), str(p.get("to_brain") or ""),
                                 str(p.get("id") or ""), bool(p.get("copy")))

        @router.post("/my-tasks/project")
        async def my_tasks_project(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.project(str(p.get("brain") or "brain"), p)

        @router.post("/my-tasks/project/delete")
        async def my_tasks_project_delete(payload: dict = Body(None)):
            p = payload or {}
            async with self._io:
                return self.project_delete(str(p.get("brain") or "brain"), str(p.get("id") or ""))

        return router


def register(app, deps: MyTasksDeps) -> MyTasks:
    feat = MyTasks(deps)
    app.include_router(feat.router)
    return feat
