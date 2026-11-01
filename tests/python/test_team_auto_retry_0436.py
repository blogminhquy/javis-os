"""0.436.0: a team job step that failed for a temporary reason runs again on its own (team_retry).

    python tests/run.py team_auto_retry

Fake engines only, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-retry-")
os.environ.pop("JAVIS_TEAM_AUTO_RETRIES", None)
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_dispatch  # noqa: E402
import team_retry  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def err(text, tool_calls=None):
    ex = RuntimeError(text)
    if tool_calls is not None:
        ex.team_tool_calls = tool_calls
    return ex


# ---------- the rules (team_retry.plan) ----------
NOW = 1_800_000_000.0
TOOLS = TR.TOOL_ROLES


def plan(error, role="plan", failures=1, **extra):
    out = dict({"status": "error", "error": error, "detail": error, "reason": ""}, **extra)
    return team_retry.plan(out, role=role, tool_roles=TOOLS, failures=failures, provider=extra.pop("provider", ""),
                           now=NOW)


p = plan("Error 529: Overloaded")
check("overload on a text step: retry in 60 s", p and p["kind"] == "transient" and p["at"] == NOW + 60
      and p["attempt"] == 2 and p["of"] == 4, p)
check("backoff grows: 300 s, then 900 s",
      plan("rate limit", failures=2)["at"] == NOW + 300 and plan("rate limit", failures=3)["at"] == NOW + 900)
check("circuit breaker: no 4th automatic retry", plan("rate limit", failures=4) is None)
check("an error that is not temporary blocks as before", plan("engine hỏng") is None
      and plan("provider unavailable") is None)
check("a step timeout never retries (it already cost up to an hour)", plan("quá 60 phút", reason="timeout") is None)
check("a login error never retries", plan("429 auth", reason="auth") is None)
check("an error before the model was called never retries", plan("connection reset", before_engine=True) is None)
check("tool step with an unknown tool count does not retry", plan("Overloaded", role="work") is None)
check("tool step that already called a tool does not retry", plan("Overloaded", role="work", tool_calls=2) is None)
check("tool step with zero tool calls retries", (plan("Overloaded", role="help", tool_calls=0) or {}).get("kind")
      == "transient")
reset = NOW + 3600
lim = plan(f"Claude AI usage limit reached|{int(reset)}", provider="anthropic-cli")
check("plan out of quota: wait for the reset time the CLI gave", lim and lim["kind"] == "limit"
      and lim["at"] == reset + team_retry.LIMIT_GRACE_S, lim)
check("plan reset too far away: block as before",
      plan(f"Claude AI usage limit reached|{int(NOW + 3 * 86400)}", provider="anthropic-cli") is None)
os.environ["JAVIS_TEAM_AUTO_RETRIES"] = "0"
check("JAVIS_TEAM_AUTO_RETRIES=0 switches it off", plan("Overloaded") is None)
os.environ.pop("JAVIS_TEAM_AUTO_RETRIES")
steps = [{"kind": "work", "agent_key": "a", "brief": "x", "job_revision": 1, "status": "failed"},
         {"kind": "work", "agent_key": "a", "brief": "x", "job_revision": 1, "status": "failed"},
         {"kind": "work", "agent_key": "a", "brief": "y", "job_revision": 1, "status": "failed"},
         {"kind": "work", "agent_key": "a", "brief": "x", "job_revision": 2, "status": "failed"},
         {"kind": "work", "agent_key": "a", "brief": "x", "job_revision": 1, "status": "done"}]
check("a chain is the same kind, member, brief and revision", team_retry.chain_failures(steps, steps[0]) == 2)
check("Core is not pinged while a job waits for its retry",
      team_dispatch.phase({"status": "team_blocked", "block_kind": "auto_retry", "block_reason": "x"}, None)[2] is False)

# ---------- the runner ----------
AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh")}


class Fake:
    def __init__(self):
        self.script = {}
        self.calls = []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run(req):
            self.calls.append(req)
            queue = self.script.get((agent_key, role)) or []
            ans = queue.pop(0) if queue else f"{agent_key} {role} xong"
            if isinstance(ans, Exception):
                raise ans
            return {"text": ans, "tokens_in": 1, "tokens_out": 1}
        return "fake", "fake-model", run


def world(name):
    d = STATE / name
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "sessions.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()
    inbox = []

    def agent_info(brain, key):
        slug, nm = AGENTS[key]
        return {"slug": slug, "name": nm, "system": f"Bạn là {nm}."}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info,
                      publish=lambda ev: None, notify=lambda team_id, text: inbox.append((team_id, text)))
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "mô tả", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, "ag_lan")
    return ss, ts, tm, fake, r, inbox, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


ss, ts, tm, fake, r, inbox, T = world("retry")
fake.say("ag_minh", "work", err("Error 529: Overloaded", tool_calls=0), "Phần của Minh xong")
j = r.submit(T["team_id"], "Minh viết bài", mentions=["ag_minh"], as_job=True, client_msg_id="r1")
run(r.dispatch_once(wait=True))
t = ts.get_task(j["task_id"])
check("temporary error: the job waits for its retry, it is not a plain failure",
      t["status"] == "team_blocked" and t["block_kind"] == team_retry.BLOCK_KIND, (t["status"], t["block_kind"]))
check("the retry time is stored", 0 < float(t["not_before"]) <= time.time() + 61, t["not_before"])
check("no inbox ping while it waits", inbox == [], inbox)
last = ss.get_team_messages_page(T["session_id"], limit=50)["messages"][-1]
check("a calm line in the team chat says when it runs again",
      (last.get("meta") or {}).get("kind") == "job_retry_wait" and "2/4" in last["content"], last["content"])
check("not due yet: nothing runs", r.retry_due(now=time.time()) == [])
due = r.retry_due(now=time.time() + 120)
check("due: the job goes back to the queue", due == [j["task_id"]]
      and ts.get_task(j["task_id"])["status"] == "team_queued" and float(ts.get_task(j["task_id"])["not_before"]) == 0)
run(r.dispatch_once(wait=True))
check("the retried step finishes the job", ts.get_task(j["task_id"])["status"] == "done")

# Circuit breaker: four failures in a row, the fourth blocks like before.
fake.say("ag_minh", "work", *[err("503 Service Unavailable", tool_calls=0) for _ in range(4)])
j2 = r.submit(T["team_id"], "Minh làm lại", mentions=["ag_minh"], as_job=True, client_msg_id="r2")
run(r.dispatch_once(wait=True))
for i in range(3):
    check(f"breaker: retry {i + 1} scheduled", ts.get_task(j2["task_id"])["block_kind"] == team_retry.BLOCK_KIND)
    r.retry_due(now=time.time() + 3600)
    run(r.dispatch_once(wait=True))
t2 = ts.get_task(j2["task_id"])
check("breaker: after 3 automatic retries the job blocks for the owner", t2["status"] == "team_blocked"
      and t2["block_kind"] == "failed", (t2["status"], t2["block_kind"]))
check("breaker: the owner is told once it really needs them", len(inbox) == 1, inbox)
r.unblock(j2["task_id"], "retry")
fake.say("ag_minh", "work", "Được rồi")
run(r.dispatch_once(wait=True))
check("the owner's Retry still works after the breaker", ts.get_task(j2["task_id"])["status"] == "done")

# A tool step that already called a tool never runs again on its own (it may have sent or posted something).
fake.say("ag_minh", "work", err("Error 529: Overloaded", tool_calls=1))
j3 = r.submit(T["team_id"], "Minh gửi tin", mentions=["ag_minh"], as_job=True, client_msg_id="r3")
run(r.dispatch_once(wait=True))
check("a step that acted blocks for the owner", ts.get_task(j3["task_id"])["block_kind"] == "failed")

# ---------- end-of-step report (team_step_report) ----------
import json  # noqa: E402
import team_step_report as SR  # noqa: E402


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


check("report: outcome defaults to succeeded, files deduplicated",
      SR.parse({"op": "done", "summary": "ok", "files": ["a.md", "a.md", "b.md"]})
      == {"outcome": "succeeded", "summary": "ok", "files": ["a.md", "b.md"]})
check("report: an empty block is dropped", SR.parse({"op": "done"}) is None)
check("report: a short result is read in full", SR.input_text("ngắn", {"summary": "s"}, 100, 7) == "ngắn")
long_text = "x" * 5000 + " KẾT LUẬN CUỐI"
got = SR.input_text(long_text, {"summary": "Đã viết bài, 3 ý chính", "files": ["out/bai.md"]}, 4000, 9)
check("report: a long result is read as its summary and files", got.startswith("Đã viết bài") and "out/bai.md" in got
      and "#9" in got and "xxxx" not in got, got)
check("report: no report, long result is cut as before", SR.input_text(long_text, None, 4000, 9) == long_text[:4000])
check("the Work/Help note asks for the report", SR.HINT in TR.WORK_TOOLS_NOTE and "done" in TR.OPS_BY_ROLE["work"])

ss, ts, tm, fake, r, inbox, T = world("report")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="Lấy số liệu"))
fake.say("ag_minh", "work", "Không vào được POS." + directive(op="done", outcome="failed",
                                                              summary="Chưa nối POS nên không lấy được số"))
j = r.submit(T["team_id"], "Báo cáo doanh thu", as_job=True, client_msg_id="p1")
run(r.dispatch_once(wait=True))
t = ts.get_task(j["task_id"])
check("a step reporting failed stops the job for the owner", t["status"] == "team_blocked" and t["block_kind"] == "failed"
      and "Chưa nối POS" in t["block_reason"], (t["status"], t["block_kind"], t["block_reason"]))
check("no synthesis turn is spent on a failed step", not [c for c in fake.calls if c["role"] == "synthesize"])
last_agent = [m for m in ss.get_team_messages_page(T["session_id"], limit=50)["messages"] if m["author_kind"] == "agent"][-1]
check("the report block is not shown in the chat", "JAVIS_TEAM" not in last_agent["content"]
      and (last_agent.get("meta") or {}).get("report", {}).get("outcome") == "failed")

fake.calls.clear()
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="Viết bài dài")
         + directive(op="assign", agent="ag_lan", brief="Viết phần mở"))
fake.say("ag_minh", "work", "y" * 6000 + directive(op="done", summary="Bài 2.000 chữ đã ghi file", files=["out/bai.md"]))
j2 = r.submit(T["team_id"], "Viết bài", as_job=True, client_msg_id="p2")
run(r.dispatch_once(wait=True))
syn = [c for c in fake.calls if c["role"] == "synthesize"]
check("a long result reaches the synthesis as its summary", syn and "Bài 2.000 chữ đã ghi file" in syn[-1]["prompt"]
      and "yyyyyyyyyy" not in syn[-1]["prompt"], [c["role"] for c in fake.calls])
check("an input is written once: the history points to the Inputs part", syn
      and syn[-1]["prompt"].count("ag_lan work xong") == 1 and "(nội dung ở phần Đầu vào" in syn[-1]["prompt"])
check("the job still finishes", ts.get_task(j2["task_id"])["status"] == "done")

# A wave of two: one member reports failed, the other succeeds. The good result is kept, not parked to run again.
fake.calls.clear()
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="Phần A")
         + directive(op="assign", agent="ag_lan", brief="Phần B"))
fake.say("ag_minh", "work", "Hỏng." + directive(op="done", outcome="failed", summary="Thiếu dữ liệu"))
fake.say("ag_lan", "work", "Phần B xong." + directive(op="done", summary="B xong"))
j3 = r.submit(T["team_id"], "Hai phần", as_job=True, client_msg_id="p3")
run(r.dispatch_once(wait=True))
st = {s_["brief"]: s_["status"] for s_ in tm.steps(j3["task_id"]) if s_["kind"] == "work"}
check("wave: the good sibling stays done when the other reports failed", st == {"Phần A": "failed", "Phần B": "done"}, st)

raise SystemExit(1 if fails else 0)
