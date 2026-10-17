"""0.208.0: department mandate of a Team and opportunity detection from granted sources (team_mandate.py).

    python tests/python/test_team_mandate_0208.py

Fake engines and a fake clock that walks several days; real SQLite stores and real folders in a temporary directory.
Sources that need the host (Kanban, connections, commands) are fakes with the same shapes as main._MandateDeps.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-mandate-")
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_mandate as TM  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh")}
T0 = 2_000_000_000.0 - (2_000_000_000 % 86400) + 9 * 3600   # 09:00 UTC on a fixed day, far from midnight locally too
DAY = 86400.0


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class Deps:
    def __init__(self, brain, clock):
        self.brain, self.clock = brain, clock
        self.failures, self.conns, self.tests, self.opened = [], {}, {}, []
        self.store = None

    def brain_root(self, team):
        return self.brain

    def kanban_failures(self, brain, since):
        return [f for f in self.failures if f["at"] >= since]

    def mcp_status(self, cid):
        return self.conns.get(cid, {"known": False})

    def run_test(self, cmd, cwd):
        return self.tests.get(cmd, {"ran": False, "error": "không chạy được"})

    def open_job(self, team, title, intent, source_ref, blocked_kind=""):
        if getattr(self, "boom", False):
            raise RuntimeError("database is locked")
        tid, created = self.store.enqueue_team(team["brain_id"], team["team_id"], title, intent, source_ref=source_ref,
                                               chat_id=f"team:{team['team_id']}", created_by="mandate",
                                               blocked_kind=blocked_kind)
        self.opened.append((tid, title, intent, source_ref))
        return tid, created


class Fake:
    def engine_for(self, team, key, role):
        async def run_(req):
            return {"text": f"{key} {role}: đã xử lý xong", "tokens_in": 1, "tokens_out": 1}
        return "fake", "fake", run_


_n = [0]


def world(label):
    _n[0] += 1
    d = STATE / f"{_n[0]:02d}-{label}"
    brain = d / "brain"
    (brain / "bao-cao").mkdir(parents=True)
    (brain / "bao-cao" / "tuan-1.md").write_text("doanh thu 10", encoding="utf-8")
    ss = sessions.SessionStore(db_path=d / "s.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    clock = Clock(T0)
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=Fake().engine_for,
                      agent_info=lambda b, k: {"slug": AGENTS[k][0], "name": AGENTS[k][1], "system": ""}, clock=clock)
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(brain), channel=f"team:{tid}")
    tm.create_team(str(brain), label, "", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, "ag_lan")
    deps = Deps(brain, clock)
    deps.store = ts
    st = TM.MandateStore(d / "team.sqlite3", clock=clock)
    eng = TM.MandateEngine(st, r, deps)
    return r, tm, ts, ss, st, eng, deps, clock, tm.get(tid), brain


BASE = {"outcome": "Báo cáo tuần luôn đúng và kịp", "metrics": ["báo cáo có trước thứ Hai"],
        "sources": ["folder:bao-cao"], "scope": "Chỉ thư mục bao-cao", "cadence_min": 60,
        "budget": {"observe_per_day": 100, "jobs_per_day": 3}, "autonomy": {"act": ["file_changed"]}}


def touch(p, text, clock):
    p.write_text(text, encoding="utf-8")
    os.utime(p, (clock(), clock()))


# ═════ 1. Off by default, owner-only, validated ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("off")
check("no mandate: nothing observed", eng.tick() == [] and st.get(T["team_id"]) is None)
for bad, why in (({}, "outcome"), (dict(BASE, sources=[]), "nguồn"), (dict(BASE, sources=["folder:../x"]), "nguồn"),
                 (dict(BASE, sources=["http://x"]), "nguồn")):
    try:
        st.put(T["team_id"], bad)
        got = None
    except TM.MandateError as ex:
        got = str(ex)
    check(f"invalid mandate refused ({why})", got and why in got, got)
m = st.put(T["team_id"], BASE)
check("a new mandate starts off (an existing team is never switched on by itself)", m["status"] == "off" and m["version"] == 1)
check("off: still nothing observed", eng.tick() == [] and st.observations(T["team_id"]) == [])

# ═════ 2. Folder source: baseline, change -> opportunity -> job with trace; dedupe, cooldown ═════
st.set_status(T["team_id"], "active")
check("first observation is the baseline, no opportunity", eng.tick() == [] and len(st.observations(T["team_id"])) == 1)
clock.advance(3600)
touch(brain / "bao-cao" / "tuan-2.md", "doanh thu 12", clock)
acts = eng.tick()
check("a changed folder becomes one enqueue opportunity", len(acts) == 1 and acts[0]["decision"] == "enqueue"
      and acts[0]["kind"] == "file_changed", acts)
opp = st.opportunity(acts[0]["opp_id"])
check("the opportunity carries source, ref, data version, reason tied to the outcome, benefit, evidence",
      opp["source"] == "folder" and opp["ref"] == "bao-cao" and opp["version_key"] and "Báo cáo tuần" in opp["reason"]
      and opp["benefit"] and any("tuan-2.md" in e for e in opp["evidence"]), opp)
check("the job was opened with the trace in its source ref and intent", deps.opened and
      deps.opened[0][3] == f"mandate:{opp['opp_id']}" and opp["opp_id"] in deps.opened[0][2]
      and "mục tiêu v1" in deps.opened[0][2], deps.opened)
job = opp["task_id"]
run(r.dispatch_once())
check("the mandate job runs like any team job and finishes", ts.get_task(job)["status"] == "done", ts.get_task(job)["status"])
clock.advance(3600)
check("same data again: no new opportunity", eng.tick() == [])
touch(brain / "bao-cao" / "tuan-2.md", "doanh thu 13", clock)
clock.advance(60 * 30)   # tick is not due yet (cadence 60 min): nothing
check("cadence: not observed before it is due", eng.tick() == [])
clock.advance(60 * 31)
got = eng.tick()
check("after the cadence a new data version is a new opportunity", len(got) == 1, got)
touch(brain / "bao-cao" / "tuan-3.md", "x", clock)
st2 = st.get(T["team_id"])
st.put(T["team_id"], dict(BASE, cadence_min=5))   # owner shortens the cadence: new version, same status
clock.advance(6 * 60)
check("cooldown: another change of the same source within the cooldown opens nothing", eng.tick() == [])
check("an edit is a new version with history", st.get(T["team_id"])["version"] == 2 and len(st.versions(T["team_id"])) == 2
      and st.get(T["team_id"])["status"] == "active")

# ═════ 3. Missing sources are shown, never invented ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("missing")
st.put(T["team_id"], dict(BASE, sources=["folder:khong-co", "mcp:conn_x", "test:pytest -q", "kanban"]), status="active")
acts = eng.tick()
sv = {x["source"]: x for x in TM.sources_view(st, st.get(T["team_id"]))}
check("missing folder, unknown connection and a command that cannot run: no opportunity", acts == [], acts)
check("each missing source is shown with what is missing", sv["folder:khong-co"]["state"] == "missing"
      and "khong-co" in sv["folder:khong-co"]["missing"] and sv["mcp:conn_x"]["state"] == "missing"
      and sv["test:pytest -q"]["state"] == "missing" and sv["kanban"]["state"] == "ok", sv)

# ═════ 4. Other sources: test failing, Kanban failure, connection down ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("sources")
st.put(T["team_id"], dict(BASE, sources=["test:pytest -q", "kanban", "mcp:pos"],
                          autonomy={"propose": ["test_failing", "job_failed", "connection_down"]}), status="active")
deps.tests["pytest -q"] = {"ran": True, "exit": 0, "output": "3 passed"}
deps.conns["pos"] = {"known": True, "ok": True, "label": "POS"}
check("all green: nothing", eng.tick() == [])
clock.advance(3600)
deps.tests["pytest -q"] = {"ran": True, "exit": 1, "output": "1 failed"}
deps.failures.append({"ref": "t_77", "title": "Đồng bộ đơn", "error": "timeout", "at": clock()})
deps.conns["pos"] = {"known": True, "ok": False, "label": "POS", "error": "401"}
acts = eng.tick()
kinds = sorted(a["kind"] for a in acts)
check("test failing, Kanban failure and connection down each become a proposal",
      kinds == ["connection_down", "job_failed", "test_failing"] and all(a["decision"] == "propose" for a in acts), acts)
cards = [m for m in ss.get_team_messages_page(T["session_id"], limit=100)["messages"]
         if (m.get("meta") or {}).get("kind") == "mandate_opportunity"]
check("each proposal is a card in the team chat", len(cards) == 3, len(cards))

# Owner rejects one: the same data version never comes back; accepts another: a job opens.
tf = next(a for a in acts if a["kind"] == "test_failing")
cd = next(a for a in acts if a["kind"] == "connection_down")
out = eng.decide(T["team_id"], tf["opp_id"], "reject")
check("reject closes the proposal", out["ok"] and st.opportunity(tf["opp_id"])["status"] == "rejected")
again = eng.decide(T["team_id"], tf["opp_id"], "accept")
check("a decided proposal cannot be decided again", not again["ok"] and again["error"] == "already_decided")
clock.advance(3 * 3600)
check("rejected and unchanged: not reopened", not [a for a in eng.tick() if a["kind"] == "test_failing"])
out = eng.decide(T["team_id"], cd["opp_id"], "accept")
check("accept opens the job (owner-opened)", out["ok"] and st.opportunity(cd["opp_id"])["status"] == "enqueued"
      and st.opportunity(cd["opp_id"])["decided_by"] == "owner" and st.opportunity(cd["opp_id"])["task_id"])
clock.advance(3 * 3600)
deps.tests["pytest -q"] = {"ran": True, "exit": 2, "output": "2 failed, new"}
check("a rejected source with NEW data comes back", [a for a in eng.tick() if a["kind"] == "test_failing"])

# ═════ 5. Approve level: the job waits for the owner's card (0.207.0 gate) ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("approve")
st.put(T["team_id"], dict(BASE, autonomy={"approve": ["file_changed"]}), status="active")
eng.tick()
clock.advance(3600)
touch(brain / "bao-cao" / "moi.md", "y", clock)
acts = eng.tick()
opp = st.opportunity(acts[0]["opp_id"])
job = opp["task_id"]
check("approve level: job opened but stopped waiting for the owner", acts[0]["decision"] == "ask"
      and ts.get_task(job)["status"] == "team_blocked" and ts.get_task(job)["block_kind"] == "waiting_user")
ap = r.approvals.pending_for_task(job)
check("approve level: a plan approval card from the mandate", ap and ap["kind"] == "plan"
      and ap["requested_by"].startswith("mandate:") and opp["approval_id"] == ap["approval_id"], ap)
run(r.dispatch_once())
check("approve level: nothing runs before the decision", not tm.steps(job))
res = r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="m1")
run(r.dispatch_once())
check("approve level: after approval the job runs and finishes", res["ok"] and ts.get_task(job)["status"] == "done",
      (res, ts.get_task(job)["status"]))
tr = eng.trace(T["team_id"], opp["opp_id"])
check("trace: mandate version -> observation -> opportunity -> decision -> approval -> job -> steps",
      tr["mandate"]["version"] == 1 and tr["observation"]["id"] == opp["observation_id"]
      and tr["opportunity"]["opp_id"] == opp["opp_id"] and tr["decision"] == "ask"
      and tr["approvals"] and tr["approvals"][0]["status"] == "consumed" and tr["job"]["status"] == "done"
      and tr["steps"], tr)

# ═════ 6. Budget per day and the next day; stop rule ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("budget")
st.put(T["team_id"], dict(BASE, sources=["folder:bao-cao", "kanban"], budget={"observe_per_day": 100, "jobs_per_day": 1},
                          autonomy={"act": ["file_changed", "job_failed"]}), status="active")
eng.tick()
clock.advance(3600)
touch(brain / "bao-cao" / "a.md", "1", clock)
deps.failures.append({"ref": "t_1", "title": "x", "error": "e", "at": clock()})
acts = sorted(eng.tick(), key=lambda a: a["kind"])
check("budget: the first opens a job, the rest of the day only proposes",
      sorted(a["decision"] for a in acts) == ["enqueue", "propose"], acts)
clock.advance(DAY)
touch(brain / "bao-cao" / "b.md", "2", clock)
acts = eng.tick()
check("next day the budget is back", [a["decision"] for a in acts] == ["enqueue"], acts)
st.put(T["team_id"], dict(BASE, budget={"observe_per_day": 100, "jobs_per_day": 9}, stop={"max_open_jobs": 0},
                          autonomy={"act": ["file_changed"]}))
clock.advance(2 * 3600)
touch(brain / "bao-cao" / "c.md", "3", clock)
acts = eng.tick()
check("stop rule max_open_jobs: above it nothing new opens, only proposed", [a["decision"] for a in acts] == ["propose"], acts)

r, tm, ts, ss, st, eng, deps, clock, T, brain = world("observe-budget")
st.put(T["team_id"], dict(BASE, cadence_min=5, budget={"observe_per_day": 2, "jobs_per_day": 3}), status="active")
for _ in range(5):
    eng.tick()
    clock.advance(10 * 60)
check("observation budget per day is respected", st.observations_since(T["team_id"], T0 - 3600) == 2,
      st.observations_since(T["team_id"], T0 - 3600))

# ═════ 7. Pause, revoke, expiry ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("revoke")
st.put(T["team_id"], dict(BASE, sources=["folder:bao-cao", "test:t"], autonomy={"act": ["file_changed"],
                                                                                 "propose": ["test_failing"]}),
       status="active")
deps.tests["t"] = {"ran": True, "exit": 0, "output": ""}
eng.tick()
st.set_status(T["team_id"], "paused")
clock.advance(3600)
touch(brain / "bao-cao" / "p.md", "x", clock)
check("paused: nothing observed", eng.tick() == [])
st.set_status(T["team_id"], "active")
deps.tests["t"] = {"ran": True, "exit": 1, "output": "đỏ"}
acts = eng.tick()
job = next(st.opportunity(a["opp_id"])["task_id"] for a in acts if a["decision"] == "enqueue")
prop = next(a["opp_id"] for a in acts if a["decision"] == "propose")
out = eng.revoke(T["team_id"])
check("revoke: the queued mandate job is cancelled", job in out["cancelled"] and ts.get_task(job)["status"] == "cancelled")
check("revoke: open proposals close", st.opportunity(prop)["status"] == "dismissed")
clock.advance(3600)
touch(brain / "bao-cao" / "q.md", "x", clock)
check("revoked: nothing observed anymore", eng.tick() == [])
try:
    st.set_status(T["team_id"], "active")
    reopened = True
except TM.MandateError:
    reopened = False
check("revoked: cannot be switched back on without rewriting it", not reopened)

r, tm, ts, ss, st, eng, deps, clock, T, brain = world("expire")
st.put(T["team_id"], dict(BASE, autonomy={"propose": ["file_changed"]}), status="active")
eng.tick()
clock.advance(3600)
touch(brain / "bao-cao" / "z.md", "x", clock)
acts = eng.tick()
clock.advance(TM.DEFAULT_EXPIRE_H * 3600 + 60)
eng.tick()
check("an open proposal expires after its time", st.opportunity(acts[0]["opp_id"])["status"] == "expired")

# ═════ 8. Two teams, one brain: mandates do not cross ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("multi")
tid2 = team_store.new_team_id()
sid2 = ss.create_session(brain=str(brain), channel=f"team:{tid2}")
tm.create_team(str(brain), "team 2", "", sid2, team_id=tid2)
tm.add_member(tid2, "ag_minh", "minh")
tm.set_leader(tid2, "ag_minh")
(brain / "kho").mkdir()
st.put(T["team_id"], BASE, status="active")
st.put(tid2, dict(BASE, sources=["folder:kho"]), status="active")
eng.tick()
clock.advance(3600)
touch(brain / "kho" / "k.md", "1", clock)
acts = eng.tick()
check("a change in team 2's source opens a job only for team 2",
      len(acts) == 1 and st.opportunity(acts[0]["opp_id"])["team_id"] == tid2
      and ts.get_task(st.opportunity(acts[0]["opp_id"])["task_id"])["team_id"] == tid2, acts)

# ═════ 9. Review 0.208.0 fixes ═════
r, tm, ts, ss, st, eng, deps, clock, T, brain = world("race")
st.put(T["team_id"], dict(BASE, sources=["folder:bao-cao", "test:slow"], autonomy={"act": ["file_changed", "test_failing"]}),
       status="active")
deps.tests["slow"] = {"ran": True, "exit": 0, "output": ""}
eng.tick()
clock.advance(3600)
touch(brain / "bao-cao" / "r.md", "x", clock)


def slow_and_revoke(cmd, cwd):
    eng.revoke(T["team_id"])          # the owner revokes while the check command is running
    return {"ran": True, "exit": 1, "output": "đỏ"}

deps.run_test = slow_and_revoke
acts = eng.tick()
live = [o for o in st.opportunities(T["team_id"], limit=50) if o.get("task_id")
        and ts.get_task(o["task_id"])["status"] not in ("cancelled",)]
check("revoke during an observation: nothing opened after it stays alive", live == [], [(o["kind"], o["status"]) for o in live])

r, tm, ts, ss, st, eng, deps, clock, T, brain = world("cooldown-keep")
st.put(T["team_id"], dict(BASE, cadence_min=5, autonomy={"propose": ["file_changed"]}), status="active")
eng.tick()
clock.advance(600)
touch(brain / "bao-cao" / "a2.md", "1", clock)
first = eng.tick()
clock.advance(600)
touch(brain / "bao-cao" / "b2.md", "2", clock)
check("cooldown holds the second change back", eng.tick() == [])
clock.advance(TM.DEFAULT_COOLDOWN_MIN * 60)
later = eng.tick()
check("after the cooldown the held-back change comes out (not lost)", len(first) == 1 and len(later) == 1
      and any("b2.md" in e for e in st.opportunity(later[0]["opp_id"])["evidence"]), later)

r, tm, ts, ss, st, eng, deps, clock, T, brain = world("accepting")
st.put(T["team_id"], dict(BASE, autonomy={"propose": ["file_changed"]}), status="active")
eng.tick()
clock.advance(3600)
touch(brain / "bao-cao" / "c.md", "1", clock)
acts = eng.tick()
deps.boom = True
try:
    eng.decide(T["team_id"], acts[0]["opp_id"], "accept")
except RuntimeError:
    pass
deps.boom = False
check("a failed accept goes back to the owner's card, never stuck in accepting",
      st.opportunity(acts[0]["opp_id"])["status"] == "proposed")

r, tm, ts, ss, st, eng, deps, clock, T, brain = world("blocked-create")
st.put(T["team_id"], dict(BASE, autonomy={"approve": ["file_changed"]}), status="active")
eng.tick()
clock.advance(3600)
touch(brain / "bao-cao" / "d.md", "1", clock)
real_needs = r.mandate_job_needs_approval
r.mandate_job_needs_approval = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("busy"))
try:
    eng.tick()
except RuntimeError:
    pass
r.mandate_job_needs_approval = real_needs
opened = [o for o in deps.opened]
check("approve level: a job whose card failed is never runnable (created stopped, then cancelled)",
      opened and ts.get_task(opened[-1][0])["status"] in ("cancelled", "team_blocked"), opened)
try:
    st.put(T["team_id"], BASE, status="revoked")
    ok_put = True
except TM.MandateError:
    ok_put = False
check("an edit cannot set revoked (only the Revoke action with its cleanup)", not ok_put)
eng.revoke(T["team_id"])
try:
    st.set_status(T["team_id"], "off")
    back = True
except TM.MandateError:
    back = False
check("revoked cannot go back through off", not back)

print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    raise SystemExit(1)
print("ALL OK")
