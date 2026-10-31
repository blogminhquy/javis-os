"""Tasks page stats (0.428.0): what Javis did next to what the owner did, over any date range.

Expected:
  - Kanban jobs count from their events (done, asked the owner, stopped, retried), with the assistant that ran them;
  - loops count from the markdown run log, a run starting "Lỗi:" counts as failed;
  - reminders and page watches count from work_log (one line per run), plus the last run of a reminder fired before
    the log existed, never twice;
  - the owner's side counts one-off tasks done, repeating ticks (habits apart), and appointments that are over;
  - Javis's share, time given back (minutes per kind, editable), the previous period of the same length, 8 weeks,
    the 84-day map, habits' 30-day rate, projects, tasks moved twice or more and ideas Javis could take over;
  - moving a one-off task to a later day counts a move; "Give to Javis" counts a hand-off.

Run:
    python tests/python/test_task_stats_0428.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import my_tasks  # noqa: E402
import task_stats  # noqa: E402
import work_log  # noqa: E402
from task_store import TaskStore  # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not info else f"  [{info}]"))
    if not cond:
        fails.append(name)


TZ = timezone(timedelta(hours=7))
now = time.time()
today = datetime.now(TZ).date()
d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
brain = Path(tempfile.mkdtemp(prefix="javis-stats-"))
root = str(brain.resolve())


def atomic_write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


mt = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(brain), atomic_write_text=atomic_write, tz=lambda: TZ))
store = TaskStore(Path(tempfile.mkdtemp(prefix="javis-stats-kb-")) / "kanban.sqlite3")

# ---- Javis: Kanban ----
a = store.enqueue(root, "Tổng hợp đơn hôm qua", "x", status="ready")
store.claim(a, "w1")
store.complete(a, "w1", "xong", metadata={"run_seconds": 120, "agent": {"slug": "kho", "name": "Trợ lý Kho"}})
b = store.enqueue(root, "Viết bài đăng", "x", status="ready")
store.claim(b, "w1")
store.ask(b, "w1", "Bài dài bao nhiêu chữ?")
c = store.enqueue(root, "Đồng bộ kho", "x", status="ready")
store.claim(c, "w1")
store.block(c, "w1", "transient", "mạng chậm", transient=True)
store.claim(c, "w1")
store.complete(c, "w1", "xong", metadata={"run_seconds": 60})
e = store.enqueue(root, "Gửi báo giá", "x", status="ready")
store.claim(e, "w1")
store.block(e, "w1", "error", "hỏng hẳn")
other = store.enqueue(str(Path(tempfile.mkdtemp()).resolve()), "Việc brain khác", "x", status="ready")
store.claim(other, "w1")
store.complete(other, "w1", "xong")

# ---- Javis: loops (markdown log, local time) ----
ld = brain / "Javis" / "loop-log"
ld.mkdir(parents=True)
hm = datetime.now(TZ) - timedelta(minutes=5)
(ld / f"{hm.date().isoformat()}.md").write_text(
    f"\n## [{hm:%Y-%m-%d %H:%M}] soi-don · loop (custom/full) - scheduled\nĐã soi 12 đơn.\n"
    f"\n## [{hm:%Y-%m-%d %H:%M}] soi-don · loop (custom/full) - scheduled\nLỗi: hết hạn mức\n", encoding="utf-8")

# ---- Javis: reminders and watches ----
work_log.append(str(brain), "reminder", "r_1", "Báo cáo POS", "ok", seconds=40, mode="task", ts=now - 60)
work_log.append(str(brain), "reminder", "r_2", "Nhắc gọi khách", "ok", mode="notify", ts=now - 50)
work_log.append(str(brain), "reminder", "r_1", "Báo cáo POS", "retry", mode="task", ts=now - 70)
work_log.append(str(brain), "watch", "w_1", "Giá đối thủ", "ok", ts=now - 30)
(brain / "Javis" / "reminders.json").write_text(json.dumps({"reminders": [
    {"id": "r_1", "mode": "task", "fired_at": now - 60, "label": "Báo cáo POS"},      # same run as the log line
    {"id": "r_old", "mode": "task", "fired_at": now - 3600, "label": "Bản tin cũ"},   # before the log: last run
]}), encoding="utf-8")

# ---- the owner ----
r = mt.create("brain", {"title": "Gọi chị Lan", "date": d(-1)})
tid = r["task"]["id"]
mt.check("brain", tid, "", "me", True)                       # done, a day late
r2 = mt.create("brain", {"title": "Dọn kho", "date": d(0)})
mt.update("brain", {"id": r2["task"]["id"], "date": d(1)})
mt.update("brain", {"id": r2["task"]["id"], "date": d(2)})  # moved twice
mt.update("brain", {"id": r2["task"]["id"], "date": d(1)})  # moved back: not a move
habit = mt.create("brain", {"title": "Đọc sách", "date": d(-3), "repeat": {"unit": "day", "n": 1}, "habit": {"start": d(-3)}})
for n in (-3, -2, -1, 0):
    mt.check("brain", habit["task"]["id"], d(n), "javis" if n == 0 else "me", True)
chore = mt.create("brain", {"title": "Chốt sổ quỹ", "date": d(-10), "repeat": {"unit": "day", "n": 1}})
for n in (-6, -5, -4):
    mt.check("brain", chore["task"]["id"], d(n), "me", True)
mt.create("brain", {"title": "Họp", "kind": "appt", "date": d(-1), "time": "09:00", "end": "10:00"})
gone = mt.create("brain", {"title": "Viết báo giá đại lý", "date": d(0)})
mt.delete("brain", gone["task"]["id"], handoff=True)
check("moving a one-off task later counts a move, moving it back does not",
      next(x for x in mt.load("brain")["tasks"] if x["id"] == r2["task"]["id"]).get("moves") == 2)

feat = task_stats.TaskStats(task_stats.TaskStatsDeps(brain_root=lambda b: str(brain), my_tasks=lambda: mt,
                                                     task_store=lambda: store, tz=lambda: TZ,
                                                     agent_names=lambda b: {"kho": "Trợ lý Kho"}))
s = feat.compute("brain", d(-6), d(0))
ai, me = s["ai"], s["me"]
rel = ai["rel"]
check("Kanban: two jobs done, one question to the owner, one failure, one self-retry",
      rel["ask"] == 1 and rel["fail"] >= 1 and rel["retry"] >= 2, rel)
check("another brain's job is not counted", ai["by_kind"]["kanban"]["n"] == 2, ai["by_kind"])
check("loops: one run done, the run starting with Lỗi counts as failed", ai["by_kind"]["loop"]["n"] == 1)
check("reminders: the logged run counts once, the old one by its last run",
      ai["by_kind"]["reminder"]["n"] == 2 and ai["by_kind"]["notify"]["n"] == 1, ai["by_kind"])
check("page watches count their alerts", ai["by_kind"]["watch"]["n"] == 1)
check("Javis done = everything that finished well", ai["done"] == 2 + 1 + 2 + 1 + 1, ai["done"])
check("time given back follows the minutes per kind",
      ai["saved"] == 2 * 20 + 5 + 2 * 10 + 2 + 3, ai["saved"])
ag = {x["key"]: x for x in ai["agents"]}
check("the assistant that ran a job is named, the rest is Javis Core",
      ag["kho"]["name"] == "Trợ lý Kho" and ag["kho"]["n"] == 1 and ag["core"]["n"] == ai["done"] - 1, ag)
check("average run time from the jobs that report it", ai["avg_seconds"] in (40, 73), ai["avg_seconds"])
check("owner: one task, four habit ticks, three chore ticks, one appointment", me["done"] == 1 + 4 + 3 + 1, me["done"])
check("a tick Javis made on the owner's word is counted apart", me["javis_ticks"] == 1)
check("on time: the task done a day late is late", me["on_time"] is not None and me["on_time"] < 100)
check("Javis's share", ai["share"] == round(100 * ai["done"] / (ai["done"] + me["done"])))
check("hand-offs are counted", ai["handoffs"] == 1)
check("the map covers 84 days ending on the last day", len(me["heat"]) == 84 and me["heat"][-1]["d"] == d(0))
check("8 weeks, the last one ending on the last day", len(s["weeks"]) == 8 and s["weeks"][-1]["to"] == d(0)
      and s["weeks"][-1]["ai"] == ai["done"], s["weeks"][-1])
h = s["me"]["habits"][0]
check("habit rate over 30 days counts scheduled days only", h["title"] == "Đọc sách" and h["rate"] == 100 and h["sched"] == 4, h)
check("tasks moved twice or more", [x["title"] for x in me["delayed"]] == ["Dọn kho"])
kinds = {(i["kind"], i["title"]) for i in s["ideas"]}
check("ideas: the task you keep moving and the chore you do by hand", ("moved", "Dọn kho") in kinds and ("repeat", "Chốt sổ quỹ") in kinds, kinds)
check("the previous period has the same length", s["prev"]["to"] == d(-7) and s["prev"]["from"] == d(-13))
check("nothing from before shows up in the previous period", s["ai"]["prev_done"] == 0 and s["me"]["prev_done"] == 0)

app = FastAPI()
app.include_router(feat.router)
cl = TestClient(app)
res = cl.post("/tasks/stats/minutes", json={"brain": "brain", "minutes": {"kanban": 45, "loop": "bad", "nope": 3}}).json()
check("minutes per kind can be changed, bad values ignored", res["minutes"]["kanban"] == 45 and res["minutes"]["loop"] == 5
      and "nope" not in res["minutes"])
got = cl.get("/tasks/stats", params={"brain": "brain", "from": d(-6), "to": d(0)}).json()
check("GET /tasks/stats uses the new minutes and adds the running total",
      got["ok"] and got["ai"]["saved"] == 2 * 45 + 5 + 2 * 10 + 2 + 3 and got["ai"]["saved_total"] >= got["ai"]["saved"], got.get("ai", {}).get("saved"))
got = cl.get("/tasks/stats", params={"brain": "brain"}).json()
check("no dates: the last 7 days", got["range"]["days"] == 7 and got["range"]["to"] == d(0))
check("the tasks store keeps its tasks after saving minutes", len(mt.load("brain")["tasks"]) == 5)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
