"""Team Jobs tab redesign (owner, 16/11/2026): what the queue endpoint sends for the new job cards.

    python tests/python/test_team_jobs_tab.py

Owner: "anh cần biết các agent đang có những nhiệm vụ gì", "có cả phân trang những việc đã hoàn thành nếu nhiều quá",
"kể cả lưu trữ về sau rất nhiều việc lưu trữ thì cũng có phân trang". A job that runs or waits for the owner carries
its steps (who, kind, status, a short brief); a finished job's steps carry the brief too; the archive is a light list
that is no longer cut at 30 jobs, and one job's report is read when it is opened. Runs the real host, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-jobs-tab-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-jobs-tab-brain-")).resolve()
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")

import main  # noqa: E402
import team_api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


api = main._TEAM_API
api.deps.spawn = lambda coro: coro.close() if hasattr(coro, "close") else None
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
H = {"origin": "http://127.0.0.1:8080"}
B = str(BR)
store = main.tasks_feature.store
teams = api.teams()

team = client.post("/teams", params={"brain": B}, headers=H,
                   json={"name": "Web", "members": ["lan", "minh"], "leader_slug": "lan"}).json()["team"]
tid = team["team_id"]
keys = {m["slug"]: m["agent_key"] for m in team["members"]}


def new_job(text, n):
    r = client.post(f"/teams/{tid}/messages", params={"brain": B}, headers=H,
                    json={"text": text, "mentions": [keys["minh"]], "as_job": True, "client_msg_id": f"job-{n}"})
    return r.json()["task_id"]


def queue():
    return client.get(f"/teams/{tid}/queue", params={"brain": B}).json()


# ---- a running job carries its steps ----
task_id = new_job("Làm trang bán hàng", 0)
claimed = store.claim_team_next(tid, "w1")
check("the job is running", claimed and claimed["id"] == task_id, claimed)
long_brief = "Viết   phần mở đầu\ncho trang bán hàng. " + "Rất dài. " * 60
teams.add_step(task_id, tid, "plan", keys["lan"], 1, "Chia việc cho Minh", [])
teams.add_step(task_id, tid, "work", keys["minh"], 1, long_brief, [])
q = queue()
run = [t for t in q["running"] if t["id"] == task_id]
steps = run[0].get("steps") if run else None
check("a running job lists its steps in order: who, kind, status, brief",
      steps is not None and [(s["agent_key"], s["kind"]) for s in steps] == [(keys["lan"], "plan"), (keys["minh"], "work")]
      and all(set(s) == {"agent_key", "kind", "status", "brief"} for s in steps) and steps[0]["brief"] == "Chia việc cho Minh", steps)
check("a long brief is cut to a couple of lines and its whitespace is folded",
      steps and len(steps[1]["brief"]) == team_api.STEP_BRIEF_MAX and steps[1]["brief"].startswith("Viết phần mở đầu cho trang"),
      steps and steps[1]["brief"][:80])

# ---- a finished job: the report with each step's brief ----
store.team_finish(task_id, "Đã làm xong trang, link: https://example.test")
q = queue()
fin = [j for j in q["finished"] if j["task_id"] == task_id]
check("a finished job keeps its result and its steps now say what each member was asked to do",
      fin and "example.test" in fin[0]["result"] and [s["brief"] for s in fin[0]["steps"]][0] == "Chia việc cho Minh"
      and fin[0].get("created_at") and fin[0].get("updated_at"), fin)

# ---- the archive: more than the old 30, light rows, the report read on demand ----
ids = [task_id]
for n in range(1, 36):
    t = new_job(f"Việc số {n}", n)
    got = store.claim_team_next(tid, "w1")
    if n == 1:
        teams.add_step(t, tid, "work", keys["minh"], 1, "Làm việc số 1", [])
        teams.add_step(t, tid, "synthesize", keys["lan"], 1, "Gom kết quả", [])
        teams.add_step(t, tid, "work", keys["minh"], 1, "Làm thêm", [])
        first = t
    store.team_finish(t, f"Kết quả {n}")
    ids.append(t)
q = queue()
check("the Finished list still shows the newest jobs only", len(q["finished"]) == team_api.FINISHED_SHOWN, len(q["finished"]))
r = client.post("/jobs/marks", headers=H, json={"brain": B, "ids": [f"team:{i}" for i in ids], "state": "archived"})
q = queue()
arch = q["archived"]
check("every archived job is listed, past the old ceiling of 30", r.status_code == 200 and len(arch) == 36 and not q["finished"],
      (r.status_code, len(arch), len(q["finished"])))
check("an archived row is light: no result, no steps, but who worked on it",
      all("result" not in j and "steps" not in j and isinstance(j.get("agents"), list) for j in arch)
      and [j["agents"] for j in arch if j["task_id"] == first] == [[keys["minh"], keys["lan"]]],
      [j for j in arch if j["task_id"] == first])
d = client.get(f"/teams/{tid}/tasks/{first}", params={"brain": B}).json()
check("opening an archived job reads its report: the result and every step with its brief",
      d.get("ok") and d["task"]["result"] == "Kết quả 1" and [s["brief"] for s in d["steps"]] == ["Làm việc số 1", "Gom kết quả", "Làm thêm"], d)
check("step_agents of no jobs is empty", teams.step_agents([]) == {})

if fails:
    print("\nFAILED " + str(len(fails)))
    raise SystemExit(1)
print("\nALL OK")
