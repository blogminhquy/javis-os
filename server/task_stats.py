"""Stats for the Tasks page, both tabs (0.428.0). Design approved by the owner on 2026-10-31.

    GET  /tasks/stats?brain&from=YYYY-MM-DD&to=YYYY-MM-DD   (both days included, local time zone)
    POST /tasks/stats/minutes {brain, minutes: {kind: n}}    how many minutes the owner would spend on each kind of job

What Javis did comes from three places, since no single store keeps it:
  - Kanban jobs: `task_events` of the Kanban store ("completed", "blocked", "retry_scheduled"), which survive the
    auto-archive of finished jobs;
  - loops: the markdown run log <brain>/Javis/loop-log/YYYY-MM-DD.md (headers carry the local time);
  - reminders and page watches: work_log.py (one line per finished run, written from 0.428.0 on). A reminder that
    ran before that only counts its last run (`fired_at`).
What the owner did comes from my_tasks (done_at, done_dates, appointments that already took place).

Time given back is an estimate: each finished job counts the minutes the owner says that kind of job would take them
(MINUTES, editable on the page). No money: the owner asked for time only.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Query

import my_tasks as my_tasks_mod
import work_log

MINUTES = {"kanban": 20, "reminder": 10, "notify": 2, "loop": 5, "watch": 3}
KINDS = tuple(MINUTES)
OWNER_KINDS = ("needs_input", "capability")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LOOP_HEAD = re.compile(r"^## \[(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})\] (.+?) · loop", re.M)
MAX_DAYS = 400


@dataclass
class TaskStatsDeps:
    brain_root: Callable[[str], str]
    my_tasks: Callable[[], Any]                      # the MyTasks feature
    task_store: Optional[Callable[[], Any]] = None   # the Kanban TaskStore
    tz: Optional[Callable[[], Any]] = None
    agent_names: Optional[Callable[[str], dict]] = None   # brain -> {slug: name}
    bot_jobs: Optional[Callable[[str], dict]] = None      # brain -> bot_jobs.job_map (0.429.0)


# ---------- helpers ----------
def _day(iso: str) -> date:
    return date.fromisoformat(iso)


def _ts(d: date, tz) -> float:
    return datetime(d.year, d.month, d.day, tzinfo=tz).timestamp() if tz else datetime(d.year, d.month, d.day).timestamp()


def _local(ts: float, tz) -> datetime:
    return datetime.fromtimestamp(ts, tz)


def _agent_slug(key: str) -> str:
    # "agent:<agent_key>:<slug>:<nonce>" (agent_jobs.assign_key)
    p = str(key or "").split(":")
    return p[2] if len(p) >= 3 and p[0] == "agent" else ""


# ---------- what Javis did ----------
def kanban_events(store, root: str, since: float, until: float) -> list:
    """Finished, stopped and self-retried Kanban jobs of one brain between two times."""
    if store is None:
        return []
    try:
        with store._lock:
            rows = store._db.execute(
                """SELECT t.id, t.title, t.idempotency_key, t.status, t.block_kind, e.event_type, e.metadata_json,
                          e.created_at
                   FROM task_events e JOIN tasks t ON t.id = e.task_id
                   WHERE t.brain_root = ? AND COALESCE(t.lane, '') <> 'team'
                     AND e.event_type IN ('completed', 'blocked', 'retry_scheduled')
                     AND e.created_at >= ? AND e.created_at < ?""",
                (root, since, until)).fetchall()
    except Exception as e:  # noqa: BLE001
        print(f"[task-stats] kanban events unreadable: {type(e).__name__}: {e}")
        return []
    out = []
    for r in rows:
        try:
            meta = json.loads(r["metadata_json"] or "{}")
        except Exception:
            meta = {}
        ev, ts = r["event_type"], float(r["created_at"])
        if ev == "completed":
            status = "ok"
        elif ev == "retry_scheduled":
            status = "retry"
        else:
            # A question to the owner leaves a fresh entry in metadata.qa; a permission stop keeps its kind.
            qa = [x for x in (meta.get("qa") or []) if isinstance(x, dict)]
            asked = bool(qa) and abs(float(qa[-1].get("asked_at") or 0) - ts) < 5
            status = "ask" if asked or (r["status"] == "blocked" and r["block_kind"] in OWNER_KINDS) else "fail"
        ag = meta.get("agent") if isinstance(meta.get("agent"), dict) else {}
        out.append({"ts": ts, "kind": "kanban", "status": status, "seconds": float(meta.get("run_seconds") or 0),
                    "agent": ag.get("slug") or _agent_slug(r["idempotency_key"]), "agent_name": ag.get("name") or "",
                    "title": r["title"] or "", "ref": r["id"]})
    return out


def loop_events(brain_root: str, since: float, until: float, tz) -> list:
    out = []
    d0, d1 = _local(since, tz).date(), _local(until, tz).date()
    folder = Path(brain_root) / "Javis" / "loop-log"
    if not folder.is_dir():
        return out
    d = d0
    while d <= d1:
        p = folder / f"{d.isoformat()}.md"
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                text = ""
            heads = list(_LOOP_HEAD.finditer(text))
            for i, m in enumerate(heads):
                body = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
                body = body.split("\n", 1)[1] if "\n" in body else ""
                dt = datetime(*map(int, m.group(1).split("-")), int(m.group(2)), int(m.group(3)), tzinfo=tz)
                ts = dt.timestamp()
                if since <= ts < until:
                    failed = body.strip().startswith("Lỗi:") or "auto-pause" in body
                    out.append({"ts": ts, "kind": "loop", "status": "fail" if failed else "ok", "seconds": 0,
                                "agent": "", "agent_name": "", "title": m.group(4).strip(), "ref": m.group(4).strip()})
        d += timedelta(days=1)
    return out


def logged_events(brain_root: str, since: float, until: float) -> list:
    out = []
    for r in work_log.read(brain_root, since, until):
        kind = r.get("kind")
        if kind == "reminder" and r.get("mode") == "notify":
            kind = "notify"
        if kind not in KINDS or r.get("status") == "stopped":
            continue
        out.append({"ts": float(r["ts"]), "kind": kind, "status": r.get("status") or "ok",
                    "seconds": float(r.get("seconds") or 0), "agent": "", "agent_name": "",
                    "title": r.get("title") or "", "ref": r.get("ref") or ""})
    return out


def reminder_last_runs(brain_root: str, since: float, until: float, logged: set) -> list:
    """Reminders that fired before work_log existed: their last run, unless the log already has it."""
    out = []
    try:
        data = json.loads((Path(brain_root) / "Javis" / "reminders.json").read_text(encoding="utf-8"))
    except Exception:
        return out
    for r in data.get("reminders") or []:
        ts = float(r.get("fired_at") or 0)
        if not (since <= ts < until) or (r.get("id"), int(ts)) in logged:
            continue
        kind = "notify" if r.get("mode") == "notify" else "reminder"
        out.append({"ts": ts, "kind": kind, "status": "fail" if r.get("error") else "ok", "seconds": 0, "agent": "",
                    "agent_name": "", "title": r.get("label") or r.get("text") or "", "ref": r.get("id") or ""})
    return out


# ---------- what the owner did ----------
def mine_events(store: dict, since: float, until: float, tz, now: float) -> list:
    """{ts, kind: task|habit|appt, by, on_time} for each thing the owner finished between two times."""
    out = []
    end_of = lambda iso: _ts(_day(iso) + timedelta(days=1), tz)  # noqa: E731
    d0, d1 = _local(since, tz).date(), _local(max(since, until - 1), tz).date()
    for t in store.get("tasks", []):
        if t.get("kind") == "appt":
            # An appointment counts once it is over (no tick): each occurrence in the window that has ended.
            if not t.get("time"):
                continue
            days = []
            if t.get("repeat"):
                anchor = t.get("date") or d0.isoformat()
                d = d0
                while d <= d1 and len(days) < 400:
                    if my_tasks_mod.occurs_on(t["repeat"], anchor, d.isoformat()):
                        days.append(d.isoformat())
                    d += timedelta(days=1)
            elif t.get("date"):
                days = [t["date"]]
            for iso in days:
                hh, mm = (t.get("end") or t["time"]).split(":")[:2]
                ts = _ts(_day(iso), tz) + int(hh) * 3600 + int(mm) * 60
                if since <= ts < until and ts <= now:
                    out.append({"ts": ts, "kind": "appt", "by": "me", "on_time": None, "id": t.get("id")})
            continue
        if t.get("repeat"):
            kind = "habit" if (t.get("habit") and not (t.get("habit") or {}).get("off")) else "task"
            for iso, v in (t.get("done_dates") or {}).items():
                ts = float((v or {}).get("at") or 0) if isinstance(v, dict) else 0
                if not ts:
                    ts = _ts(_day(iso), tz) + 12 * 3600
                if since <= ts < until:
                    # "On time" is about one-off tasks with a day; a repeating tick is always on its own day.
                    out.append({"ts": ts, "kind": kind, "by": (v or {}).get("by", "me") if isinstance(v, dict) else "me",
                                "on_time": None, "id": t.get("id")})
            continue
        if t.get("status") == "done" and since <= float(t.get("done_at") or 0) < until:
            ts = float(t["done_at"])
            out.append({"ts": ts, "kind": "task", "by": t.get("done_by") or "me",
                        "on_time": (ts < end_of(t["date"])) if t.get("date") else None, "id": t.get("id")})
    return out


# ---------- the whole answer ----------
class TaskStats:
    def __init__(self, deps: TaskStatsDeps):
        self.deps = deps
        self.router = self._make_router()

    def _tz(self):
        return self.deps.tz() if self.deps.tz else None

    def ai_events(self, brain: str, since: float, until: float) -> list:
        root = str(Path(self.deps.brain_root(brain)).resolve())
        store = self.deps.task_store() if self.deps.task_store else None
        ev = kanban_events(store, root, since, until) + loop_events(root, since, until, self._tz())
        logged = logged_events(root, since, until)
        seen = {(e["ref"], int(e["ts"])) for e in logged if e["kind"] in ("reminder", "notify")}
        # A run logged a moment after fired_at was stored: match on the reminder id within the same minute.
        seen |= {(r, t + d) for r, t in list(seen) for d in (-2, -1, 1, 2)}
        return ev + logged + reminder_last_runs(root, since, until, seen)

    def _bot_owners(self, brain: str, events: list, names: dict) -> None:
        """0.429.0: a job a chatbot made counts for the bot's assistant (or the bot itself when that assistant is not
        in this brain), not for Javis Core. Only events with no assistant of their own are moved."""
        if not self.deps.bot_jobs:
            return
        try:
            m = self.deps.bot_jobs(brain) or {}
        except Exception:
            return
        bots, jobs = {b["id"]: b for b in m.get("bots") or []}, m.get("jobs") or {}
        pre = {"kanban": "k:", "reminder": "r:", "notify": "r:", "loop": "l:"}
        for e in events:
            if e.get("agent") or e["kind"] not in pre:
                continue
            b = bots.get(jobs.get(pre[e["kind"]] + str(e.get("ref") or "")))
            if not b:
                continue
            if b.get("agent") and b["agent"] in names:
                e["agent"], e["agent_name"] = b["agent"], names[b["agent"]]
            else:
                e["agent"], e["agent_name"] = "bot:" + b["id"], b.get("name") or ""

    def minutes(self, brain: str) -> dict:
        m = dict(MINUTES)
        try:
            saved = (self.deps.my_tasks().load(brain).get("prefs") or {}).get("minutes") or {}
            m.update({k: int(v) for k, v in saved.items() if k in MINUTES and 0 <= int(v) <= 600})
        except Exception:
            pass
        return m

    def compute(self, brain: str, d_from: str, d_to: str, now: Optional[float] = None) -> dict:
        tz = self._tz()
        now = float(now or time.time())
        f, t = _day(d_from), _day(d_to)
        if t < f:
            f, t = t, f
        if (t - f).days > MAX_DAYS:
            f = t - timedelta(days=MAX_DAYS)
        start, end = _ts(f, tz), _ts(t + timedelta(days=1), tz)
        span = end - start
        pstart = start - span
        wstart = _ts(t - timedelta(days=55), tz)          # 8 weeks of 7 days ending on `to`
        hstart = _ts(t - timedelta(days=83), tz)          # 12 weeks for the map
        lo = min(pstart, wstart, hstart)
        mins = self.minutes(brain)
        ai_all = self.ai_events(brain, lo, end)
        store = self.deps.my_tasks().load(brain)
        me_all = mine_events(store, lo, end, tz, now)

        inr = lambda e, a, b: a <= e["ts"] < b  # noqa: E731
        ai = [e for e in ai_all if inr(e, start, end)]
        ai_p = [e for e in ai_all if inr(e, pstart, start)]
        me = [e for e in me_all if inr(e, start, end)]
        me_p = [e for e in me_all if inr(e, pstart, start)]
        ok = lambda L: [e for e in L if e["status"] == "ok"]  # noqa: E731
        saved = lambda L: sum(mins.get(e["kind"], 0) for e in ok(L))  # noqa: E731

        def on_time(L):
            dated = [e for e in L if e.get("on_time") is not None]
            return round(100 * sum(1 for e in dated if e["on_time"]) / len(dated)) if dated else None

        by_day = {}
        for e in me:
            k = _local(e["ts"], tz).date().isoformat()
            by_day.setdefault(k, {"task": 0, "habit": 0, "appt": 0})[e["kind"]] += 1
        heat = {}
        for e in me_all:
            if e["ts"] >= hstart:
                k = _local(e["ts"], tz).date().isoformat()
                heat[k] = heat.get(k, 0) + 1
        gold = [0] * 24
        for e in me_all:
            if e["ts"] >= end - 28 * 86400 and e["kind"] != "appt":
                gold[_local(e["ts"], tz).hour] += 1
        hours_me, hours_ai = [0] * 24, [0] * 24
        for e in me:
            if e["kind"] != "appt":
                hours_me[_local(e["ts"], tz).hour] += 1
        for e in ok(ai):
            hours_ai[_local(e["ts"], tz).hour] += 1
        night = sum(1 for e in ok(ai) if _local(e["ts"], tz).hour >= 22 or _local(e["ts"], tz).hour < 7)

        weeks = []
        for i in range(8):
            a = _ts(t - timedelta(days=55 - 7 * i), tz)
            b = a + 7 * 86400
            wa = [e for e in ai_all if inr(e, a, b)]
            weeks.append({"from": _local(a, tz).date().isoformat(), "to": _local(b - 1, tz).date().isoformat(),
                          "me": sum(1 for e in me_all if inr(e, a, b)), "ai": len(ok(wa)), "saved": saved(wa)})

        by_kind = {k: {"n": 0, "minutes": 0} for k in KINDS}
        for e in ok(ai):
            by_kind[e["kind"]]["n"] += 1
            by_kind[e["kind"]]["minutes"] += mins.get(e["kind"], 0)
        names = {}
        try:
            names = (self.deps.agent_names(brain) or {}) if self.deps.agent_names else {}
        except Exception:
            names = {}
        self._bot_owners(brain, ai, names)
        agents = {}
        for e in ai:
            if e["status"] not in ("ok", "fail", "ask"):
                continue
            key = e.get("agent") or "core"
            a = agents.setdefault(key, {"key": key, "name": e.get("agent_name") or names.get(key, "") if key != "core" else "",
                                        "n": 0, "ok": 0, "fail": 0, "minutes": 0})
            if e["status"] == "ok":
                a["n"] += 1
                a["ok"] += 1
                a["minutes"] += mins.get(e["kind"], 0)
            elif e["status"] == "fail":
                a["fail"] += 1
        rel = {s: sum(1 for e in ai if e["status"] == s) for s in ("ok", "retry", "ask", "fail")}
        secs = [e["seconds"] for e in ok(ai) if e["seconds"] > 0]

        me_n, ai_n = len(me), len(ok(ai))
        me_pn, ai_pn = len(me_p), len(ok(ai_p))
        share = lambda a, b: round(100 * b / (a + b)) if a + b else 0  # noqa: E731
        log = store.get("log") or {}
        handoffs = [float(x) for x in (log.get("handoffs") or [])]

        today = _local(now, tz).date().isoformat()
        habits = []
        for task in store.get("tasks", []):
            hb = task.get("habit") or {}
            if not task.get("repeat") or not hb or hb.get("off"):
                continue
            anchor = task.get("date") or hb.get("start") or today
            sched = done = 0
            d = t - timedelta(days=29)
            while d <= t:
                iso = d.isoformat()
                if iso >= (hb.get("start") or anchor) and iso <= today and my_tasks_mod.occurs_on(task["repeat"], anchor, iso):
                    if iso in (task.get("done_dates") or {}):
                        done += 1
                        sched += 1
                    elif iso < today:
                        sched += 1
                d += timedelta(days=1)
            st = my_tasks_mod.habit_state(task, today)
            habits.append({"id": task["id"], "title": task.get("title") or "", "rate": round(100 * done / sched) if sched else None,
                           "done": done, "sched": sched, "cur": st["cur"], "frozen": st["frozen"]})
        projects = []
        for p in store.get("projects", []):
            ts_ = [x for x in store.get("tasks", []) if x.get("project") == p.get("id") and not x.get("repeat")
                   and x.get("kind") != "appt" and x.get("status") != "cancelled"]
            if ts_:
                projects.append({"id": p["id"], "name": p.get("name") or "", "color": p.get("color") or "",
                                 "done": sum(1 for x in ts_ if x.get("status") == "done"), "total": len(ts_)})
        open_tasks = [x for x in store.get("tasks", []) if not x.get("repeat") and x.get("kind") != "appt"
                      and x.get("status") not in ("done", "cancelled")]
        delayed = sorted(({"id": x["id"], "title": x.get("title") or "", "moves": int(x.get("moves") or 0)}
                          for x in open_tasks if int(x.get("moves") or 0) >= 2), key=lambda x: -x["moves"])[:5]
        overdue = sum(1 for x in open_tasks if x.get("date") and x["date"] < today)

        # Things Javis could take over: jobs the owner keeps moving, and repeating chores they do by hand.
        ideas = [{"kind": "moved", "id": x["id"], "title": x["title"], "n": x["moves"], "minutes": mins["kanban"]}
                 for x in delayed[:2]]
        month_ago = now - 30 * 86400
        for task in store.get("tasks", []):
            if not task.get("repeat") or task.get("habit") or task.get("kind") == "appt":
                continue
            n = sum(1 for v in (task.get("done_dates") or {}).values()
                    if isinstance(v, dict) and v.get("by", "me") == "me" and float(v.get("at") or 0) >= month_ago)
            if n >= 3:
                ideas.append({"kind": "repeat", "id": task["id"], "title": task.get("title") or "", "n": n,
                              "minutes": round(n / 30 * 7 * mins["reminder"])})
        ideas = ideas[:3]

        return {
            "ok": True,
            "range": {"from": f.isoformat(), "to": t.isoformat(), "days": (t - f).days + 1},
            "prev": {"from": _local(pstart, tz).date().isoformat(), "to": (f - timedelta(days=1)).isoformat()},
            "minutes": mins,
            "me": {"done": me_n, "prev_done": me_pn, "by_day": by_day, "on_time": on_time(me), "prev_on_time": on_time(me_p),
                   "overdue": overdue, "habit_done": sum(1 for e in me if e["kind"] == "habit"),
                   "appts": sum(1 for e in me if e["kind"] == "appt"),
                   "javis_ticks": sum(1 for e in me if e.get("by") == "javis"),
                   "heat": [{"d": (t - timedelta(days=83 - i)).isoformat(), "n": heat.get((t - timedelta(days=83 - i)).isoformat(), 0)}
                            for i in range(84)],
                   "gold": gold, "hours": hours_me, "habits": habits, "projects": projects, "delayed": delayed},
            "ai": {"done": ai_n, "prev_done": ai_pn, "share": share(me_n, ai_n), "prev_share": share(me_pn, ai_pn),
                   "saved": saved(ai), "prev_saved": saved(ai_p), "by_kind": by_kind,
                   "agents": sorted(agents.values(), key=lambda a: -a["n"]), "hours": hours_ai, "night": night,
                   "rel": rel, "avg_seconds": round(sum(secs) / len(secs)) if secs else 0,
                   "handoffs": sum(1 for x in handoffs if start <= x < end),
                   "prev_handoffs": sum(1 for x in handoffs if pstart <= x < start)},
            "weeks": weeks,
            "ideas": ideas,
        }

    def saved_total(self, brain: str) -> int:
        """All the time given back since the first record (minutes)."""
        mins = self.minutes(brain)
        return sum(mins.get(e["kind"], 0) for e in self.ai_events(brain, 0, time.time() + 60) if e["status"] == "ok")

    def _make_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/tasks/stats")
        async def tasks_stats(brain: str = Query("brain"), from_: str = Query("", alias="from"), to: str = Query("")):
            tz = self._tz()
            today = datetime.now(tz).date()
            d_to = to if _DATE.match(to or "") else today.isoformat()
            d_from = from_ if _DATE.match(from_ or "") else (_day(d_to) - timedelta(days=6)).isoformat()
            try:
                out = self.compute(brain, d_from, d_to)
                out["ai"]["saved_total"] = self.saved_total(brain)
                return out
            except Exception as e:  # noqa: BLE001
                print(f"[task-stats] failed: {type(e).__name__}: {e}")
                return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

        @router.post("/tasks/stats/minutes")
        async def tasks_stats_minutes(payload: dict = Body(None)):
            p = payload or {}
            brain = str(p.get("brain") or "brain")
            got = p.get("minutes") or {}
            clean = {}
            for k, v in got.items():
                try:
                    if k in MINUTES and 0 <= int(v) <= 600:
                        clean[k] = int(v)
                except (TypeError, ValueError):
                    continue
            mt = self.deps.my_tasks()
            async with mt._io:
                data = mt.load(brain)
                prefs = data.setdefault("prefs", {})
                prefs["minutes"] = dict(prefs.get("minutes") or {}, **clean)
                mt.save(brain, data)
            return {"ok": True, "minutes": self.minutes(brain)}

        return router


def register(app, deps: TaskStatsDeps) -> TaskStats:
    feat = TaskStats(deps)
    app.include_router(feat.router)
    return feat
