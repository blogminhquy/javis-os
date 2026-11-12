"""Everything in "Mine" reaches the notifications (owner, 06/11/2026).

    python tests/run.py nhac_viec_cua_toi      (no network)

The owner: "Phần nhiệm vụ của tôi đang chưa được nối lên phần thông báo ... hãy thông báo tất cả những gì có ở trong
phần của tôi". Before, only habits and the appointments with a reminder chosen were announced: a task with a time never
was, and an appointment Javis made from chat (reminder left empty, the page showing "15 minutes before") neither.
Now a timed task is announced at its time, an empty appointment reminder means 15 minutes before, and a morning list
names everything on today with the count of overdue tasks. "No reminder" ("0") still means none.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import my_tasks  # noqa: E402
import notify_policy  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


D = "2026-11-06"
task = {"id": "t1", "kind": "task", "title": "Gọi nhà cung cấp", "date": D, "time": "10:00", "status": "open"}
appt = {"id": "a1", "kind": "appt", "title": "Họp", "date": D, "time": "14:00", "remind": "", "status": "open"}

# ---- when a timed item is due ----
check("a task with a time is reminded at its time", my_tasks.timed_due(task, D, "10:00"))
check("not before its time", not my_tasks.timed_due(task, D, "09:59"))
check("a little late still goes out (server was down)", my_tasks.timed_due(task, D, "10:45"))
check("long past: no reminder", not my_tasks.timed_due(task, D, "11:00"))
check("once a day", not my_tasks.timed_due(dict(task, reminded=D), D, "10:00"))
check("a task already done: none", not my_tasks.timed_due(dict(task, status="done"), D, "10:00"))
check("another day: none", not my_tasks.timed_due(task, "2026-11-07", "10:00"))
check("a task with minutes set is reminded that much earlier", my_tasks.timed_due(dict(task, remind="30"), D, "09:30"))
check("an appointment with the reminder left empty: 15 minutes before, like the page shows",
      my_tasks.remind_minutes(appt) == 15 and my_tasks.timed_due(appt, D, "13:45") and not my_tasks.timed_due(appt, D, "13:44"))
check("'No reminder' (0) means none, for appointments and tasks",
      not my_tasks.timed_due(dict(appt, remind="0"), D, "13:50") and not my_tasks.timed_due(dict(task, remind="0"), D, "10:00"))
daily = {"unit": "day", "n": 1}
rep = dict(task, date="2026-11-01", repeat=daily, done_dates={}, skip_dates={})
check("a repeating task is reminded on each of its days", my_tasks.timed_due(rep, D, "10:00"))
check("but not on a day it is done or skipped",
      not my_tasks.timed_due(dict(rep, done_dates={D: {"at": 1}}), D, "10:00")
      and not my_tasks.timed_due(dict(rep, skip_dates={D: 1}), D, "10:00"))
habit = dict(rep, habit={"start": "2026-11-01", "remind": "time", "at": "10:00"})
check("a habit keeps its own nudge, not this one", not my_tasks.timed_due(habit, D, "10:00"))
check("text before the time says it is coming, at the time says it is time",
      "Sắp tới" in my_tasks.timed_text(dict(task, remind="30"), "09:30") or "Coming up" in my_tasks.timed_text(dict(task, remind="30"), "09:30"))
check("an appointment keeps its own text (with the place)", "Kho" in my_tasks.timed_text(dict(appt, location="Kho"), "13:45"))

# ---- the morning list ----
untimed = {"id": "t2", "kind": "task", "title": "Viết bài blog", "date": D, "time": "", "status": "open"}
over = {"id": "t3", "kind": "task", "title": "Nộp thuế", "date": "2026-11-01", "time": "", "status": "open"}
done = {"id": "t4", "kind": "task", "title": "Đã xong", "date": D, "time": "", "status": "done"}
items, n_over = my_tasks.agenda([untimed, appt, task, over, done, habit], D)
check("the morning list: today's open items, timed ones first in time order, habits and done ones left out",
      [t["id"] for t in items] == ["t1", "a1", "t2"], [t["id"] for t in items])
check("overdue one-off tasks are counted", n_over == 1, n_over)
txt = my_tasks.agenda_text(items, n_over)
check("the list names each item with its time", "10:00 Gọi nhà cung cấp" in txt and "14:00 Họp" in txt and "- Viết bài blog" in txt, txt)
check("and says how many are overdue", "1" in txt.splitlines()[-1], txt)
check("nothing on and nothing overdue: no message", my_tasks.agenda_text([], 0) == "")
many = [dict(untimed, id=f"x{i}", title=f"Việc {i}") for i in range(20)]
check("a long list is cut and counted", len(my_tasks.agenda_text(many, 0).splitlines()) == my_tasks.AGENDA_MAX + 2)
check("no long dash in the messages", all(chr(0x2014) not in s and chr(0x2013) not in s
                                            for s in (txt, my_tasks.timed_text(task, "10:00"))))

# ---- the tick: everything goes out once, through the reminder group ----
brain = Path(tempfile.mkdtemp(prefix="javis-nhacviec-"))
sent = []


def atomic_write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


async def notify(chat_id, text, brain="", dedup="", source="habit"):
    sent.append((text, dedup, source))
    return True, ""


# A zone where it is 08:00 now, so the morning list is due and a task set for 08:00 is on time.
now_utc = datetime.now(timezone.utc)
tz = timezone(timedelta(minutes=8 * 60 - (now_utc.hour * 60 + now_utc.minute)))
today = datetime.now(tz).date().isoformat()
feat = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(brain), atomic_write_text=atomic_write,
                                             scheduler_brains=lambda: [], notify=notify, tz=lambda: tz))
feat.save("brain", {"rev": 0, "projects": [], "tasks": [
    {"id": "k1", "kind": "task", "title": "Uống thuốc", "date": today, "time": "08:00", "status": "open"},
    {"id": "k2", "kind": "task", "title": "Dọn kho", "date": today, "time": "", "status": "open"},
    {"id": "k3", "kind": "appt", "title": "Gặp khách", "date": today, "time": "18:00", "remind": "", "status": "open"},
]})
asyncio.run(feat.tick())
keys = [d for _, d, _ in sent]
check("the tick sends the morning list and the 08:00 task", keys == [f"agenda:{today}", f"task:k1:{today}"], keys)
check("both go as 'mytask', which is the Reminders group",
      all(s == "mytask" for _, _, s in sent) and notify_policy.group_of(source="mytask", kind="report") == "reminder")
check("the list carries all three items", all(w in sent[0][0] for w in ("Uống thuốc", "Dọn kho", "Gặp khách")), sent[0][0])
asyncio.run(feat.tick())
check("nothing is sent twice", len(sent) == 2, [d for _, d, _ in sent])
check("the day is remembered in the store", feat.load("brain").get("agenda_sent") == today)

# A separate morning briefing may replace only the standalone 07:30 agenda.
# The per-brain opt-out must leave the timed task reminder unaffected.
feat.save("brain", {"rev": 0, "projects": [], "agenda_enabled": False,
                     "agenda_sent": "", "tasks": [
    {"id": "opt1", "kind": "task", "title": "Việc có giờ",
     "date": today, "time": "08:00", "status": "open"},
    {"id": "opt2", "kind": "task", "title": "Việc không có giờ",
     "date": today, "time": "", "status": "open"},
]})
sent.clear()
asyncio.run(feat.tick())
keys = [d for _, d, _ in sent]
check("disabled morning agenda does not ring or set agenda_sent",
      keys == [f"task:opt1:{today}"] and feat.load("brain").get("agenda_sent") != today, keys)
check("timed task reminder still rings with agenda disabled",
      sent and sent[0][2] == "mytask" and "Việc có giờ" in sent[0][0], sent)
sent.clear()
asyncio.run(feat.tick())
check("opted-out task's due reminder is not duplicated", not sent, sent)
feat.save("brain", {"rev": 0, "projects": [], "agenda_enabled": True,
                     "agenda_sent": "", "tasks": [
    {"id": "re1", "kind": "task", "title": "Bật lại",
     "date": today, "time": "", "status": "open"},
]})
sent.clear()
asyncio.run(feat.tick())
check("enabling agenda restores one morning notice", [d for _, d, _ in sent] == [f"agenda:{today}"],
      sent)
check("agenda opt-out survives regular store saves", feat.load("brain").get("agenda_enabled") is True)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
