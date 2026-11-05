"""Bundled plugin javis-mine, editing from chat (2026-11-05): everything the owner can change on the Tasks page can be
asked of Javis.

Expected:
  - op=update turns a repeating task into an appointment (needs a time; the end follows from duration or one hour),
    and back; changes date, time, repeat (on, off, weekdays), place, reminder, notes, tags, habit on/off, star, status;
  - a star only on a one-off task; a habit not on an appointment;
  - op=skip skips one time of a repeat (the next one by default) without touching the schedule;
  - op=delete removes one item; op=uncheck unticks;
  - op=add makes an appointment; op=list scope=upcoming / all shows appointments and repeats;
  - several matches ask back and change nothing.

Run:
    python tests/python/test_javis_mine_edit.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import tempfile
from datetime import date, timedelta
from pathlib import Path

import my_tasks  # noqa: E402
import plugins_host  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


VAULT = Path(tempfile.mkdtemp(prefix="javis-mine-edit-"))


def atomic_write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


feat = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(b), atomic_write_text=atomic_write))
my_tasks._FEATURE = feat
spec = importlib.util.spec_from_file_location("javis_mine_plugin_edit", ROOT / "system/plugins/javis-mine/plugin.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ctx = plugins_host.PluginContext("javis-mine", "bundled", ROOT / "system/plugins/javis-mine", str(VAULT))
m.register(ctx)
h = ctx._tools[0]["handler"]


def run(**a):
    return asyncio.run(h(a, ctx))


def get(title):
    return next(t for t in feat.load(str(VAULT))["tasks"] if t["title"] == title)


today = date.today()
iso = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731

# ---- a weekly repeat becomes an appointment
run(op="add", title="Họp team nội dung", repeat="week", days="T2")
out = run(op="update", name="họp team", kind="appt")
check("an appointment without a time asks for it", out.startswith("ERROR") and "giờ" in out, out)
check("and nothing changed", get("Họp team nội dung").get("kind", "task") == "task")
out = run(op="update", name="họp team", kind="appt", time="9:30", location="Văn phòng")
t = get("Họp team nội dung")
check("repeat -> appointment, keeps the repeat", out.startswith("OK") and t["kind"] == "appt" and t["repeat"]["unit"] == "week", out)
check("time normalised, end one hour later, place and a reminder set",
      t["time"] == "09:30" and t["end"] == "10:30" and t["location"] == "Văn phòng" and t["remind"] == "15", t)
out = run(op="update", name="Họp team nội dung", duration=90)
check("duration moves the end", get("Họp team nội dung")["end"] == "11:00", out)
out = run(op="update", name="Họp team nội dung", time="14:00")
check("a new start keeps the length", get("Họp team nội dung")["end"] == "15:30", get("Họp team nội dung"))
out = run(op="update", name="Họp team nội dung", days="T2, T4")
check("weekdays change alone", get("Họp team nội dung")["repeat"]["days"] == [1, 3], out)
out = run(op="update", name="Họp team nội dung", kind="task")
check("and back to a task", get("Họp team nội dung")["kind"] == "task", out)

# ---- one-off task: date, star, tags, done
run(op="add", title="Gửi báo giá chị Lan", date=iso(0))
out = run(op="update", name="báo giá", date=iso(1), time="10:00", star=True, tags="Bán hàng, Khách sỉ", notes="kèm bảng giá")
t = get("Gửi báo giá chị Lan")
names = {p["id"]: p["name"] for p in feat.load(str(VAULT))["projects"]}
check("date, time, star, notes changed", t["date"] == iso(1) and t["time"] == "10:00" and t["star"] is True and t["notes"] == "kèm bảng giá", out)
check("tag names become tags (made when missing)", [names[x] for x in t["tags"]] == ["Bán hàng", "Khách sỉ"], t["tags"])
out = run(op="update", name="báo giá", date="none")
check("date can be cleared", get("Gửi báo giá chị Lan")["date"] is None, out)
out = run(op="update", name="báo giá", status="done")
check("status done ticks it, by Javis", get("Gửi báo giá chị Lan")["status"] == "done" and get("Gửi báo giá chị Lan")["done_by"] == "javis", out)
out = run(op="uncheck", name="báo giá")
check("uncheck opens it again", get("Gửi báo giá chị Lan")["status"] == "open", out)
out = run(op="update", name="báo giá", date="05/11")
check("a bad date is refused", out.startswith("ERROR"), out)

# ---- rules
run(op="add", title="Đối soát đơn hàng", repeat="day")
out = run(op="update", name="đối soát", star=True)
check("no star on a repeat", out.startswith("ERROR") and get("Đối soát đơn hàng").get("star") is not True, out)
out = run(op="update", name="đối soát", habit=True)
check("a repeat can become a habit", get("Đối soát đơn hàng")["habit"] and not get("Đối soát đơn hàng")["habit"].get("off"), out)
out = run(op="update", name="đối soát", habit=False)
check("and stop being one", get("Đối soát đơn hàng")["habit"].get("off") is True, out)
out = run(op="update", name="đối soát", repeat="none")
check("repeat none stops repeating", get("Đối soát đơn hàng")["repeat"] is None, out)
out = run(op="update", name="đối soát")
check("nothing to change is said", out.startswith("ERROR"), out)

# ---- skip and delete
run(op="add", title="Tổng kết doanh thu", repeat="day", date=iso(-3))
out = run(op="skip", name="tổng kết")
check("skip takes the next time by default", out.startswith("OK") and iso(0) in get("Tổng kết doanh thu")["skip_dates"], out)
out = run(op="skip", name="tổng kết", date=iso(2))
check("or a given date", iso(2) in get("Tổng kết doanh thu")["skip_dates"] and get("Tổng kết doanh thu")["repeat"]["unit"] == "day", out)
out = run(op="skip", name="báo giá")
check("a one-off cannot be skipped", out.startswith("ERROR"), out)
run(op="add", title="Dọn Drive")
out = run(op="delete", name="dọn drive")
check("delete removes one item", out.startswith("OK") and all(x["title"] != "Dọn Drive" for x in feat.load(str(VAULT))["tasks"]), out)

# ---- add an appointment, list
out = run(op="add", title="Gặp chị Hoa", kind="appt", date=iso(1), time="10:00", duration=45, location="Quán Mộc", remind="30")
t = get("Gặp chị Hoa")
check("add an appointment", out.startswith("OK") and t["kind"] == "appt" and t["end"] == "10:45" and t["remind"] == "30", out)
check("an appointment without a time is refused", run(op="add", title="X", kind="appt", date=iso(1)).startswith("ERROR"))
out = run(op="list", scope="upcoming", days=7)
check("upcoming lists the appointment and the repeats", "Gặp chị Hoa" in out and "Họp team nội dung" in out, out)
out = run(op="list", scope="all", name="báo giá")
check("all with a name filters", "Gửi báo giá chị Lan" in out and "Gặp chị Hoa" not in out, out)

# ---- ambiguity
run(op="add", title="Gọi khách A")
run(op="add", title="Gọi khách B")
out = run(op="update", name="gọi khách", date=iso(3))
check("several matches ask back and change nothing", "HỎI LẠI" in out and get("Gọi khách A")["date"] is None, out)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
