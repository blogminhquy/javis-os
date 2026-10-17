"""0.210.0: host-level, seven simulated days, three teams in two brains, fake engines only.

    python tests/python/test_team_multiday_0210.py

What it proves end to end (real TeamRunner, real stores, real hub guard with the outbound call counted, a fake clock
that walks hour by hour, one restart in the middle):
- goal -> observation -> opportunity -> decision -> approval -> execution -> product -> acceptance, traceable;
- a step that needs the owner really stops (slot released, never done, nothing executed) and survives a restart;
- an approved outside action runs exactly once, a rejected or expired one never;
- the mandate stays inside its sources and budget, rejected data never comes back unchanged, revoke stops it;
- a job is done only when its product passes the owner's criteria;
- teams do not interfere with each other.

Fail fast if anything tries to build a real engine: JAVIS_NO_REAL_TEAM_ENGINE=1 and the runner only gets the fake.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

# Day boundaries are local time in the code (budgets per day); pin the zone so the simulated days are the same on
# every machine (review 0.210.0: Tokyo or Auckland crossed midnight inside "day 1").
os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-multiday-")
os.environ["JAVIS_NO_REAL_TEAM_ENGINE"] = "1"
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_approval  # noqa: E402
import team_mandate as TM  # noqa: E402
import team_runner as TR  # noqa: E402
import team_gate  # noqa: E402
import team_store  # noqa: E402

fails = []
LOG = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:600]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


HOUR, DAY = 3600.0, 86400.0
T0 = 2_000_000_000.0 - (2_000_000_000 % DAY) + 8 * HOUR


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


clock = Clock(T0)
EFFECTS = []


async def fake_call_route(route, fn, args):
    EFFECTS.append((fn, json.dumps(args, sort_keys=True, ensure_ascii=False)))
    return "đã gửi"


ZALO = {"conn": {"id": "c_zalo", "connector_id": "zalo-test", "perm": "full", "label": "Zalo"}, "tool": "send_message",
        "spec": {}}

AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh"), "ag_hoa": ("hoa", "Hoa"), "ag_tu": ("tu", "Tú")}


class Fake:
    """Script per (agent, role); an entry is a string or an async function of the request."""

    def __init__(self):
        self.script, self.calls = {}, []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, key, role):
        async def run_(req):
            self.calls.append({"team": team["team_id"], "agent": key, "role": role, "gate": req.get("team_gate"),
                               "at": clock()})
            q = self.script.get((key, role)) or []
            ans = q.pop(0) if q else f"{AGENTS[key][1]} ({role}) đã xử lý xong."
            if callable(ans):
                ans = await ans(req)
            return {"text": ans, "tokens_in": 2, "tokens_out": 2}
        return "fake", "fake-model", run_


def writer(path, text, reply="Đã ghi sản phẩm"):
    async def go(req):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        return reply
    return go


def sender(args):
    async def go(req):
        # The hub level the engine factory gives the step: gated with a gate, full for a team the owner set to full.
        mode = team_gate.HUB_MODE if req.get("team_gate") else "full"
        out = await mcp_hub._guard(ZALO, "zalo_send_message", mode)(args)
        return f"Gửi tin: {out}"
    return go


class MDeps:
    def __init__(self, ts):
        self.ts, self.tests, self.clock = ts, {}, clock

    def brain_root(self, team):
        return Path(team["brain_id"])

    def kanban_failures(self, brain, since):
        return []

    def mcp_status(self, cid):
        return {"known": False}

    def run_test(self, cmd, cwd):
        return self.tests.get(cmd, {"ran": False, "error": "không chạy"})

    def open_job(self, team, title, intent, source_ref, blocked_kind=""):
        return self.ts.enqueue_team(team["brain_id"], team["team_id"], title, intent, source_ref=source_ref,
                                    chat_id=f"team:{team['team_id']}", created_by="mandate", blocked_kind=blocked_kind)


# ── the world: two brains, three teams ──
B1, B2 = STATE / "brain-shop", STATE / "brain-ops"
for b in (B1, B2):
    (b / "yeu-cau").mkdir(parents=True)
ss = sessions.SessionStore(db_path=STATE / "s.db")
ts = task_store.TaskStore(STATE / "kanban.sqlite3")
tm = team_store.TeamStore(STATE / "team.sqlite3")
fake = Fake()


def info(brain, key):
    return {"slug": AGENTS[key][0], "name": AGENTS[key][1], "system": ""} if key in AGENTS else None


def make_runner():
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=info, clock=clock,
                      max_parallel_teams=3)
    st = TM.MandateStore(STATE / "team.sqlite3", clock=clock)
    eng = TM.MandateEngine(st, r, MDeps(ts))
    return r, st, eng


def team(brain, name, members, leader, mode=None):
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(brain), channel=f"team:{tid}")
    tm.create_team(str(brain), name, "", sid, team_id=tid)
    for k in members:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, leader)
    if mode:
        tm.set_work_mode(tid, mode)
    return tm.get(tid)


A = team(B1, "Nội dung", ["ag_lan", "ag_minh"], "ag_lan")
B = team(B1, "Bán hàng", ["ag_hoa", "ag_minh"], "ag_hoa")
C = team(B2, "Vận hành", ["ag_tu"], "ag_tu", mode="full")
r, st, eng = make_runner()
# Fail fast: the REAL engine factory refuses to build anything in this test (review 0.210.0: comparing the runner's
# factory with itself proved nothing).
import main  # noqa: E402
import team_engine  # noqa: E402
real_built = []
with patch.object(main, "_team_agent_info", side_effect=info):
    _p, _m, real_run = main._team_engine_for(A, "ag_lan", "plan")

    async def _try_real():
        try:
            await real_run({"team_id": A["team_id"], "system": "", "prompt": "x", "turn_id": "tu_x",
                            "engine_started": lambda *a: None, "tool_turn": False})
            return "built"
        except TR.EngineUnavailable as ex:
            return str(ex)
    why = run(_try_real())
check("fail fast: the real team engine factory refuses to build an engine (JAVIS_NO_REAL_TEAM_ENGINE)",
      "JAVIS_NO_REAL_TEAM_ENGINE" in why and team_engine.build is main._TEAM_ENGINE_BUILD_REAL, why)
check("fail fast: this week runs on the fake engine factory only", r.engine_for == fake.engine_for)

st.put(A["team_id"], {"outcome": "Mỗi yêu cầu nội dung có bài viết đạt chuẩn", "sources": ["folder:yeu-cau"],
                      "scope": "Chỉ thư mục yeu-cau và bai-viet", "cadence_min": 60,
                      "budget": {"observe_per_day": 30, "jobs_per_day": 1}, "autonomy": {"approve": ["file_changed"]}},
       status="active")
st.put(B["team_id"], {"outcome": "Kịch bản bán hàng luôn chạy đúng", "sources": ["test:kiem-tra-kich-ban"],
                      "cadence_min": 60, "autonomy": {"propose": ["test_failing"]}}, status="active")
eng.deps.tests["kiem-tra-kich-ban"] = {"ran": True, "exit": 0, "output": "ok"}


def tick_hours(n, actions=None):
    """Advance the clock hour by hour: mandates observe, the runner dispatches, deadlines expire."""
    global r, eng
    for h in range(n):
        clock.t += HOUR
        if actions and h in actions:
            actions[h]()
        r.expire_approvals()
        for a in eng.tick():
            LOG.append(("opp", clock(), a))
        run(r.dispatch_once())


patches = [patch.object(mcp_client, "call_route", side_effect=fake_call_route),
           patch.object(mcp_catalog, "classify", side_effect=lambda c, t, a=None: "danger" if "send" in t else "read"),
           patch.object(mcp_catalog, "get", side_effect=lambda cid: {"id": cid})]
for p in patches:
    p.start()

tick_hours(1)   # baselines

# ═════ Day 1: a request lands for team A -> approve-level job -> owner sets criteria and approves -> fix -> pass ═════
(B1 / "yeu-cau" / "bai-ra-mat.md").write_text("Cần bài ra mắt sản phẩm, có giá và cách liên hệ.", encoding="utf-8")
tick_hours(1)
opps_a = st.opportunities(A["team_id"])
check("day 1: the new request became one opportunity with source, version and reason", len(opps_a) == 1
      and opps_a[0]["source"] == "folder" and opps_a[0]["version_key"] and "yeu-cau" in opps_a[0]["reason"] + opps_a[0]["ref"],
      opps_a)
job_a = opps_a[0]["task_id"]
check("day 1: the mandate job waits for the owner before any step", ts.get_task(job_a)["block_kind"] == "waiting_user"
      and not tm.steps(job_a))
r.set_acceptance(A["team_id"], job_a, [{"kind": "file_contains", "path": "bai-viet/ra-mat.md", "min_chars": 40,
                                        "must_contain": ["giá", "liên hệ"]}], fix_rounds=2)
fake.say("ag_lan", "plan", writer(B1 / "bai-viet" / "ra-mat.md", "Bản nháp ngắn."),
         writer(B1 / "bai-viet" / "ra-mat.md", "Ra mắt sản phẩm mới: giá 199 nghìn, liên hệ 0900 000 000 để đặt sớm."))
ap = r.approvals.pending_for_task(job_a)
tick_hours(3, {0: lambda: r.decide_approval(A["team_id"], ap["approval_id"], "approve", decision_key="d1-a")})
t = ts.get_task(job_a)
check("day 1: done only after the product passed the criteria (one fix round)", t["status"] == "done"
      and [h["verdict"] for h in r.acceptance.history(job_a)] == ["fail", "pass"], (t["status"], r.acceptance.history(job_a)))
tr = eng.trace(A["team_id"], opps_a[0]["opp_id"])
check("day 1: full trace goal -> observation -> opportunity -> decision -> approval -> job -> product acceptance",
      tr["mandate"]["version"] == 1 and tr["observation"] and tr["decision"] == "ask"
      and tr["approvals"][0]["status"] == "consumed" and tr["job"]["status"] == "done"
      and tr["acceptance"]["status"] == "passed" and tr["acceptance"]["last"][0]["evidence"]["sha256"], tr)

# Budget: a second request the same day is only proposed (jobs_per_day = 1).
(B1 / "yeu-cau" / "bai-2.md").write_text("Bài thứ hai", encoding="utf-8")
clock.t += 61 * 60
tick_hours(1)
second = [o for o in st.opportunities(A["team_id"]) if o["opp_id"] != opps_a[0]["opp_id"]]
check("day 1: past the day's job budget the next opportunity is only proposed", second and second[0]["decision"] == "propose",
      second)
rej = eng.decide(A["team_id"], second[0]["opp_id"], "reject")
check("day 1: the owner rejects that proposal", rej["ok"] and st.opportunity(second[0]["opp_id"])["status"] == "rejected", rej)
# Stays inside its sources: a change in a folder the mandate was not given never becomes anything.
(B1 / "khac").mkdir()
n_before = len(st.opportunities(A["team_id"], limit=200))
(B1 / "khac" / "bi-mat.md").write_text("không thuộc nguồn được giao", encoding="utf-8")
tick_hours(2)
check("day 1: a change outside the granted sources makes no opportunity",
      len(st.opportunities(A["team_id"], limit=200)) == n_before)

# A rejected outside action never runs: team B is asked to message customers on day 1 and the owner says no.
fake.say("ag_minh", "work", sender({"threadId": "nhom-khach", "message": "Giảm giá 50% hôm nay!"}))
job_r = r.submit(B["team_id"], "Nhắn nhóm khách báo giảm giá", mentions=["ag_minh"], as_job=True,
                 client_msg_id="r1")["task_id"]
tick_hours(1)
ap_r = r.approvals.pending_for_task(job_r)
r.decide_approval(B["team_id"], ap_r["approval_id"], "reject", note="Không giảm giá kiểu này", decision_key="d1-r")
tick_hours(2)
check("day 1: a rejected outside action never ran and the job stays stopped with the reason", EFFECTS == []
      and ts.get_task(job_r)["block_kind"] == "rejected" and r.approvals.get(ap_r["approval_id"])["status"] == "rejected",
      (EFFECTS, ts.get_task(job_r)["block_kind"]))

# ═════ Day 2: team B's check fails -> proposal -> owner accepts -> member wants to send -> gate -> approve -> once ═════
clock.t = T0 + DAY + HOUR
eng.deps.tests["kiem-tra-kich-ban"] = {"ran": True, "exit": 1, "output": "kịch bản 3 sai giá"}
tick_hours(1)
opp_b = [o for o in st.opportunities(B["team_id"]) if o["kind"] == "test_failing"]
check("day 2: the failing check became a proposal for team B", opp_b and opp_b[0]["status"] == "proposed", opp_b)
SEND = {"threadId": "nhom-khach", "message": "Shop đã sửa giá kịch bản 3, mời anh chị xem lại."}
fake.say("ag_minh", "work", sender(SEND), sender(SEND))
eng.decide(B["team_id"], opp_b[0]["opp_id"], "accept")
job_b = st.opportunity(opp_b[0]["opp_id"])["task_id"]
fake.say("ag_hoa", "plan", "Giao Minh sửa và báo khách." + '\n<!-- JAVIS_TEAM: {"op": "assign", "agent": "ag_minh", "brief": "Sửa giá và báo nhóm khách"} -->')
tick_hours(2)
ap_b = r.approvals.pending_for_task(job_b)
check("day 2: the outside send was stopped before it ran and became an exact-call request", EFFECTS == [] and ap_b
      and ap_b["kind"] == "action" and "nhom-khach" in ap_b["fingerprints"][0]["call"], (EFFECTS, ap_b))
fake.say("ag_tu", "work", "Đã kiểm kho xong.")
job_c0 = r.submit(C["team_id"], "Kiểm kho trong lúc B chờ", mentions=["ag_tu"], as_job=True, client_msg_id="c0")["task_id"]
tick_hours(1)
check("day 2: while team B waits for the owner, another team's job runs in the next tick",
      ts.get_task(job_b)["block_kind"] == "waiting_user" and ts.get_task(job_c0)["status"] == "done",
      (ts.get_task(job_b)["block_kind"], ts.get_task(job_c0)["status"]))

# ═════ Day 3: restart while B waits; approve after the restart -> the send runs once ═════
clock.t = T0 + 2 * DAY + HOUR
# Restart: every store reopened from its file, no gate of the old process left in memory.
team_gate._GATES.clear()
ss = sessions.SessionStore(db_path=STATE / "s.db")
ts = task_store.TaskStore(STATE / "kanban.sqlite3")
tm = team_store.TeamStore(STATE / "team.sqlite3")
r, st, eng = make_runner()
eng.deps.tests["kiem-tra-kich-ban"] = {"ran": True, "exit": 1, "output": "kịch bản 3 sai giá"}
rep = r.recover()
check("day 3: after the restart the waiting job is neither resumed nor failed", job_b not in rep["resumed"]
      and ts.get_task(job_b)["block_kind"] == "waiting_user" and r.approvals.get(ap_b["approval_id"])["status"] == "pending")
r.decide_approval(B["team_id"], ap_b["approval_id"], "approve", decision_key="d3-b")
tick_hours(2)
check("day 3: the approved send ran exactly once and the job finished", len(EFFECTS) == 1 and ts.get_task(job_b)["status"] == "done",
      (EFFECTS, ts.get_task(job_b)["status"]))
fake.say("ag_minh", "work", sender(SEND))
job_b2 = r.submit(B["team_id"], "Gửi lại đúng tin đó", mentions=["ag_minh"], as_job=True, client_msg_id="b2")["task_id"]
tick_hours(1)
check("day 3: the same send in a new job is stopped again (the approval was used, it does not carry over)",
      len(EFFECTS) == 1 and r.approvals.pending_for_task(job_b2) is not None, (EFFECTS, ts.get_task(job_b2)["block_kind"]))

# ═════ Day 4: team C (full) works in parallel, untouched by the gate ═════
clock.t = T0 + 3 * DAY + HOUR
SEND_C = {"threadId": "nhom-van-hanh", "message": "Lịch trực tuần này đã có."}
fake.say("ag_tu", "work", sender(SEND_C))
job_c = r.submit(C["team_id"], "Báo lịch trực cho nhóm", mentions=["ag_tu"], as_job=True, client_msg_id="c1")["task_id"]
tick_hours(1)
gates_c = [c["gate"] for c in fake.calls if c["team"] == C["team_id"]]
check("day 4: the full team sends without a gate and without asking (the owner's choice)",
      ts.get_task(job_c)["status"] == "done" and gates_c and not any(gates_c) and len(EFFECTS) == 2
      and r.approvals.for_task(job_c) == [], (gates_c, EFFECTS))

# ═════ Day 4-6: reject a proposal; unchanged data never comes back; new data does ═════
tick_hours(24)
check("days 4-5: the rejected opportunity stays rejected",
      st.opportunity(second[0]["opp_id"])["status"] == "rejected")
check("days 4-5: a rejected opportunity with unchanged data never came back",
      len([o for o in st.opportunities(A["team_id"]) if o["status"] in ("proposed", "asked", "enqueued", "open")
           and o["opp_id"] != opps_a[0]["opp_id"]]) == 0)

# Approval deadline expires overnight: nothing runs.
clock.t = T0 + 5 * DAY + HOUR
fake.say("ag_minh", "work", "Xin duyệt chi tiền." + '\n<!-- JAVIS_TEAM: {"op": "ask_approval", "title": "Chạy quảng cáo 2 triệu", '
         '"action": "Chạy 2 ngày", "deadline_at": ' + str(clock.t + 6 * HOUR) + "} -->")
job_d = r.submit(B["team_id"], "Đề xuất quảng cáo", mentions=["ag_minh"], as_job=True, client_msg_id="d1")["task_id"]
tick_hours(1)
ap_d = r.approvals.pending_for_task(job_d)
tick_hours(12)
check("day 6: an approval left past its deadline expired, the job says so, nothing ran",
      r.approvals.get(ap_d["approval_id"])["status"] == "expired" and ts.get_task(job_d)["block_kind"] == "approval_expired"
      and len(EFFECTS) == 2, (r.approvals.get(ap_d["approval_id"])["status"], ts.get_task(job_d)["block_kind"]))

(B1 / "yeu-cau" / "bai-2.md").write_text("Bài thứ hai, đã thêm yêu cầu mới", encoding="utf-8")
tick_hours(2)
check("day 6: new data on the rejected source makes a new opportunity",
      any(o["ref"] == "yeu-cau" and o["status"] in ("asked", "proposed") and o["created_at"] > T0 + 5 * DAY
          and o["version_key"] != second[0]["version_key"] for o in st.opportunities(A["team_id"])))

# ═════ Day 7: revoke team A's mandate -> its unstarted job cancelled, nothing new ═════
clock.t = T0 + 6 * DAY + HOUR
out = eng.revoke(A["team_id"])
(B1 / "yeu-cau" / "bai-3.md").write_text("Yêu cầu sau khi thu hồi", encoding="utf-8")
before = len(st.opportunities(A["team_id"], limit=200))
tick_hours(6)
check("day 7: after revoke nothing new is observed or opened", len(st.opportunities(A["team_id"], limit=200)) == before
      and all(ts.get_task(t_)["status"] == "cancelled" for t_ in out["cancelled"]))

# ═════ Invariants over the whole week ═════
all_jobs = [ts.get_task(o["task_id"]) for tm_ in (A, B) for o in st.opportunities(tm_["team_id"], limit=200) if o.get("task_id")]
with_criteria = [j for j in all_jobs if r.acceptance.get(j["id"])]
check("week: every job with criteria that is done has a passing or owner-confirmed acceptance",
      all(r.acceptance.get(j["id"])["status"] in ("passed", "accepted") for j in with_criteria if j["status"] == "done"))
check("week: exactly two outside effects: the one the owner approved for B and the full team's own",
      len(EFFECTS) == 2 and EFFECTS[0][1] == json.dumps(SEND, sort_keys=True, ensure_ascii=False)
      and EFFECTS[1][1] == json.dumps(SEND_C, sort_keys=True, ensure_ascii=False), EFFECTS)
per_day = {}
for o in st.observations(A["team_id"], limit=5000):
    per_day.setdefault(int((o["observed_at"] - T0) // DAY), set()).add(o["observed_at"])
check("week: observations per day never exceed the mandate's observe_per_day (30)",
      per_day and max(len(v) for v in per_day.values()) <= 30, {k: len(v) for k, v in per_day.items()})
done_waiting = [j for j in ts.team_tasks_by_status("done") if r.approvals.pending_for_task(j["id"])]
check("week: no job is done while it still has a pending approval", done_waiting == [], done_waiting)
check("week: every mandate job carries its trace in the source ref", all(
    str(j.get("source_ref") or "").startswith("mandate:op_") for j in all_jobs), [j.get("source_ref") for j in all_jobs])
summary = {"opportunities": sum(len(st.opportunities(x["team_id"], limit=500)) for x in (A, B)),
           "approvals": len(r.approvals.for_team(A["team_id"])) + len(r.approvals.for_team(B["team_id"])),
           "effects": len(EFFECTS), "engine_calls": len(fake.calls)}
print("summary", json.dumps(summary, ensure_ascii=False))

# The pilot's trace export reads this week back, read-only, as the chain the report will use.
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("trace_export", ROOT / "pilot" / "team-multiday" / "trace_export.py")
te = importlib.util.module_from_spec(spec)
spec.loader.exec_module(te)
lines = te.export(STATE, A["team_id"])
links = [x["link"] for x in lines]
first_opp = opps_a[0]["opp_id"]
chain = [x["link"] for x in lines if x.get("opp_id") == first_opp or x.get("task_id") == job_a]
check("trace export: the pilot tool reads the chain mandate -> observation -> opportunity -> decision -> approval -> "
      "job -> steps -> acceptance", all(k in links for k in ("mandate_version", "observation", "opportunity"))
      and all(k in chain for k in ("opportunity", "decision", "approval", "job", "step", "acceptance")), chain)
acc_line = next(x for x in lines if x["link"] == "acceptance" and x["task_id"] == job_a)
check("trace export: acceptance carries the checks with sha256 evidence",
      acc_line["status"] == "passed" and acc_line["checks"][-1]["evidence"].get("sha256"), acc_line)

for p in patches:
    p.stop()
print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    raise SystemExit(1)
print("ALL OK")
