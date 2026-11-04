"""Clean days, priorities and skipped times in the owner's task store ("Nhịp hôm nay", 2026-11-04).

Expected:
  - `star` is stored as a bool; `skip_dates` keeps only real dates, and a date already skipped keeps its time;
  - a past day is clean when nothing due was left at its end and something got done, empty when nothing was due or
    done, unclean otherwise; the first unclean day freezes ("i"), the next one in a row loses the chain ("x");
  - a task done or a repeat skipped AFTER the day ended does not make that day clean;
  - a judged day is kept: later edits do not rewrite it;
  - habits and appointments are not tasks for the clean day nor for the finished count;
  - GET /my-tasks carries `clean` and `done_total`, POST /my-tasks/mark counts a clearing of the overdue list.

Run:
    python tests/python/test_task_pulse_store.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import my_tasks  # noqa: E402

fails = []
root = Path(tempfile.mkdtemp(prefix="javis-pulse-"))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def at(day: str, hh: int = 12) -> float:
    return datetime.combine(date.fromisoformat(day), datetime.min.time()).timestamp() + hh * 3600


feat = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(root), atomic_write_text=atomic_write))

# ---- fields
t = feat.create("brain", {"title": "Send the quote", "date": "2026-11-04", "star": 1})["task"]
check("star is stored as a bool", t["star"] is True)
check("star can be removed", feat.update("brain", {"id": t["id"], "star": False})["task"]["star"] is False)
r = feat.create("brain", {"title": "Weekly review", "date": "2026-10-06", "repeat": {"unit": "week", "days": [2]}})["task"]
u = feat.update("brain", {"id": r["id"], "skip_dates": {"2026-11-03": 1, "03/11": 1, "2026-11-10": 0}})["task"]
check("skip_dates keeps only real, set dates", list(u["skip_dates"]) == ["2026-11-03"] and u["skip_dates"]["2026-11-03"] > 1)
first = u["skip_dates"]["2026-11-03"]
u = feat.update("brain", {"id": r["id"], "skip_dates": {"2026-11-03": 1, "2026-11-10": 1}})["task"]
check("a date already skipped keeps its time", u["skip_dates"]["2026-11-03"] == first and "2026-11-10" in u["skip_dates"])

# ---- judging one day
D = "2026-10-20"
base = at("2026-10-01")
one = {"id": "a", "title": "a", "date": D, "status": "done", "done_at": at(D), "created_at": base}
check("a day with its task done is clean", my_tasks.judge_day([one], D) == "c")
check("nothing due and nothing done is empty", my_tasks.judge_day([dict(one, date="2026-10-25", status="open", done_at=0)], D) == "e")
check("a task due and still open is unclean", my_tasks.judge_day([dict(one, status="open", done_at=0)], D) == "u")
check("a task done only the next day leaves the day unclean",
      my_tasks.judge_day([dict(one, done_at=at("2026-10-21"))], D) == "u")
check("a task created after the day does not count", my_tasks.judge_day([dict(one, created_at=at("2026-10-22"), status="open", done_at=0)], D) == "e")
rep = {"id": "r", "title": "r", "date": "2026-10-06", "repeat": {"unit": "day", "n": 1}, "done_dates": {}, "created_at": base}
check("a repeat not done on its day is unclean", my_tasks.judge_day([rep], D) == "u")
check("a repeat skipped that day is handled (not done, so empty)",
      my_tasks.judge_day([dict(rep, skip_dates={D: at(D)})], D) == "e")
check("a repeat skipped only the next day is still unclean",
      my_tasks.judge_day([dict(rep, skip_dates={D: at("2026-10-21")})], D) == "u")
check("a repeat done on its day counts as done", my_tasks.judge_day([dict(rep, done_dates={D: {"at": at(D), "by": "me"}})], D) == "c")
habit = dict(rep, habit={"start": "2026-10-06", "remind": "auto"})
appt = {"id": "p", "kind": "appt", "title": "p", "date": D, "time": "10:00", "created_at": base}
check("habits and appointments are not tasks for the clean day", my_tasks.judge_day([habit, appt], D) == "e")

# ---- judging a run of days
data = {"tasks": [
    {"id": "1", "title": "x", "date": "2026-10-28", "status": "done", "done_at": at("2026-10-28"), "created_at": at("2026-10-27")},
    {"id": "2", "title": "y", "date": "2026-10-30", "status": "open", "done_at": 0, "created_at": at("2026-10-27")},
]}
check("the judge adds the days up to yesterday", my_tasks.judge_clean_days(data, "2026-11-01"))
days = data["clean"]["days"]
check("the first day after the store began is empty", days.get("2026-10-27") == "e")
check("a day with its task done is clean", days.get("2026-10-28") == "c")
check("the first unclean day freezes, the next one loses the chain", days.get("2026-10-30") == "i" and days.get("2026-10-31") == "x")
check("today is never judged", "2026-11-01" not in days)
data["tasks"][1]["status"], data["tasks"][1]["done_at"] = "done", at("2026-11-01")
check("nothing new to judge on the same day", not my_tasks.judge_clean_days(data, "2026-11-01"))
check("a judged day is kept", data["clean"]["days"]["2026-10-30"] == "i")

check("finished count: one-offs and repeat times, not habits",
      my_tasks.done_total([one, dict(rep, done_dates={D: {"at": 1}, "2026-10-21": {"at": 1}}), dict(habit, done_dates={D: {"at": 1}}), appt]) == 3)

# ---- HTTP
app = FastAPI()
app.include_router(feat.router)
cl = TestClient(app)
lst = cl.get("/my-tasks", params={"brain": "brain"}).json()
check("GET /my-tasks carries clean days and the finished count", "days" in lst["clean"] and isinstance(lst["done_total"], int))
m1 = cl.post("/my-tasks/mark", json={"brain": "brain", "kind": "over_clear"}).json()
m2 = cl.post("/my-tasks/mark", json={"brain": "brain", "kind": "over_clear"}).json()
check("POST /my-tasks/mark counts each clearing", m1["ok"] and m2["over_clears"] == m1["over_clears"] + 1)
check("an unknown mark is refused", not cl.post("/my-tasks/mark", json={"brain": "brain", "kind": "x"}).json()["ok"])
check("the count comes back on the list", cl.get("/my-tasks", params={"brain": "brain"}).json()["clean"]["over_clears"] == m2["over_clears"])

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
