"""Habits on the Tasks page (0.424.0): the server mirror of the streak rules and the daily reminder.

Expected:
  - only scheduled days count: a weekday habit rests on the other days (no freeze, no break);
  - one missed session freezes, the next one done thaws, two missed sessions in a row lose the streak;
  - a monthly 31st falls on the last day of a short month (same as the page);
  - the reminder goes out once a day, only on a scheduled day that is not done, at the set time or half an hour
    after the usual time (earlier while frozen), never for a habit switched off or set to "No reminder".

Run:
    python tests/python/test_habits_0424.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import my_tasks  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


T = date(2026, 10, 30)   # a Friday


def d(n):
    return (T + timedelta(days=n)).isoformat()


def done(*days):
    return {x: {"at": datetime.fromisoformat(x + "T21:30:00").replace(tzinfo=timezone.utc).timestamp(), "by": "me"} for x in days}


# ---- schedule ----
week = {"unit": "week", "n": 1, "days": [2, 4, 6]}   # Tue, Thu, Sat
check("T3/T5/T7 falls on Thursday", my_tasks.occurs_on(week, "2026-09-01", "2026-10-29"))
check("and not on Friday", not my_tasks.occurs_on(week, "2026-09-01", "2026-10-30"))
check("every 2 weeks skips the week in between", my_tasks.occurs_on({"unit": "week", "n": 2, "days": [1]}, "2026-10-05", "2026-10-19")
      and not my_tasks.occurs_on({"unit": "week", "n": 2, "days": [1]}, "2026-10-05", "2026-10-12"))
check("monthly 31st falls on Sep 30", my_tasks.occurs_on({"unit": "month", "n": 1}, "2026-08-31", "2026-09-30"))
check("nothing before the anchor", not my_tasks.occurs_on({"unit": "day", "n": 1}, "2026-11-01", "2026-10-30"))

# ---- streaks ----
daily = {"unit": "day", "n": 1}
h = {"start": d(-10), "remind": "auto"}
all_done = {"date": d(-10), "repeat": daily, "habit": h, "done_dates": done(*[d(-i) for i in range(10, 0, -1)])}
st = my_tasks.habit_state(all_done, T.isoformat())
check("ten days done, today open: streak 10, not frozen", st["cur"] == 10 and not st["frozen"] and not st["done_today"])
one_miss = dict(all_done, done_dates=done(*[d(-i) for i in range(10, 1, -1)]))
st = my_tasks.habit_state(one_miss, T.isoformat())
check("yesterday missed: frozen, streak kept", st["frozen"] and st["cur"] == 9)
thawed = dict(one_miss, done_dates=dict(one_miss["done_dates"], **done(d(0))))
st = my_tasks.habit_state(thawed, T.isoformat())
check("done today after a frozen day: thawed and counted", not st["frozen"] and st["done_today"] and st["cur"] == 10)
two_miss = dict(all_done, done_dates=done(*[d(-i) for i in range(10, 2, -1)]))
st = my_tasks.habit_state(two_miss, T.isoformat())
check("two sessions missed in a row: streak lost", st["cur"] == 0 and not st["frozen"])
sessions = [x.isoformat() for x in (date(2026, 9, 1) + timedelta(days=i) for i in range(59)) if x < T and (x.weekday() + 1) % 7 in (2, 4, 6)]
swim = {"date": "2026-09-01", "repeat": week, "habit": {"start": "2026-09-01"}, "done_dates": done(*sessions)}
st = my_tasks.habit_state(swim, T.isoformat())
check("a weekday habit rests on Friday, streak intact", st["rest"] and not st["frozen"] and st["cur"] > 20)

# ---- reminder tick ----
brain = Path(tempfile.mkdtemp(prefix="javis-habits-"))
sent = []


def atomic_write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


async def notify(chat_id, text, brain="", dedup=""):
    sent.append((text, dedup))
    return True, ""


feat = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(brain), atomic_write_text=atomic_write,
                                             scheduler_brains=lambda: [], notify=notify, tz=lambda: timezone.utc))
now = datetime.now(timezone.utc)
today = now.date().isoformat()
early = "00:00"
data = {"rev": 0, "projects": [], "tasks": [
    {"id": "m_due", "title": "Read 30 minutes", "date": today, "repeat": daily, "habit": {"start": today, "remind": "time", "at": early}, "done_dates": {}},
    {"id": "m_done", "title": "Exercise", "date": today, "repeat": daily, "habit": {"start": today, "remind": "time", "at": early}, "done_dates": done(today)},
    {"id": "m_off", "title": "Stretch", "date": today, "repeat": daily, "habit": {"start": today, "remind": "off"}, "done_dates": {}},
    {"id": "m_paused", "title": "Walk", "date": today, "repeat": daily, "habit": {"start": today, "remind": "time", "at": early, "off": True}, "done_dates": {}},
    {"id": "m_late", "title": "Journal", "date": today, "repeat": daily, "habit": {"start": today, "remind": "time", "at": "23:59"}, "done_dates": {}},
    {"id": "m_plain", "title": "Pay bills", "date": today, "repeat": daily, "habit": None, "done_dates": {}},
]}
feat.save("brain", data)
n = asyncio.run(feat.tick())
check("only the due, undone, switched-on habit is reminded" + ("" if now.strftime("%H:%M") < "23:59" else " (skipped at 23:59)"),
      n == 1 and sent[0][1] == "habit:m_due:" + today and "Read 30 minutes" in sent[0][0])
n = asyncio.run(feat.tick())
check("never twice in a day", n == 0 and len(sent) == 1)
check("the day it was reminded is stored", next(t for t in feat.load("brain")["tasks"] if t["id"] == "m_due")["habit"].get("nudged") == today)
check("Javis reminds: half an hour after the usual time, earlier while frozen",
      my_tasks.nudge_time({"habit": {"remind": "auto"}, "time": "21:00"}, {"frozen": False}) == "21:30"
      and my_tasks.nudge_time({"habit": {"remind": "auto"}, "time": "21:00"}, {"frozen": True}) == "20:30")

# ---- appointment reminder (0.425.0) ----
sent.clear()
soon = (now + timedelta(minutes=10)).strftime("%H:%M")
if "00:00" < soon < "23:50" and soon > now.strftime("%H:%M"):
    data = feat.load("brain")
    data["tasks"].append({"id": "a_soon", "kind": "appt", "title": "Supplier meeting", "date": today, "time": soon,
                          "end": "23:59", "remind": "15", "location": "Warehouse", "done_dates": {}})
    data["tasks"].append({"id": "a_late", "kind": "appt", "title": "Evening call", "date": today, "time": "23:58",
                          "end": "23:59", "remind": "5", "done_dates": {}})
    feat.save("brain", data)
    asyncio.run(feat.tick())
    check("an appointment within its reminder window is announced once, with its place",
          [d for _, d in sent] == ["appt:a_soon:" + today] and "Warehouse" in sent[0][0])
    asyncio.run(feat.tick())
    check("not twice", len(sent) == 1)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
