"""Team jobs waiting for the owner are mirrored into "Việc của tôi" (server/team_owner_tasks.py).

Expected:
  - a job blocked as waiting_user / acceptance_review / cap_reached gets ONE open item, never a duplicate on a second sync;
  - other block kinds (failed, rejected) and archived teams get none;
  - when the job stops waiting, the item is ticked done by javis; an item the owner ticked is never reopened;
  - a new reason on the same job is a new wait, so a new item.

Run:
    python tests/python/test_team_owner_tasks.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import tempfile
from pathlib import Path

import my_tasks
import team_owner_tasks as tot

fails = []
root = Path(tempfile.mkdtemp(prefix="javis-own-"))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def aw(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


mt = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(root), atomic_write_text=aw))
teams = {"t1": {"team_id": "t1", "brain_id": "b", "name": "Content", "status": "active"},
         "t2": {"team_id": "t2", "brain_id": "b", "name": "Cũ", "status": "archived"}}


def job(i, kind, reason, team="t1"):
    return {"id": i, "team_id": team, "title": "Job " + i, "block_kind": kind, "block_reason": reason}


def run(blocked):
    return tot.sync(mt, "b", tot.wanted_for(blocked, teams.get).get("b", []), "2026-11-11")


def items():
    return [t for t in mt.load("b")["tasks"] if t.get("team_ref")]


r = run([job("j1", "waiting_user", "Chờ chủ nhóm duyệt: A"), job("j2", "failed", "lỗi"),
         job("j3", "waiting_user", "x", "t2"), job("j4", "cap_reached", "hết lượt")])
check("2 waiting jobs create 2 items", r["created"] == 2 and len(items()) == 2)
check("title names the team", any("Content" in t["title"] and "Job j1" in t["title"] for t in items()))
r = run([job("j1", "waiting_user", "Chờ chủ nhóm duyệt: A"), job("j4", "cap_reached", "hết lượt")])
check("second sync creates no duplicate", r["created"] == 0 and len(items()) == 2)
r = run([job("j1", "waiting_user", "Chờ chủ nhóm duyệt: A")])
done = {t["team_ref"].split("|")[0]: t for t in items() if t["status"] == "done"}
check("job no longer waiting: item ticked done by javis", r["closed"] == 1 and done.get("j4", {}).get("done_by") == "javis")
mt.check("b", next(t["id"] for t in items() if t["team_ref"].startswith("j1")))
r = run([job("j1", "waiting_user", "Chờ chủ nhóm duyệt: A")])
check("item the owner ticked is not reopened", r["created"] == 0 and all(t["status"] == "done" for t in items() if t["team_ref"].startswith("j1")))
r = run([job("j1", "waiting_user", "Chờ chủ nhóm duyệt: B")])
check("new reason on the same job is a new item", r["created"] == 1)
r = run([])
check("nothing waiting: everything closes", all(t["status"] == "done" for t in items()))

print("\n%d failed" % len(fails) if fails else "\nall ok")
raise SystemExit(1 if fails else 0)
