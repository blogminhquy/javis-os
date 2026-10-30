"""The owner's own tasks store (Tasks page, tab "Mine", 0.423.0).

Expected:
  - create/update clean their fields (bad dates, times, repeats and colors are dropped, not stored);
  - a one-off task is checked and unchecked as a whole; a repeating one per date in done_dates, with who ticked it;
  - delete returns the task and restore puts it back (undo); move writes the target first, copy gets a new id;
  - projects are created, renamed, recoloured, pinned and deleted (their tasks stay, without a project);
  - the HTTP routes answer through FastAPI.

Run:
    python tests/python/test_my_tasks_0423.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import json
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import my_tasks  # noqa: E402

fails = []
roots = {"brain": Path(tempfile.mkdtemp(prefix="javis-my-a-")), "other": Path(tempfile.mkdtemp(prefix="javis-my-b-"))}


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


feat = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(roots.get(b, roots["brain"])),
                                             atomic_write_text=atomic_write))

r = feat.create("brain", {"title": "  Call Lan about the wholesale order  ", "date": "2026-10-30", "time": "14:00",
                          "project": "p_x", "repeat": {"unit": "fortnight"}})
t = r["task"]
check("create answers ok with an id", r["ok"] and t["id"].startswith("m_"))
check("title is trimmed", t["title"] == "Call Lan about the wholesale order")
check("date and time are kept", t["date"] == "2026-10-30" and t["time"] == "14:00")
check("an unknown repeat unit is dropped", t["repeat"] is None)
check("a missing title is refused", not feat.create("brain", {"title": "  "})["ok"])
bad = feat.create("brain", {"title": "x", "date": "30/10/2026", "time": "25:99"})["task"]
check("bad date and time are dropped", bad["date"] is None and bad["time"] == "")

u = feat.update("brain", {"id": t["id"], "time": "15:30", "notes": "bring the price list", "subs": [{"t": "price list"}, {"t": " "}]})
check("update changes only what is sent", u["ok"] and u["task"]["time"] == "15:30" and u["task"]["date"] == "2026-10-30")
check("empty steps are dropped", [s["t"] for s in u["task"]["subs"]] == ["price list"])
check("update of an unknown id fails", not feat.update("brain", {"id": "m_nope", "title": "y"})["ok"])

c = feat.check("brain", t["id"])
check("a one-off task is checked as a whole", c["task"]["status"] == "done" and c["task"]["done_at"] > 0)
c = feat.check("brain", t["id"], done=False)
check("and unchecked", c["task"]["status"] == "open" and c["task"]["done_at"] == 0)

rep = feat.create("brain", {"title": "Read 30 minutes", "date": "2026-10-01", "time": "21:00",
                            "repeat": {"unit": "week", "n": 1, "days": [2, 4, 9, "x", 6]}})["task"]
check("weekly repeat keeps only real weekdays", rep["repeat"] == {"unit": "week", "n": 1, "days": [2, 4, 6]})
feat.check("brain", rep["id"], "2026-10-29", "javis")
feat.check("brain", rep["id"], "2026-10-27")
got = feat.load("brain")
rr = next(x for x in got["tasks"] if x["id"] == rep["id"])
check("a repeating task records each date and who ticked it",
      rr["done_dates"]["2026-10-29"]["by"] == "javis" and rr["done_dates"]["2026-10-27"]["by"] == "me")
check("a repeating task stays open", rr["status"] == "open")
feat.check("brain", rep["id"], "2026-10-27", done=False)
check("unchecking one date removes only it", list(feat.load("brain")["tasks"][-1]["done_dates"]) == ["2026-10-29"])

hb = feat.create("brain", {"title": "Exercise", "habit": {"remind": "time", "at": "07:00"}})["task"]
check("a habit without a repeat repeats every day", hb["repeat"] == {"unit": "day", "n": 1} and hb["habit"]["at"] == "07:00")

d = feat.delete("brain", t["id"])
check("delete returns the task", d["ok"] and d["task"]["id"] == t["id"])
check("the task is gone", all(x["id"] != t["id"] for x in feat.load("brain")["tasks"]))
feat.restore("brain", d["task"])
check("restore puts it back once", sum(1 for x in feat.load("brain")["tasks"] if x["id"] == t["id"]) == 1)
feat.restore("brain", d["task"])
check("restoring twice does not duplicate", sum(1 for x in feat.load("brain")["tasks"] if x["id"] == t["id"]) == 1)

m = feat.move("brain", "other", rep["id"], copy=True)
check("copy to another brain gets a new id and keeps the source", m["ok"] and m["task"]["id"] != rep["id"]
      and any(x["id"] == rep["id"] for x in feat.load("brain")["tasks"]))
m = feat.move("brain", "other", t["id"])
check("move to another brain removes it here and drops the project", m["ok"] and m["task"]["project"] == ""
      and all(x["id"] != t["id"] for x in feat.load("brain")["tasks"])
      and any(x["id"] == t["id"] for x in feat.load("other")["tasks"]))
check("move to the same brain is refused", not feat.move("brain", "brain", rep["id"])["ok"])

p = feat.project("brain", {"name": "Wholesale", "color": "#22C55E"})
pid = p["project"]["id"]
check("project created with a lower-case colour", p["ok"] and p["project"]["color"] == "#22c55e")
p = feat.project("brain", {"id": pid, "name": "Wholesale shop", "color": "red", "pinned": True})
check("project renamed and pinned, a bad colour ignored", p["project"]["name"] == "Wholesale shop"
      and p["project"]["color"] == "#22c55e" and p["project"]["pinned"] is True)
feat.update("brain", {"id": rep["id"], "project": pid})
pd = feat.project_delete("brain", pid)
check("deleting a project keeps its tasks, without the project", pd["ok"] and pd["tasks"] == [rep["id"]]
      and next(x for x in feat.load("brain")["tasks"] if x["id"] == rep["id"])["project"] == "")

store = roots["brain"] / "Javis" / "my-tasks.json"
check("the store is a JSON file in the brain", json.loads(store.read_text(encoding="utf-8"))["rev"] > 0)

app = FastAPI()
app.include_router(feat.router)
cl = TestClient(app)
r = cl.post("/my-tasks", json={"brain": "brain", "title": "From HTTP", "date": "2026-11-02"}).json()
check("POST /my-tasks creates", r["ok"] and r["task"]["date"] == "2026-11-02")
lst = cl.get("/my-tasks", params={"brain": "brain"}).json()
check("GET /my-tasks lists tasks and projects", lst["ok"] and any(x["title"] == "From HTTP" for x in lst["tasks"]) and "projects" in lst)
r2 = cl.post("/my-tasks/check", json={"brain": "brain", "id": r["task"]["id"]}).json()
check("POST /my-tasks/check", r2["ok"] and r2["task"]["status"] == "done")

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
