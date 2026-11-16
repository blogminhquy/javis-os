"""An assistant's own Auto runs show in its Jobs tab (Partners page).

    python tests/python/test_agent_jobs_auto_runs.py

Owner, 16/11/2026: the Auto block of an assistant said "Hôm nay đã tự làm 1 lần" while its Jobs tab said "Chưa có công
việc nào". The number counts rows of the shared call ledger (a run the assistant started by itself: looking around,
reviewing a reaction, reviewing itself, weighing a message to the owner); the tab only read goals, team jobs, chat
jobs and workflow runs, so a self-run had nowhere to appear. Each counted run is now one card under the Auto source,
read from the same ledger rows the number counts, with what the run ended in.

Real temporary store, real ledger, the same event rows the pulse host writes. No model.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-autoruns-")
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
TEMP = Path(tempfile.mkdtemp(prefix="javis-autoruns-w-"))

import agent_budget as AB  # noqa: E402
import agent_jobs  # noqa: E402
import agent_ledger as ALG  # noqa: E402
import agent_pulse as AP  # noqa: E402
import resonance_store as RS  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


gs = RS.GoalStore(TEMP / "resonance.sqlite3")
L = ALG.CallLedger(gs)
K, SLUG, B = "ag_runs", "minh", "/brains/shop"
DM = f"dm:{K}"
lt = time.localtime()
NOON = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 12, 0, 0, 0, 0, -1))
_r = [0]


def spend(purpose, at=NOON, ctx=DM, key=K, status="ok", ref=None):
    """One ledger row, the way a run reserves, marks and settles it. `status` "running": left open."""
    _r[0] += 1
    cid = L.reserve(purpose=purpose, reason_ref=ref or f"t:{_r[0]}", agent_key=key, context_ref=ctx, obligation=False,
                    now=at)
    assert cid is not None, "the shared daily ceiling refused the row: spread test rows over more days"
    if status == "refunded":
        L.refund(cid, now=at)
    elif status == "reserved":
        pass
    else:
        L.mark_engine(cid, now=at)
        if status != "running":
            L.settle(cid, status, now=at + 30)
    return cid


def scan(result, at=NOON, ctx=DM, extra=()):
    """A finished look-around: the ledger row plus the events `agent_pulse_host._run_scan` and `_act_core` write."""
    cid = spend("scan", at=at, ctx=ctx)
    for kind, reason, payload in extra:
        AP.record_event(gs, K, ctx, kind, reason=reason, payload=payload, at=at)
    AP.record_event(gs, K, ctx, "scan", source="opportunities", reason=result.get("action", "none"),
                    payload={"call_id": cid, "result": result, "opportunities": []}, at=at)
    return cid


def collect(**kw):
    return agent_jobs.collect(K, SLUG, B, goals=gs, principal=RS.Principal("owner", "owner", B), **kw)


def by_id(out):
    return {j["id"]: j for j in out["jobs"]}


# The owner's case: one self-run today, the number says 1, the tab must not be empty.
c_none = scan({"action": "none", "reason": "nothing new"}, at=NOON)
used = AB.usage(gs, K, NOON)["used"]
out = collect()
check("the number in the Auto block counts the run", used == 1, used)
check("the Jobs tab lists the same run under Auto", out["source_counts"].get("auto") == 1 and len(out["jobs"]) == 1,
      out["source_counts"])
j = (out["jobs"] or [{}])[0]
check("a finished run: Done, kind auto_run, id from the ledger row",
      j.get("id") == f"run:{c_none}" and j.get("bucket") == "done" and j.get("kind") == "auto_run"
      and j.get("source") == "auto", j)
check("looked around, found nothing: says so by code, no fake result text",
      j.get("title_code") == "scan" and (j.get("outcome") or {}).get("code") == "none" and j.get("result") == "", j)
check("time of the card is when the run ended", j.get("updated_at") == NOON + 30, j.get("updated_at"))
check("no cancel, resume or priority buttons that cannot work",
      j.get("cancel") is None and j.get("priority") is None and not j.get("resume"), j)

# What each run ended in.
c_did = scan({"action": "say", "verdict": "acted", "message_id": 11, "decision_id": None}, at=NOON + 100,
             extra=[("said", "followup:3", {"message_id": 11, "decision_id": None, "kind": "report",
                                            "did": ["Gửi báo giá cho anh Nam", "Cập nhật bảng tồn kho"]})])
c_said = scan({"action": "say", "verdict": "speak", "message_id": 12, "decision_id": 5}, at=NOON + 200,
              extra=[("said", "mail:9", {"message_id": 12, "decision_id": 5})])
c_held = scan({"action": "say", "verdict": "silent", "reason": "below_threshold", "decision_id": 6}, at=NOON + 300)
c_prop = scan({"action": "propose", "ref": "msg:13", "proposal_id": 1, "source_ref": "mail:10", "downgraded": ""},
              at=NOON + 400, extra=[("propose", "mail:10", {"ref": "msg:13", "proposal_id": 1,
                                                            "title": "Trả lời khách hỏi giá sỉ", "downgraded": ""})])
c_enq = scan({"action": "enqueue", "task_id": "t9", "source_ref": "mail:11"}, at=NOON + 500,
             extra=[("enqueue", "mail:11", {"task_id": "t9", "title": "Soạn báo cáo tuần"})])
c_side = scan({"action": "none", "reason": "", "acted": {"action": "say", "verdict": "acted", "message_id": 14}},
              at=NOON + 600, extra=[("said", "pulse:x", {"message_id": 14, "decision_id": None,
                                                         "did": ["Dọn thư rác trong hộp thư"]})])
jobs = by_id(collect())
j = jobs.get(f"run:{c_did}") or {}
check("did real work and reported it: the work itself is the result",
      (j.get("outcome") or {}).get("code") == "did" and "Gửi báo giá cho anh Nam" in j.get("result", "")
      and "Cập nhật bảng tồn kho" in j.get("result", ""), j)
j = jobs.get(f"run:{c_said}") or {}
check("only sent the owner a message", (j.get("outcome") or {}).get("code") == "said" and j.get("result") == "", j)
j = jobs.get(f"run:{c_held}") or {}
check("drafted a message, decided it was not worth sending", (j.get("outcome") or {}).get("code") == "held", j)
j = jobs.get(f"run:{c_prop}") or {}
check("proposed a job: the proposal's title is the result",
      (j.get("outcome") or {}).get("code") == "proposed" and j.get("result") == "Trả lời khách hỏi giá sỉ", j)
j = jobs.get(f"run:{c_enq}") or {}
check("queued a job: its title is the result",
      (j.get("outcome") or {}).get("code") == "enqueued" and j.get("result") == "Soạn báo cáo tuần", j)
j = jobs.get(f"run:{c_side}") or {}
check("did work without meaning to message: still shown as work done",
      (j.get("outcome") or {}).get("code") == "did" and j.get("result") == "Dọn thư rác trong hộp thư", j)

# The other counted kinds.
c_rev = spend("review", at=NOON + 700, ctx="*")
AP.record_event(gs, K, "*", "self_review", source="learn", reason="applied:2",
                payload={"call_id": c_rev, "applied": 2, "results": [], "proposals": []}, at=NOON + 700)
c_rev0 = spend("review", at=NOON + 710, ctx="*")
AP.record_event(gs, K, "*", "self_review", source="learn", reason="applied:0",
                payload={"call_id": c_rev0, "applied": 0, "results": [], "proposals": []}, at=NOON + 710)
c_react = spend("reaction_review", at=NOON + 720)
c_judge = spend("judge_batch", at=NOON + 730)
jobs = by_id(collect())
j = jobs.get(f"run:{c_rev}") or {}
check("self-review that changed something: says how many",
      j.get("title_code") == "review" and j.get("outcome") == {"code": "reviewed", "n": 2}, j)
check("self-review that changed nothing", (jobs.get(f"run:{c_rev0}") or {}).get("outcome") == {"code": "reviewed", "n": 0})
check("reviewing a reaction has its own title", (jobs.get(f"run:{c_react}") or {}).get("title_code") == "reaction_review")
check("weighing a message in the private chat has its own title", (jobs.get(f"run:{c_judge}") or {}).get("title_code") == "judge")
check("a run with no recorded ending has no outcome, not a guessed one", (jobs.get(f"run:{c_judge}") or {}).get("outcome") is None)

# Exactly what the number counts, nothing else.
spend("scan", at=NOON + 800, status="refunded")                    # never reached the model
spend("judge_batch", at=NOON + 810, ctx="team:t1")                 # a team's batch judging: the team's quota
spend("reply", at=NOON + 820, ctx="team:t1")                       # an obligation, not a self-run
spend("scan", at=NOON + 830, key="ag_other", ctx="dm:ag_other")    # another assistant
c_err = spend("scan", at=NOON + 840, status="error")
AP.record_event(gs, K, DM, "scan_error", reason="TimeoutError", payload={"call_id": c_err}, at=NOON + 840)
c_run = spend("scan", at=NOON + 850, status="running")
c_res = spend("scan", at=NOON + 860, status="reserved")
out = collect(limit=100)
jobs = by_id(out)
used = AB.usage(gs, K, NOON + 900)["used"]
runs_today = [j for j in out["jobs"] if j["kind"] == "auto_run"]
check("as many cards as the number says", len(runs_today) == used and used == 14, (len(runs_today), used))
j = jobs.get(f"run:{c_err}") or {}
check("a run that broke: Done, marked failed, with the cause",
      j.get("bucket") == "done" and j.get("failed") is True and j.get("reason") == "TimeoutError", j)
check("a run still going: In progress", (jobs.get(f"run:{c_run}") or {}).get("bucket") == "running"
      and (jobs.get(f"run:{c_res}") or {}).get("bucket") == "running", jobs.get(f"run:{c_run}"))
check("In progress first, then newest finished first",
      [j["id"] for j in out["jobs"]][:3] == [f"run:{c_res}", f"run:{c_run}", f"run:{c_err}"], [j["id"] for j in out["jobs"]][:4])
check("counts by bucket", out["counts"]["running"] == 2 and out["counts"]["done"] == 12, out["counts"])

# Yesterday's runs stay in the tab (it is a record), while the number starts again each day.
c_old = scan({"action": "none"}, at=NOON - 86400)
check("a run from yesterday is still listed", f"run:{c_old}" in by_id(collect(limit=100)))
check("and is not in today's number", AB.usage(gs, K, NOON + 900)["used"] == 14)

# Where Open leads.
check("private chat run with no chat session yet: no Open button", (by_id(agent_jobs.collect(K, SLUG, B, goals=gs, limit=100)).get(f"run:{c_none}") or {})
      .get("open") is None)
c_team = scan({"action": "none"}, at=NOON + 870, ctx="team:t7")
j = by_id(collect(limit=100)).get(f"run:{c_team}") or {}
check("team run: Open goes to the team", j.get("open") == {"kind": "team", "team_id": "t7", "task_id": ""}, j.get("open"))


class Sessions:
    def list_sessions(self, **kw):
        return [{"id": "s_minh", "title": "Minh", "msg_count": 3}] if kw.get("channel") == f"agent:{SLUG}" else []


j = by_id(collect(limit=100, sessions=Sessions())).get(f"run:{c_did}") or {}
check("private chat run: Open goes to the assistant's chat", j.get("open") == {"kind": "chat", "session_id": "s_minh"},
      j.get("open"))
check("self-review has nothing to open", (by_id(collect(limit=100, sessions=Sessions())).get(f"run:{c_rev}") or {})
      .get("open") is None)

# Paging: finished runs read by window, like the other sources.
for i in range(45):
    spend("scan", at=NOON - (2 + i) * 86400)        # one a day: the shared ceiling is per day
out = collect(limit=30)
check("more finished runs than the page: says there are more", out["counts_partial"]["done"] is True and out["next"] == "30",
      (out["counts_partial"], out["next"]))
seen = {j["id"] for j in out["jobs"]}
nxt, guard = out["next"], 0
while nxt and guard < 10:
    more = collect(limit=30, cursor=nxt)
    seen |= {j["id"] for j in more["jobs"]}
    nxt, guard = more["next"], guard + 1
check("every run is reachable page by page", len([i for i in seen if i.startswith("run:")]) == 16 + 45, len(seen))

# Done and archive work on a run like on any finished job.
marked = collect(limit=100, marks={f"run:{c_none}": {"state": "archived", "at": 5}, f"run:{c_did}": {"state": "deleted", "at": 6}})
check("archived run moves to the archive, deleted run is gone",
      [a["id"] for a in marked["archived"]] == [f"run:{c_none}"] and f"run:{c_did}" not in by_id(marked)
      and f"run:{c_none}" not in by_id(marked), [a["id"] for a in marked["archived"]])

# The dot on the assistant's avatar: a run going on counts as working; a finished look-around is not "a job just
# finished" and a broken one does not turn the avatar red.
cn = agent_jobs.active_counts({SLUG: K}, B, goals=gs, principal=RS.Principal("owner", "owner", B), now=NOON + 900).get(SLUG, {})
check("avatar counts: only the runs still going", cn.get("running") == 2 and not cn.get("done") and not cn.get("failed"), cn)

# A self-run is not something another assistant can be asked to verify.
items = agent_jobs.verify_targets({SLUG: K, "lan": "ag_lan"}, "lan", B, goals=gs,
                                  principal=RS.Principal("owner", "owner", B))
check("verify targets: no self-runs", not [x for x in items if str(x["id"]).startswith("run:")], items[:3])

# No store, or an assistant with no key yet: just empty, no error.
bare = agent_jobs.collect(K, SLUG, B)
check("no store: empty, no error from the Auto source", bare["source_counts"].get("auto") == 0
      and not [e for e in bare["errors"] if e["source"] == "auto"], bare["errors"])
out = agent_jobs.collect("", SLUG, B, goals=gs, principal=RS.Principal("owner", "owner", B))
check("no key: no runs", not [j for j in out["jobs"] if j["kind"] == "auto_run"], out["jobs"][:2])

# One definition of "a self-run": the tab reads the rows through agent_budget, the module that counts them.
src = (SERVER / "agent_jobs.py").read_text(encoding="utf-8")
check("the tab asks agent_budget for the runs", "agent_budget" in src and "runs(" in src)
host = (SERVER / "agent_pulse_host.py").read_text(encoding="utf-8")
check("the pulse host still writes the call id and result on the scan event",
      '"scan", source="bounded" if bounded else "opportunities"' in host and '"call_id": cid, "result": result' in host)

# The two screens of the owner's report, through the real routes: the number in the Auto block
# (GET /agents/{slug}/pulse) and the Jobs tab (GET /agents/{slug}/jobs) must tell the same story.
BR = (TEMP / "brain-main").resolve()
(BR / "agents").mkdir(parents=True)
(BR / "agents" / "viet.md").write_text("\n".join(["---", "name: Viết", "role: Viết bài", "---", "Bạn là Viết.", ""]),
                                       encoding="utf-8")
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def boom(*a, **kw):
    raise AssertionError("a test must not build a real engine")


main._pulse_engine_for = boom
main._team_engine_for = boom
main._resonance_engine = boom
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
BM = str(BR)
vkey = client.post("/resonance/agents/toggle", params={"brain": BM}, json={"slug": "viet", "enabled": True}).json()[
    "agent"]["agent_key"]
empty = client.get("/agents/viet/jobs", params={"brain": BM}).json()
check("route: Auto on, nothing run yet: an empty tab is right", empty["ok"] and empty["jobs"] == [], empty.get("jobs"))
mst = main._resonance_store()
now = time.time()
rid = ALG.CallLedger(mst).reserve(purpose="scan", reason_ref=f"pulse:{vkey}:dm:{vkey}:1", agent_key=vkey,
                                  context_ref=f"dm:{vkey}", obligation=False, now=now)
ALG.CallLedger(mst).mark_engine(rid, now=now)
AP.record_event(mst, vkey, f"dm:{vkey}", "said", reason="mail:1",
                payload={"message_id": 3, "decision_id": None, "did": ["Trả lời thư của chị Hà"]}, at=now)
ALG.CallLedger(mst).settle(rid, "ok", now=now + 5)
AP.record_event(mst, vkey, f"dm:{vkey}", "scan", source="opportunities", reason="say",
                payload={"call_id": rid, "result": {"action": "say", "verdict": "acted", "message_id": 3},
                         "opportunities": ["mail:1"]}, at=now)
used = client.get("/agents/viet/pulse", params={"brain": BM}).json()["parts"]["lessons"]["budget"]["used"]
got = client.get("/agents/viet/jobs", params={"brain": BM}).json()
mine = [x for x in got["jobs"] if x["kind"] == "auto_run"]
check("route: the Auto block says 1 and the Jobs tab shows that 1 run", used == 1 and len(mine) == 1
      and got["source_counts"]["auto"] == 1, (used, got.get("source_counts")))
check("route: the card carries the work the assistant did", mine and mine[0]["outcome"] == {"code": "did"}
      and mine[0]["result"] == "Trả lời thư của chị Hà" and mine[0]["bucket"] == "done", mine[:1])
only = client.get("/agents/viet/jobs", params={"brain": BM, "source": "auto", "bucket": "done"}).json()
check("route: source and state filters keep it", [x["id"] for x in only["jobs"]] == [f"run:{rid}"], only.get("jobs"))
cnt = client.get("/agents/jobs/counts", params={"brain": BM}).json()
check("route: a finished self-run puts no dot on the assistant's avatar", "viet" not in cnt.get("counts", {}), cnt)
mk = client.post("/jobs/marks", json={"brain": BM, "ids": [f"run:{rid}"], "state": "archived"})
after = client.get("/agents/viet/jobs", params={"brain": BM}).json()
check("route: pressing Done files the run in the archive", mk.status_code == 200 and after["jobs"] == []
      and [a["id"] for a in after.get("archived", [])] == [f"run:{rid}"], (mk.status_code, after.get("archived")))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    raise SystemExit(1)
print("all ok")
