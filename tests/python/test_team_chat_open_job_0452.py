"""A member answering the owner opens the job from the team chat (0.452.0).

    python tests/run.py team_chat_open_job_0452 -v

Owner, 04/11/2026: members of a team could not get each other working from the chat; the leader could only propose a
job and the owner had to press Create job. "Để tạo thành 1 loop hoàn chỉnh mà hiệu quả": whoever answers the owner now
opens the job asked for, and the leader plans and assigns it like any job. Real stores and runner on temporary SQLite,
a scripted fake engine. No model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-autojob-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-autojob-w-"))

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


AGENTS = {"lan": "Lan", "minh": "Minh"}


class Fake:
    def __init__(self):
        self.script = {}
        self.calls = []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run_(req):
            self.calls.append(req)
            q = self.script.get((agent_key, role)) or []
            return {"text": q.pop(0) if q else f"{agent_key} {role} xong"}
        return "aux", "fake-model", run_


_n = [0]


def world(label):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()

    def agent_info(root, key):
        slug = key[3:] if key.startswith("ag_") else ""
        if slug not in AGENTS:
            return None
        return {"slug": slug, "name": AGENTS[slug], "system": f"Bạn là {AGENTS[slug]}.", "model": "", "model_provider": ""}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info)
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
    tm.create_team(str(d), label, "", sid, team_id=tid)
    for s in AGENTS:
        tm.add_member(tid, f"ag_{s}", s)
    tm.set_leader(tid, "ag_lan")
    return r, tm, ts, ss, fake, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


def reply(r, t, text, cid, mentions=None):
    return run(r.run_replies(r.submit(t["team_id"], text, client_msg_id=cid, mentions=mentions or [])))


def msgs(ss, t):
    return ss.get_team_messages_page(t["session_id"], limit=200)["messages"]


def jobs(ts, t):
    q = ts.team_queue(t["team_id"])
    return [x for k in ("running", "waiting", "blocked") for x in (q.get(k) or [])]


# ═════ the leader opens the job the owner asked for ═════
r, tm, ts, ss, fake, T = world("leader")
check("a new team may open 5 jobs a day from the chat", T["caps"]["auto_jobs"] == 5 and r._auto_jobs_left(T) == 5, T["caps"])
fake.say("ag_lan", "leader_reply", "Em mở việc ngay." + directive(op="open_job", title="Viết bài giới thiệu nước mắm",
                                                                   brief="Bài 500 chữ, giọng gần gũi"))
reply(r, T, "Viết giúp anh bài giới thiệu nước mắm", "c1")
lp = fake.calls[-1]["prompt"]
check("the leader's chat turn is told it can open the job itself", TR.AUTO_JOB_HINT in lp and "propose_job" not in lp, lp[-800:])
js = jobs(ts, T)
check("the leader's reply opens the job, no Create job press", len(js) == 1 and js[0]["title"] == "Viết bài giới thiệu nước mắm", js)
job = ts.get_task(js[0]["id"]) if js else {}
check("the job is coordinated by the leader and carries the brief", job.get("coordinator_key") == "ag_lan"
      and "500 chữ" in (job.get("intent") or ""), job)
sysm = [m for m in msgs(ss, T) if m["author_kind"] == "system" and (m.get("meta") or {}).get("kind") == "job_opened"]
check("the chat says who opened which job", sysm and "Lan" in sysm[-1]["content"] and "nước mắm" in sysm[-1]["content"]
      and sysm[-1].get("task_id") == js[0]["id"], [m["content"] for m in msgs(ss, T)])
check("it counts against today's allowance", r._auto_jobs_left(tm.get(T["team_id"])) == 4)

# ═════ a member called with @ opens the job too, still coordinated by the leader ═════
fake.say("ag_minh", "member_reply", "Để em làm." + directive(op="open_job", title="Sửa nút Mua ngay"))
reply(r, T, "@Minh sửa nút Mua ngay giúp anh", "c2", mentions=["ag_minh"])
mp = fake.calls[-1]["prompt"]
check("a member's chat turn is told it can open the job too", TR.AUTO_JOB_HINT in mp, mp[-600:])
js = jobs(ts, T)
mine = [x for x in js if x["title"] == "Sửa nút Mua ngay"]
check("a member's reply opens the job", len(mine) == 1, [x["title"] for x in js])
check("and the leader coordinates it: members never hand work to each other directly",
      mine and ts.get_task(mine[0]["id"]).get("coordinator_key") == "ag_lan")

# ═════ one job per owner message ═════
before = len(jobs(ts, T))
fake.say("ag_lan", "leader_reply", "Mở." + directive(op="open_job", title="Một") + directive(op="open_job", title="Hai"))
reply(r, T, "Làm hai việc", "c3")
check("two open_job in one answer to one message make one job", len(jobs(ts, T)) == before + 1, [x["title"] for x in jobs(ts, T)])

# ═════ the whole loop: chat -> job -> plan -> work -> synthesize -> done, result back in the chat ═════
r, tm, ts, ss, fake, T = world("loop")
fake.say("ag_lan", "leader_reply", "Em mở việc." + directive(op="open_job", title="Lên dàn ý bài blog"))
fake.say("ag_lan", "plan", "Minh làm dàn ý." + directive(op="assign", id="a", agent="ag_minh", brief="Dàn ý 5 ý"))
fake.say("ag_minh", "work", "Dàn ý: 1, 2, 3, 4, 5.")
reply(r, T, "Lên dàn ý bài blog về bữa cơm gia đình", "c1")
for _ in range(6):
    run(r.dispatch_once())
    if all(ts.get_task(x["id"])["status"] == "done" for x in jobs(ts, T)) and not jobs(ts, T):
        break
done = [t for t in ts.team_history(T["team_id"], 10) if t["title"] == "Lên dàn ý bài blog"]
roles = [c["role"] for c in fake.calls]
check("a job opened from the chat runs the whole loop to done", done and done[0]["status"] == "done", (roles, jobs(ts, T)))
check("through the leader's plan, then the member's work (one part: its result is the job's result, no summary turn)",
      {"plan", "work"} <= set(roles) and roles.index("plan") < roles.index("work"), roles)
res = [m for m in msgs(ss, T) if (m.get("meta") or {}).get("job_result")]
check("and the result lands back in the team chat", res and "dàn ý" in res[-1]["content"].lower(), [m["content"] for m in msgs(ss, T)])

# ═════ the daily allowance ═════
r, tm, ts, ss, fake, T = world("cap")
tm.set_caps(T["team_id"], {"auto_jobs": 1})
T = tm.get(T["team_id"])
fake.say("ag_lan", "leader_reply", "Mở." + directive(op="open_job", title="Việc một"),
         "Mở tiếp." + directive(op="open_job", title="Việc hai"))
reply(r, T, "Việc một", "c1")
reply(r, T, "Việc hai", "c2")
titles = [x["title"] for x in jobs(ts, T)]
check("past the daily allowance no more jobs are opened", titles == ["Việc một"], titles)
last = [m for m in msgs(ss, T) if m["author_kind"] == "agent"][-1]
check("and the answer says why", any("đủ số việc" in n for n in (last.get("meta") or {}).get("notes") or []),
      (last.get("meta") or {}).get("notes"))
check("with nothing left the prompt goes back to proposing", "propose_job" in fake.calls[-1]["prompt"]
      or TR.AUTO_JOB_HINT not in fake.calls[-1]["prompt"])

# ═════ off: back to the old behaviour ═════
r, tm, ts, ss, fake, T = world("off")
tm.set_caps(T["team_id"], {"auto_jobs": 0})
T = tm.get(T["team_id"])
fake.say("ag_lan", "leader_reply", "Mở." + directive(op="open_job", title="Không được mở"))
reply(r, T, "Làm giúp anh", "c1")
check("0 turns it off: the leader is told to propose, not open", "propose_job" in fake.calls[-1]["prompt"]
      and TR.AUTO_JOB_HINT not in fake.calls[-1]["prompt"])
check("and an open_job in the answer opens nothing", jobs(ts, T) == [])
try:
    tm.set_caps(T["team_id"], {"auto_jobs": 51})
    check("the allowance is at most 50 a day", False)
except team_store.TeamError:
    check("the allowance is at most 50 a day", True)
check("the owner can change it from the team limits", "auto_jobs" in team_store.OWNER_CAPS)

# ═════ only an answer to the owner opens a job ═════
r, tm, ts, ss, fake, T = world("roles")
notes = []
with r.accept_lock:
    r._chat_open_job(T["team_id"], "ag_minh", {"op": "open_job", "title": "X"}, notes, None)
check("without an owner message to answer, no job", jobs(ts, T) == [] and notes, notes)
check("a volunteer turn (nobody called it) is not a reply role", "member_volunteer" not in TR.REPLY_ROLES)

# ═════ the dashboard has the field ═════
tjs = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
vi = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
check("the team limits form has the daily allowance", '"auto_jobs"' in tjs.split("var CAP_FIELDS", 1)[1][:300]
      and "teams.cap.auto_jobs" in tjs and vi.get("teams.cap.auto_jobs") and en.get("teams.cap.auto_jobs"))

print("\n" + ("XANH" if not fails else f"ĐỎ: {len(fails)} lỗi"))
raise SystemExit(1 if fails else 0)
