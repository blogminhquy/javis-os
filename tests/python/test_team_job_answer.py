"""19/11/2026: the owner answers a team job stopped on a step, instead of only pressing Retry.

    python tests/run.py team_job_answer

The owner: "một số việc chờ như này không hỏi lại được cũng không tương tác được để làm rõ yêu cầu", "thử lại không
được thì chỉ có ấn X để tắt thôi". Retry ran the same brief again and stopped again; the answer now reaches the member.
Fake engines only, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-answer-")
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_vy": ("vy", "Vy")}


class Fake:
    def __init__(self):
        self.script = {}
        self.calls = []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run(req):
            self.calls.append(dict(req, agent=agent_key))
            queue = self.script.get((agent_key, role)) or []
            ans = queue.pop(0) if queue else f"{agent_key} {role} xong"
            return {"text": ans, "tokens_in": 1, "tokens_out": 1}
        return "fake", "fake-model", run


def world(name):
    d = STATE / name
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "sessions.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()

    def agent_info(brain, key):
        slug, nm = AGENTS[key]
        return {"slug": slug, "name": nm, "system": f"Bạn là {nm}."}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info,
                      publish=lambda ev: None, notify=lambda team_id, text: None)
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "mô tả", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, "ag_lan")
    return ss, ts, tm, fake, r, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


def messages(ss, sid):
    return ss.get_team_messages_page(sid, limit=100)["messages"]


ss, ts, tm, fake, r, T = world("answer")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_vy", brief="Kiểm chứng bài v2"))
fake.say("ag_vy", "work", "Chưa có v2." + directive(op="done", outcome="failed", summary="V1 chưa đạt, chưa có v2"))
j = r.submit(T["team_id"], "Viết 2 bài", as_job=True, client_msg_id="p1")
run(r.dispatch_once(wait=True))
t = ts.get_task(j["task_id"])
check("setup: the member's report stops the job for the owner", t["status"] == "team_blocked" and t["block_kind"] == "failed",
      (t["status"], t["block_kind"]))

check("an empty answer changes nothing", r.answer_blocked(j["task_id"], "   ") is None
      and ts.get_task(j["task_id"])["status"] == "team_blocked")

before = len(tm.steps(j["task_id"]))
res = r.answer_blocked(j["task_id"], "Dùng bản v1, bỏ qua kiểm chứng v2", text="> Việc dừng: V1 chưa đạt\n\nDùng bản v1, "
                       "bỏ qua kiểm chứng v2", client_msg_id="ans1")
check("the answer is taken", res and res["created"] is True, res)
t = ts.get_task(j["task_id"])
check("the job goes back to the queue", t["status"] == "team_queued", t["status"])
last_msg = messages(ss, T["session_id"])[-1]
check("the answer is the owner's message in the chat, linked to the job",
      last_msg["author_kind"] == "owner" and last_msg["task_id"] == j["task_id"] and last_msg["id"] == res["message_id"]
      and last_msg["content"].startswith("> Việc dừng") and (last_msg.get("meta") or {}).get("kind") == "job_answer"
      and (last_msg.get("meta") or {}).get("agent_key") == "ag_vy", last_msg)
st = tm.steps(j["task_id"])
new = st[-1]
check("one new step, same member and kind as the stopped one", len(st) == before + 1 and new["agent_key"] == "ag_vy"
      and new["kind"] == "work" and new["status"] == "queued", [(s["agent_key"], s["kind"], s["status"]) for s in st])
check("its brief carries the old brief, why it stopped and the answer",
      new["brief"].startswith("Kiểm chứng bài v2") and "V1 chưa đạt, chưa có v2" in new["brief"]
      and "Dùng bản v1, bỏ qua kiểm chứng v2" in new["brief"], new["brief"])

again = r.answer_blocked(j["task_id"], "Dùng bản v1, bỏ qua kiểm chứng v2", client_msg_id="ans1")
check("the same answer sent twice (lost connection) returns the first message, no second step",
      again == {"message_id": res["message_id"], "created": False} and len(tm.steps(j["task_id"])) == before + 1, again)
check("a new answer once the job runs again is refused", r.answer_blocked(j["task_id"], "khác", client_msg_id="ans2") is None)

fake.calls.clear()
fake.say("ag_vy", "work", "Đã kiểm chứng trên v1." + directive(op="done", summary="Đạt trên v1"))
run(r.dispatch_once(wait=True))
work = [c for c in fake.calls if c["agent"] == "ag_vy"]
check("the member's next turn reads the owner's answer", work and "Dùng bản v1, bỏ qua kiểm chứng v2" in work[0]["prompt"],
      [c.get("role") for c in fake.calls])
check("the job finishes", ts.get_task(j["task_id"])["status"] == "done", ts.get_task(j["task_id"])["status"])

# A stop that waits for another button never takes an answer here.
ss, ts, tm, fake, r, T = world("cap")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_vy", brief="Phần A"))
fake.say("ag_vy", "work", "Hỏng." + directive(op="done", outcome="failed", summary="Thiếu dữ liệu"))
j2 = r.submit(T["team_id"], "Một việc", as_job=True, client_msg_id="q1")
run(r.dispatch_once(wait=True))
ts.team_reblock(j2["task_id"], "cap_reached", "Hết lượt")
n = len(messages(ss, T["session_id"]))
check("cap_reached: no answer, nothing posted", r.answer_blocked(j2["task_id"], "làm tiếp", client_msg_id="x1") is None
      and len(messages(ss, T["session_id"])) == n and ts.get_task(j2["task_id"])["status"] == "team_blocked")
check("an unknown job: no answer", r.answer_blocked("t_nope", "x") is None)

# The route.
api_src = (Path(SERVER) / "team_api.py").read_text(encoding="utf-8")
check("route POST /teams/{team_id}/tasks/{task_id}/answer calls answer_blocked and wakes the runner",
      '@app.post("/teams/{team_id}/tasks/{task_id}/answer")' in api_src
      and "api.runner().answer_blocked(task_id, answer, text=text, client_msg_id=cmid)" in api_src)

raise SystemExit(1 if fails else 0)
