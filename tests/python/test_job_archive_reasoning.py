"""0.193.0: finished jobs stay until the owner presses Done, Done moves them to an archive, only the archive deletes;
each assistant has its own reasoning level (default medium); private chat from a team.

    python tests/python/test_job_archive_reasoning.py

Owner, 16/10/2026: "việc đã hoàn thành thì cũng phải hiện ... khi ấn done thì mới mất đi khỏi stack việc ... xuống 1 thư
mục archive thôi chứ ko xóa hẳn ... rồi mới hiện nút xóa hoặc là xóa tất cả", "agent hiện tại không lựa chọn được mức suy
luận, cần bổ sung ngay và mặc định là trung bình". Runs the real host, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-job-archive-")
BR = Path(tempfile.mkdtemp(prefix="javis-job-archive-brain-")).resolve()
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")

import main  # noqa: E402
import job_marks  # noqa: E402
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

# ---- the marks store ----
jobs = [{"id": "a", "bucket": "done"}, {"id": "b", "bucket": "done"}, {"id": "c", "bucket": "running"}, {"id": "d", "bucket": "done"}]
kept, arch = job_marks.split(jobs, {"a": {"state": "archived", "at": 2}, "b": {"state": "deleted", "at": 1},
                                    "c": {"state": "archived", "at": 3}})
check("split: archived finished jobs leave the list, deleted ones vanish, a job running again ignores an old mark",
      [j["id"] for j in kept] == ["c", "d"] and [j["id"] for j in arch] == ["a"], (kept, arch))

# ---- a team with one finished job ----
r = client.post("/teams", params={"brain": B}, headers=H, json={"name": "Web", "members": ["lan", "minh"], "leader_slug": "lan"})
team = r.json()["team"]
tid = team["team_id"]
keys = {m["slug"]: m["agent_key"] for m in team["members"]}
r = client.post(f"/teams/{tid}/messages", params={"brain": B}, headers=H,
                json={"text": "Làm trang bán hàng", "mentions": [keys["minh"]], "as_job": True, "client_msg_id": "j1"})
task_id = r.json()["task_id"]
store = main.tasks_feature.store
claimed = store.claim_team_next(tid, "w1")
check("the job is taken by the team", claimed and claimed["id"] == task_id, claimed)
store.team_finish(task_id, "Đã làm xong trang, link: https://example.test")
q = client.get(f"/teams/{tid}/queue", params={"brain": B}).json()
fin = [j for j in q.get("finished") or [] if j["task_id"] == task_id]
check("a finished team job shows under Finished with its report (result) until the owner presses Done",
      fin and "example.test" in fin[0]["result"] and fin[0]["id"] == f"team:{task_id}" and q.get("archived") == [], q)

# Done -> archive
r = client.post("/jobs/marks", headers=H, json={"brain": B, "ids": [f"team:{task_id}"], "state": "archived"})
q = client.get(f"/teams/{tid}/queue", params={"brain": B}).json()
check("Done moves it to the archive, nothing is deleted", r.status_code == 200 and not q["finished"]
      and [j["task_id"] for j in q["archived"]] == [task_id] and store.get_task(task_id) is not None, q)
code_minh = client.get("/agents/minh/jobs", params={"brain": B}).json()
check("the assistant's Jobs tab follows the same mark (archive list, not the main list)",
      not any(j["id"] == f"team:{task_id}" for j in code_minh["jobs"])
      and [j["id"] for j in code_minh.get("archived") or []] == [f"team:{task_id}"], code_minh)
# back to the list
client.post("/jobs/marks", headers=H, json={"brain": B, "ids": [f"team:{task_id}"], "state": ""})
check("Restore puts it back under Finished", [j["task_id"] for j in client.get(f"/teams/{tid}/queue", params={"brain": B}).json()["finished"]] == [task_id])
# delete
client.post("/jobs/marks", headers=H, json={"brain": B, "ids": [f"team:{task_id}"], "state": "archived"})
client.post("/jobs/marks", headers=H, json={"brain": B, "ids": [f"team:{task_id}"], "state": "deleted"})
q = client.get(f"/teams/{tid}/queue", params={"brain": B}).json()
check("deleting from the archive hides it everywhere; the job record itself stays", not q["finished"] and not q["archived"]
      and store.get_task(task_id) is not None, q)
check("a bad request is refused", client.post("/jobs/marks", headers=H, json={"brain": B, "ids": [], "state": "deleted"}).status_code == 400
      and client.post("/jobs/marks", headers=H, json={"brain": B, "ids": ["x"], "state": "gone"}).status_code == 400)

# ---- reasoning per assistant ----
a = client.get("/agents/get", params={"slug": "lan", "brain": B}).json()
check("an assistant that never chose a level thinks at medium", a.get("reasoning") == "medium", a)
r = client.post("/agents/lan/reasoning", data={"level": "high", "brain": B})
meta = main._read_md(BR / "agents" / "lan.md")[0]
check("setting the level writes only that key", r.status_code == 200 and meta.get("reasoning") == "high"
      and meta.get("name") == "Lan", meta)
check("a bad level or Javis Core is refused", client.post("/agents/lan/reasoning", data={"level": "max!", "brain": B}).status_code == 400
      and client.post("/agents/javis-core/reasoning", data={"level": "low", "brain": B}).status_code == 400)
r = client.post("/agents", data={"name": "Lan", "slug": "lan", "role": "Thành viên", "prompt": "Bạn là Lan.", "brain": B,
                                  "reasoning": "low"})
check("the settings form saves the level", r.status_code == 200 and main._read_md(BR / "agents" / "lan.md")[0].get("reasoning") == "low")
r = client.post("/agents", data={"name": "Lan", "slug": "lan", "role": "Thành viên", "prompt": "Bạn là Lan.", "brain": B})
check("an old form that does not send it keeps the level", main._read_md(BR / "agents" / "lan.md")[0].get("reasoning") == "low")
s = main.get_store().create_session(brain=main._brain_key(B), engine="cli", channel="agent:lan")
m = client.get(f"/sessions/{s}/meta").json()
check("the model bar of the assistant's chat reads its level", m.get("agent_slug") == "lan" and m.get("agent_reasoning") == "low", m)
info = main._team_agent_info(main._brain_key(B), keys["lan"])
check("team turns know the member's level", info and info.get("reasoning") == "low", info)


class _Api:
    reasoning = "off"


e = _Api()
check("an API engine in a team turn takes the member's level", main._team_reasoning(e, "high", "x") == "x" and e.reasoning == "high")


class _Claude:
    effort = None


c = _Claude()
out = main._team_reasoning(c, "medium", "câu hỏi")
check("a Claude engine in a team turn gets the effort (or the keyword on an old CLI)",
      (c.effort == "medium" and out == "câu hỏi") or (c.effort is None and out != "câu hỏi"), (c.effort, out))
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("an assistant's chat turn uses its own level", 'reasoning = _agent_reasoning(_read_md(_agents_dir(brain) / f"{_persona[1]}.md")[0])' in src)

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_job_archive_reasoning: all pass")
