"""Team work carries on by itself after a restart (owner, 16/11/2026).

    python tests/python/test_team_resume_after_restart.py

Owner: "sau mỗi lần cập nhật thì các team tự khởi động lại để tiếp tục công việc". Before this a job whose step was
talking to the model when the server stopped was blocked as `interrupted` until the owner pressed Continue, and a chat
reply cut the same way showed "Retry". Now both run again by themselves. Two cases still stop and ask: an outside action
of the step may already have gone out (once_ledger), or restarts cut the same step RESTART_RESUME_MAX times already.
Real stores on temp SQLite, fake engine, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-resume-")
os.environ.pop("JAVIS_RESUME_AFTER_RESTART", None)
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import once_ledger  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_store  # noqa: E402
import team_runner as TR  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh"), "ag_hoa": ("hoa", "Hoa")}


class Fake:
    def __init__(self):
        self.calls = []

    def engine_for(self, team, agent_key, role):
        async def run(req):
            self.calls.append(req)
            return {"text": f"{agent_key} {role} xong", "tokens_in": 11, "tokens_out": 7}
        return "fake", "fake-model", run


def world(name):
    d = STATE / name
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "sessions.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for,
                      agent_info=lambda brain, key: {"slug": AGENTS[key][0], "name": AGENTS[key][1], "system": ""})
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, "ag_lan")
    return ss, ts, tm, fake, r, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


def cut_job(ts, tm, r, T, text, n, who="ag_minh"):
    """A job whose Work step reached the model, then the server died: the turn is open and past the engine mark."""
    j = r.submit(T["team_id"], text, mentions=[who], as_job=True, client_msg_id=f"cut-{n}")
    ts.claim_team_next(T["team_id"], "old-worker")
    r.start_job_steps(j["task_id"])
    st = tm.next_queued_step(j["task_id"])
    tm.claim_step(st["step_id"])
    tu = tm.reserve_turn(T["team_id"], j["task_id"], st["step_id"], who, "work")
    tm.mark_engine(tu, "fake", "fake-model")
    return j["task_id"], st, tu


def system_notes(ss, T):
    return [m["content"] for m in ss.get_team_messages_page(T["session_id"], limit=200)["messages"] if m["author_kind"] == "system"]


# ---------- a step cut by the restart runs again by itself ----------
ss, ts, tm, fake, r, T = world("resume")
task, st, tu = cut_job(ts, tm, r, T, "Viết bài", 1)
rep = r.recover()
steps = tm.steps(task)
check("the cut turn is settled once and its step is marked interrupted", tm.turn(tu)["status"] == "interrupted"
      and tm.step(st["step_id"])["status"] == "interrupted")
check("the job is not blocked: it is handed back to run on", task in rep["resumed"] and task not in rep["blocked"]
      and ts.get_task(task)["status"] == "team_running", (rep, ts.get_task(task)["status"]))
again = [s for s in steps if s["status"] == "queued"]
check("a new step waits for the same member with the same brief", len(again) == 1 and again[0]["agent_key"] == st["agent_key"]
      and again[0]["kind"] == st["kind"] and again[0]["brief"] == st["brief"], steps)
check("the team chat says in one line that the job carries on", any("khởi động lại" in x and "tự làm tiếp" in x for x in system_notes(ss, T)),
      system_notes(ss, T))
run(r.resume_jobs(rep["resumed"]))
check("and the job runs to its end with no press from the owner", ts.get_task(task)["status"] == "done"
      and any(c["agent_key"] == st["agent_key"] and c["role"] == "work" for c in fake.calls), ts.get_task(task)["status"])

# ---------- a clean stop: the turn settled itself, the step was left running ----------
ss, ts, tm, fake, r, T = world("clean")
task, st, tu = cut_job(ts, tm, r, T, "Dịch bài", 2)
r._settle_turn(tu, "interrupted")
tm.release_busy(st["agent_key"], tu)
check("setup: no open turn, the step still says running", not tm.open_turns() and tm.step(st["step_id"])["status"] == "running")
rep = r.recover()
check("a step left running by a clean stop is picked up the same way", task in rep["resumed"]
      and tm.step(st["step_id"])["status"] == "interrupted" and [s["status"] for s in tm.steps(task)].count("queued") == 1, tm.steps(task))

# ---------- an outside action whose fate is unknown: stop and ask ----------
ss, ts, tm, fake, r, T = world("outside")
task, st, tu = cut_job(ts, tm, r, T, "Gửi báo giá", 3)
key = TR.once_key(task, tm.step(st["step_id"]))


async def hang(args):
    raise asyncio.CancelledError()


async def send_then_die():
    tok = turn_context.bind(turn_context.make("team", chat_id=T["team_id"], job=key))
    try:
        await once_ledger.run("zalo_send_message", {"threadId": "42", "message": "Báo giá"}, hang)
    except asyncio.CancelledError:
        pass
    finally:
        turn_context.reset(tok)

run(send_then_die())
check("setup: the ledger holds one uncertain outside action for this step", len(once_ledger.unknowns(key)) == 1, once_ledger.unknowns(key))
fake.calls.clear()
rep = r.recover()
t = ts.get_task(task)
check("the job stops and asks instead of risking a second send", task in rep["blocked"] and t["status"] == "team_blocked"
      and t["block_kind"] == "interrupted" and "ra ngoài" in t["block_reason"] and fake.calls == [], t)
check("no new step was queued behind the owner's back", not [s for s in tm.steps(task) if s["status"] == "queued"], tm.steps(task))
check("the once key is the same for a retry of the step and different for another step",
      TR.once_key(task, dict(tm.step(st["step_id"]), step_id="other")) == key
      and TR.once_key(task, dict(tm.step(st["step_id"]), brief="việc khác")) != key and key.startswith(f"team:{task}:"))

# ---------- a restart loop: the third cut of the same step asks ----------
ss, ts, tm, fake, r, T = world("loop")
task, st, tu = cut_job(ts, tm, r, T, "Tổng hợp số liệu", 4)
for n in range(TR.RESTART_RESUME_MAX):
    rep = r.recover()
    nxt = tm.next_queued_step(task)
    check(f"cut {n + 1}: carries on by itself", task in rep["resumed"] and nxt is not None, rep)
    tm.claim_step(nxt["step_id"])
    tu = tm.reserve_turn(T["team_id"], task, nxt["step_id"], nxt["agent_key"], "work")
    tm.mark_engine(tu, "fake", "fake-model")
rep = r.recover()
t = ts.get_task(task)
check("one cut more than the limit stops the job with the reason", task in rep["blocked"] and t["block_kind"] == "interrupted"
      and str(TR.RESTART_RESUME_MAX + 1) in t["block_reason"], t)
check("Continue still works on such a job", r.unblock(task, "retry") and ts.get_task(task)["status"] != "team_blocked")

# ---------- switched off: the old behaviour ----------
ss, ts, tm, fake, r, T = world("off")
task, st, tu = cut_job(ts, tm, r, T, "Soạn email", 5)
os.environ["JAVIS_RESUME_AFTER_RESTART"] = "0"
try:
    rep = r.recover()
finally:
    os.environ.pop("JAVIS_RESUME_AFTER_RESTART", None)
check("JAVIS_RESUME_AFTER_RESTART=0: the job waits for the owner as before", task in rep["blocked"] and rep["replies"] == []
      and ts.get_task(task)["block_kind"] == "interrupted" and not [s for s in tm.steps(task) if s["status"] == "queued"], rep)

# ---------- a chat reply cut by the restart answers again ----------
ss, ts, tm, fake, r, T = world("reply")
sub = r.submit(T["team_id"], "Chào cả nhóm", client_msg_id="hello")
mid = sub["message_id"]
r.started_at = r.started_at + 5      # the reply above belongs to the "old" process
rep = r.recover()
check("the cut reply is handed back to be answered again", rep["replies"] == [{"team_id": T["team_id"], "message_id": mid, "agent_key": "ag_lan"}], rep)
check("until then its line says the restart cut it", [x["reason"] for x in tm.replies_of(T["team_id"], mid)] == ["restart"])
run(r.retry_cut_replies(rep["replies"]))
row = tm.replies_of(T["team_id"], mid)[0]
check("the leader answers without the owner pressing Retry", row["status"] == "done"
      and any(c["agent_key"] == "ag_lan" and c["role"] == "leader_reply" for c in fake.calls), row)
check("a reply that is gone meanwhile is skipped, not raised", run(r.retry_cut_replies([{"team_id": "tm_none", "message_id": 1, "agent_key": "ag_lan"}])) is None)

if fails:
    print("\nFAILED " + str(len(fails)))
    raise SystemExit(1)
print("\nALL OK")
