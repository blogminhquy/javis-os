"""0.207.0 and 0.208.0 routes through the real app: approvals, work mode, department mandate.

    python tests/python/test_team_routes_0207_0208.py

Fake engine for team turns (same harness as test_team_api.py); real stores in a temporary state folder.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-routes-")
os.environ.setdefault("JAVIS_NO_REAL_TEAM_ENGINE", "1")
BR = Path(tempfile.mkdtemp(prefix="javis-team-routes-brain-"))
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")
(BR / "bao-cao").mkdir()
(BR / "bao-cao" / "a.md").write_text("1", encoding="utf-8")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


spawned = []


async def fake_publish(ev):
    pass


main._CHAT_RUNTIME.publish = fake_publish
api = main._TEAM_API
api.deps.spawn = spawned.append
api.deps.notify = lambda sid, text: None
script = {}


def fake_engine_for(team, agent_key, role):
    async def run(req):
        q = script.get((agent_key, role)) or []
        return {"text": q.pop(0) if q else f"{agent_key} {role} xong", "tokens_in": 1, "tokens_out": 1}
    return "fake", "fake-model", run


api.deps.engine_for = fake_engine_for


def dispatch():
    async def go():
        await api.runner().dispatch_once(wait=True)
        while spawned:
            j = spawned.pop(0)
            if asyncio.iscoroutine(j):
                await j
        await api.runner().wait_jobs()
    asyncio.run(go())


c = TestClient(main.app, base_url="http://127.0.0.1:8080")
Q = f"?brain={BR}"
r = c.post(f"/teams{Q}", json={"name": "Phòng nội dung", "members": ["lan", "minh"], "leader_slug": "lan"})
check("team created", r.status_code == 200, r.text)
team = r.json()["team"]
TID = team["team_id"]
check("a new team is gated by default and says so in its view", team.get("work_mode") == "gated", team.get("work_mode"))

# ── approvals through the routes ──
lan = next(m["agent_key"] for m in team["members"] if m["slug"] == "lan")
script[(lan, "plan")] = ["@Chủ nhóm anh duyệt phương án chạy quảng cáo này nhé?", "Đã chạy theo phương án được duyệt."]
r = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Lên phương án quảng cáo", "as_job": True, "client_msg_id": "j1"})
check("job submitted", r.status_code == 200, r.text)
dispatch()
aps = c.get(f"/teams/{TID}/approvals{Q}").json()["approvals"]
check("GET approvals lists the pending request (no internal fingerprints)",
      len(aps) == 1 and aps[0]["status"] == "pending" and "fingerprints" not in aps[0], aps)
aid = aps[0]["approval_id"]
r = c.post(f"/teams/{TID}/approvals/{aid}/decide{Q}", json={"decision": "approve"})
check("decide without a click key is refused", r.status_code == 400, r.text)
r = c.post(f"/teams/{TID}/approvals/{aid}/decide{Q}", json={"decision": "reject", "decision_key": "k0"})
check("reject without a reason is refused", r.status_code == 400, r.text)
r = c.post(f"/teams/{TID}/approvals/{aid}/decide{Q}", json={"decision": "approve", "decision_key": "k1", "expected_rev": 9})
check("a stale revision is refused (409)", r.status_code == 409, r.text)
r = c.post(f"/teams/{TID}/approvals/{aid}/decide{Q}", json={"decision": "approve", "decision_key": "k2", "expected_rev": 1})
check("approve with key and revision", r.status_code == 200 and r.json()["status"] == "approved", r.text)
r2 = c.post(f"/teams/{TID}/approvals/{aid}/decide{Q}", json={"decision": "approve", "decision_key": "k2", "expected_rev": 1})
check("same click key replays", r2.status_code == 200 and r2.json()["replay"] is True, r2.text)
r3 = c.post(f"/teams/{TID}/approvals/{aid}/decide{Q}", json={"decision": "reject", "note": "x", "decision_key": "k3"})
check("another key after the decision: already decided (409)", r3.status_code == 409
      and r3.json().get("error") and "already_decided" in str(r3.json()), r3.text)
dispatch()
q = c.get(f"/teams/{TID}/queue{Q}").json()
check("the approved job finished", any("Lên phương án" in (t.get("title") or "") for t in q.get("finished", [])), q)
r = c.post(f"/teams/{TID}/approvals/ap_nope/decide{Q}", json={"decision": "approve", "decision_key": "k9"})
check("unknown request: 404", r.status_code == 404, r.text)

# ── work mode ──
r = c.post(f"/teams/{TID}/work_mode{Q}", json={"mode": "everything"})
check("bad work mode refused", r.status_code == 400)
r = c.post(f"/teams/{TID}/work_mode{Q}", json={"mode": "full"})
check("work mode full saved", r.status_code == 200 and c.get(f"/teams/{TID}{Q}").json()["team"]["work_mode"] == "full",
      r.text)
c.post(f"/teams/{TID}/work_mode{Q}", json={"mode": "gated"})

# ── mandate ──
check("no mandate by default", c.get(f"/teams/{TID}/mandate{Q}").json()["mandate"] is None)
r = c.put(f"/teams/{TID}/mandate{Q}", json={"outcome": "", "sources": ["folder:bao-cao"]})
check("invalid mandate refused with the reason", r.status_code == 400 and "outcome" in r.json()["error"], r.text)
body = {"outcome": "Báo cáo đúng hạn", "sources": ["folder:bao-cao", "mcp:khong-co"], "cadence_min": 5,
        "autonomy": {"propose": ["file_changed"]}}
r = c.put(f"/teams/{TID}/mandate{Q}", json=body)
check("mandate saved off, version 1", r.status_code == 200 and r.json()["mandate"]["status"] == "off"
      and r.json()["mandate"]["version"] == 1, r.text)
r = c.post(f"/teams/{TID}/mandate/status{Q}", json={"status": "active"})
check("mandate switched on", r.status_code == 200 and r.json()["mandate"]["status"] == "active", r.text)
me = api.mandate_engine()
check("the server observes mandates (host deps wired)", me is not None)
me.tick()
view = c.get(f"/teams/{TID}/mandate{Q}").json()
src = {s["source"]: s for s in view["sources"]}
check("the missing connection is shown as missing", src["mcp:khong-co"]["state"] == "missing"
      and src["folder:bao-cao"]["state"] == "ok", src)
tv = c.get(f"/teams/{TID}{Q}").json()["team"]
check("team view carries the mandate summary", tv["mandate"]["outcome"] == "Báo cáo đúng hạn"
      and tv["mandate"]["sources_state"], tv.get("mandate"))
(BR / "bao-cao" / "b.md").write_text("2", encoding="utf-8")
api.mandates().mark_observed(TID, 0)
acts = me.tick()
check("a folder change becomes a proposal", acts and acts[0]["decision"] == "propose", acts)
oid = acts[0]["opp_id"]
r = c.post(f"/teams/{TID}/mandate/opportunities/{oid}/decide{Q}", json={"decision": "accept"})
check("owner accepts the proposal: a job opens", r.status_code == 200 and r.json()["opportunity"]["status"] == "enqueued"
      and r.json()["opportunity"]["task_id"], r.text)
dispatch()
tr = c.get(f"/teams/{TID}/mandate/trace/{oid}{Q}").json()["trace"]
check("trace through the route: mandate -> observation -> opportunity -> job", tr["mandate"]["version"] == 1
      and tr["observation"] and tr["job"] and tr["job"]["status"] == "done", tr)
r = c.post(f"/teams/{TID}/mandate/status{Q}", json={"status": "revoked"})
check("mandate revoked", r.status_code == 200 and r.json()["mandate"]["status"] == "revoked", r.text)
r = c.post(f"/teams/{TID}/mandate/status{Q}", json={"status": "active"})
check("a revoked mandate cannot be switched back on", r.status_code == 409, r.text)

print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    raise SystemExit(1)
print("ALL OK")
