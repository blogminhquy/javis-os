"""One team runs several jobs at once when they belong to different assistants (2026-11-12).

    python tests/run.py team_parallel_jobs

A customer: "việc nó chạy tuần tự trong khi 2 agent 2 việc khác nhau có thể chạy song song, chỉ tuần tự khi thằng này
làm xong có kết quả rồi mới tới thằng kia". A team ran one job at a time (a server limit), so a job for Minh waited for
a job for Hoa to end.

- Up to three jobs of one team run together, each with a different assistant in charge.
- Two jobs of the same assistant keep their order. Two jobs the leader coordinates do too.
- A job worded as an order ("sau khi ... xong") waits for everything before it, and nothing starts ahead of it.
- JAVIS_TEAM_JOBS=1 gives one job at a time back. Other teams still get their place in the pool.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

TEMP = Path(tempfile.mkdtemp(prefix="javis-team-parallel-jobs-"))
os.environ.setdefault("JAVIS_STATE_DIR", str(TEMP / "state"))
(TEMP / "state").mkdir(exist_ok=True)

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []
WAIT = 10.0


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra != "" and not cond else ""))
    if not cond:
        fails.append(name)


SLUGS = ("lan", "minh", "hoa", "tu", "an")


class Fake:
    """A stand-in engine: per (assistant, role) a queue of answers; an async function is awaited with the request."""

    def __init__(self):
        self.script, self.order = {}, []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run_(req):
            self.order.append((agent_key, role))
            q = self.script.get((agent_key, role)) or []
            ans = q.pop(0) if q else f"{agent_key} {role} xong"
            if callable(ans):
                ans = await ans(req)
            return {"text": ans}
        return "aux", "fake-model", run_


_n = [0]


def world(label, members=SLUGS, **kw):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()

    def agent_info(root, key):
        slug = key[3:]
        return {"slug": slug, "name": slug.capitalize(), "system": slug, "model": "", "model_provider": ""} if slug in SLUGS else None

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info, **kw)

    def new_team(name, mem=members, leader="ag_lan"):
        tid = team_store.new_team_id()
        sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
        tm.create_team(str(d), name, "", sid, team_id=tid)
        for s in mem:
            tm.add_member(tid, f"ag_{s}", s)
        if leader:
            tm.set_leader(tid, leader)
        return tm.get(tid)

    return r, tm, ts, fake, new_team(label), new_team


def job(r, t, text, who=None, cid=None):
    """A job for `who` (an assistant key), or for the leader to plan when `who` is None. Returns its task id."""
    sub = r.submit(t["team_id"], text, mentions=[who] if who else [], as_job=True, client_msg_id=cid or text)
    return sub["task_id"]


def running(ts, t):
    return [x["id"] for x in ts.team_queue(t["team_id"])["running"]]


def waiting(ts, t):
    return [x["id"] for x in ts.team_queue(t["team_id"])["waiting"]]


def together(fake, a, b):
    """Make the work turns of assistants `a` and `b` finish only if both are in flight at the same time."""
    ev = {a: asyncio.Event(), b: asyncio.Event()}

    def gate(me, other):
        async def answer(req):
            ev[me].set()
            await asyncio.wait_for(ev[other].wait(), WAIT)
            return f"{me} xong"
        return answer
    fake.say(a, "work", gate(a, b))
    fake.say(b, "work", gate(b, a))


# ───── two assistants, two jobs: at the same time ─────
r, tm, ts, fake, T, _ = world("hai-nguoi")
j1, j2 = job(r, T, "Viết bài quảng cáo", "ag_minh"), job(r, T, "Thiết kế banner", "ag_hoa")


async def both():
    together(fake, "ag_minh", "ag_hoa")
    got = await r.dispatch_once(wait=False)
    now = running(ts, T)
    await r.wait_jobs()
    return got, now

got, now = asyncio.run(both())
check("two jobs of two assistants are both taken by one pass of the dispatcher", sorted(got) == sorted([j1, j2]), got)
check("and both are running at that moment", sorted(now) == sorted([j1, j2]), now)
check("each finished (each waited for the other to be in flight, so they did overlap)",
      ts.get_task(j1)["status"] == "done" and ts.get_task(j2)["status"] == "done",
      (ts.get_task(j1)["status"], ts.get_task(j2)["status"], ts.get_task(j1).get("block_reason")))

# ───── two jobs of the same assistant keep their order; a job of another one does not wait behind them ─────
r, tm, ts, fake, T, _ = world("cung-nguoi")
a1, a2, b1 = job(r, T, "Minh việc 1", "ag_minh"), job(r, T, "Minh việc 2", "ag_minh"), job(r, T, "Hoa việc 1", "ag_hoa")


async def same():
    got = await r.dispatch_once(wait=False)
    now, wait_ = running(ts, T), waiting(ts, T)
    again = await r.dispatch_once(wait=False)
    await r.wait_jobs()
    after = await r.dispatch_once(wait=False)
    await r.wait_jobs()
    return got, now, wait_, again, after

got, now, wait_, again, after = asyncio.run(same())
check("Minh's first job and Hoa's job start together; Minh's second job waits", sorted(now) == sorted([a1, b1]) and wait_ == [a2], (now, wait_))
check("another pass while they run opens nothing more", again == [], again)
check("Minh's second job starts once his first is over", after == [a2] and ts.get_task(a2)["status"] == "done", (after, ts.get_task(a2)["status"]))

# ───── a job worded as an order waits for everything before it, and nothing jumps ahead of it ─────
r, tm, ts, fake, T, _ = world("thu-tu")
s1 = job(r, T, "Nghiên cứu đối thủ", "ag_minh")
s2 = job(r, T, "Sau khi nghiên cứu xong thì viết bài theo kết quả đó", "ag_hoa")
s3 = job(r, T, "Chụp ảnh sản phẩm", "ag_tu")


async def ordered():
    await r.dispatch_once(wait=False)
    first = running(ts, T)
    await r.wait_jobs()
    await r.dispatch_once(wait=False)
    second = running(ts, T)
    await r.wait_jobs()
    await r.dispatch_once(wait=False)
    await r.wait_jobs()
    return first, second

first, second = asyncio.run(ordered())
check("the job that asks to come after waits, and the job behind it does not start ahead of it", first == [s1], first)
check("once the first is over, the ordered job runs, with the next one beside it", sorted(second) == sorted([s2, s3]), second)
check("all three end", all(ts.get_task(x)["status"] == "done" for x in (s1, s2, s3)))

# ───── at most three at once ─────
r, tm, ts, fake, T, _ = world("toi-da-ba")
four = [job(r, T, f"Việc của {s}", f"ag_{s}") for s in ("minh", "hoa", "tu", "an")]


async def capped():
    got = await r.dispatch_once(wait=False)
    now = running(ts, T)
    await r.wait_jobs()
    rest = await r.dispatch_once(wait=False)
    await r.wait_jobs()
    return got, now, rest

got, now, rest = asyncio.run(capped())
check("four jobs of four assistants: three run, the fourth waits", len(now) == 3 and sorted(now) == sorted(four[:3]), now)
check("the fourth runs when a place frees", rest == [four[3]] and ts.get_task(four[3])["status"] == "done", rest)
check("the limits table says three", {x["key"]: x["value"] for x in r.authority_view(T["team_id"]).get("limits") or []}.get("running_jobs") == 3)

# ───── jobs the leader coordinates: one at a time; beside a job given to a member: together ─────
r, tm, ts, fake, T, _ = world("dieu-phoi")
l1, l2, m1 = job(r, T, "Lên kế hoạch tuần"), job(r, T, "Lên kế hoạch tháng"), job(r, T, "Dọn file", "ag_tu")


async def led():
    await r.dispatch_once(wait=False)
    now = running(ts, T)
    await r.wait_jobs()
    return now

now = asyncio.run(led())
check("two jobs the leader coordinates do not run together, a member's own job runs beside the first",
      sorted(now) == sorted([l1, m1]), now)

# ───── JAVIS_TEAM_JOBS=1: one job at a time, as before ─────
os.environ["JAVIS_TEAM_JOBS"] = "1"
try:
    r, tm, ts, fake, T, _ = world("mot-viec")
finally:
    os.environ.pop("JAVIS_TEAM_JOBS", None)
o1, o2 = job(r, T, "Việc A", "ag_minh"), job(r, T, "Việc B", "ag_hoa")


async def one():
    await r.dispatch_once(wait=False)
    now = running(ts, T)
    await r.wait_jobs()
    return now

check("JAVIS_TEAM_JOBS=1 gives one job at a time back", asyncio.run(one()) == [o1])

# ───── the pool is counted in teams: a busy team does not take the other team's place ─────
r, tm, ts, fake, T, new_team = world("hai-team", max_parallel_teams=2)
T2 = new_team("team-hai")
p = [job(r, T, f"A {s}", f"ag_{s}") for s in ("minh", "hoa", "tu")]
p2 = job(r, T2, "B minh", "ag_minh", cid="b-minh")


async def pool():
    await r.dispatch_once(wait=False)
    now = (running(ts, T), running(ts, T2))
    await r.wait_jobs()
    return now

now = asyncio.run(pool())
check("a team with three running jobs leaves the second team its place (pool of 2 teams)",
      sorted(now[0]) == sorted(p) and now[1] == [p2], now)

# ───── the store: a named job is claimed only while it waits, in its own team, under the limit ─────
r, tm, ts, fake, T, new_team = world("kho")
T2 = new_team("kho-hai")
k1, k2, k3 = job(r, T, "K1", "ag_minh"), job(r, T, "K2", "ag_hoa"), job(r, T, "K3", "ag_tu")
check("the named job is taken, not the head", (ts.claim_team_next(T["team_id"], "w", max_running=2, task_id=k2) or {}).get("id") == k2)
check("a job that already runs is not taken twice", ts.claim_team_next(T["team_id"], "w", max_running=2, task_id=k2) is None)
check("a job of another team is not taken", ts.claim_team_next(T2["team_id"], "w", max_running=2, task_id=k1) is None)
check("without a name: the head, as before", (ts.claim_team_next(T["team_id"], "w", max_running=2) or {}).get("id") == k1)
check("at the limit nothing more is taken", ts.claim_team_next(T["team_id"], "w", max_running=2, task_id=k3) is None)

print("")
if fails:
    print(f"RED: {len(fails)}")
    sys.exit(1)
print("All green.")
