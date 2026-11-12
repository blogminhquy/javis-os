"""A new team has no cap on the replies and steps of one job (2026-11-12).

    python tests/run.py team_new_defaults

A customer: "tốn token xíu cũng ok, mục tiêu đã ghép team là phải giải quyết được việc". A job stopped at 12 replies or 8
steps and waited for the owner to press "Cho thêm lượt". The owner decided: teams made from now on start without those
two caps. The daily cap of the team stays, and teams made before keep what they had.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-team-new-defaults-"))

from fastapi.testclient import TestClient  # noqa: E402
import main as M  # noqa: E402
import team_api  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:500] + "]") if not cond and extra != "" else ""))
    if not cond:
        fails.append(name)


brain = Path(tempfile.mkdtemp(prefix="javis-brain-team-new-defaults-")).resolve()
(brain / "agents").mkdir()
(brain / "agents" / "lan.md").write_text("---\nname: Lan\nrole: Thành viên\n---\nBạn là Lan.\n", encoding="utf-8")
M._TEAM_API.deps.spawn = lambda coro: coro.close() if hasattr(coro, "close") else None
c = TestClient(M.app, base_url="http://127.0.0.1:8080")
q = f"?brain={brain}"
teams = M._TEAM_API.teams()

r = c.post(f"/teams{q}", json={"name": "Team mới", "members": ["lan"], "leader_slug": "lan", "client_req_id": "n1"})
t = r.json()["team"]
caps = t["caps"]
check("a team made through the route has no cap on replies and steps of one job",
      r.status_code == 200 and caps["task_turns"] is None and caps["task_steps"] is None, caps)
check("the daily cap and the other limits are the defaults", caps["daily_turns"] == team_store.DEFAULT_CAPS["daily_turns"] == 100
      and caps["help_depth"] == 2 and caps["no_progress"] == 2, caps)
check("the answer of the create call already carries them", team_api.NEW_TEAM_UNCAPPED == ("task_turns", "task_steps"))
ev = [e for e in teams.events(t["team_id"]) if e["kind"] == "caps_set"]
check("it is written as the host's doing, not as a choice the owner made", len(ev) == 1 and ev[0]["by"] == "host", ev)
check("so it does not count as an owner-set limit", teams.owner_caps_after(t["team_id"], 0) == set(), teams.owner_caps_after(t["team_id"], 0))

r2 = c.post(f"/teams{q}", json={"name": "Team mới", "members": ["lan"], "leader_slug": "lan", "client_req_id": "n1"})
check("the same create request again changes nothing", r2.json().get("duplicate") is True
      and len([e for e in teams.events(t["team_id"]) if e["kind"] == "caps_set"]) == 1)

r3 = c.post(f"/teams/{t['team_id']}/caps{q}", json={"caps": {"task_turns": 20}})
check("the owner can still put a number back", r3.status_code == 200 and r3.json()["team"]["caps"]["task_turns"] == 20
      and r3.json()["team"]["caps"]["task_steps"] is None, r3.text[:300])

# A team that exists already (made before this change, or straight in the store) keeps the default numbers.
sid = M.get_store().create_session(brain=str(brain), channel="team:tm_old", title="Cũ")
old = teams.create_team(str(brain), "Team cũ", "", sid, team_id="tm_old")
check("a team made before keeps 12 replies and 8 steps per job", old["caps"]["task_turns"] == 12 and old["caps"]["task_steps"] == 8, old["caps"])

print("")
if fails:
    print(f"RED: {len(fails)}")
    sys.exit(1)
print("All green.")
