"""0.437.0: a team plan's parts declare which parts they wait for (`id` / `after`).

    python tests/run.py team_step_deps

Fake engines only, no model call. Independent parts run together, a part waits only for the parts it names and gets
only their results as inputs, retries and help continuations keep the part's label, and an old store gains the columns.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sqlite3
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-deps-")
os.environ.pop("JAVIS_TEAM_AUTO_RETRIES", None)
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra!r}" if not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh"), "ag_hoa": ("hoa", "Hoa"), "ag_tu": ("tu", "Tú")}


class Fake:
    def __init__(self):
        self.script = {}
        self.calls = []
        self.live = 0
        self.peak = 0
        self.together = set()   # agents whose next Work turns must overlap (proves they run in one wave)
        self.started = set()
        self.ready = None

    def expect_together(self, *agents):
        self.together, self.started, self.ready = set(agents), set(), asyncio.Event()

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run(req):
            self.calls.append(req)
            self.live += 1
            self.peak = max(self.peak, self.live)
            try:
                if role == "work" and agent_key in self.together:
                    self.started.add(agent_key)
                    if self.started == self.together:
                        self.ready.set()
                    # A timeout reports broken concurrency without hanging the suite.
                    try:
                        await asyncio.wait_for(self.ready.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
                    self.together.discard(agent_key)
                else:
                    await asyncio.sleep(0)
                queue = self.script.get((agent_key, role)) or []
                ans = queue.pop(0) if queue else f"{agent_key} {role} xong"
                if isinstance(ans, Exception):
                    raise ans
            finally:
                self.live -= 1
            return {"text": ans, "tokens_in": 1, "tokens_out": 1}
        return "fake", "fake-model", run

    def order(self):
        return [(c["agent_key"], c["role"]) for c in self.calls]

    def call(self, agent, role="work", n=0):
        got = [c for c in self.calls if c["agent_key"] == agent and c["role"] == role]
        return got[n] if len(got) > n else {"prompt": ""}


def inputs_of(req):
    """The Inputs part of a step prompt (the history window above it may mention anything)."""
    p = req.get("prompt") or ""
    i = p.find("Đầu vào:")
    return p[i:] if i >= 0 else ""


def world(name, leader="ag_lan"):
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
                      publish=lambda e: None, notify=lambda team_id, text: inbox.append(text))
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "mô tả", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, leader)
    return ss, ts, tm, fake, r, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


# ---------- plan parsing ----------
notes = []
earlier = []
for op in ({"id": "a"}, {"id": "b", "after": ["a"]}, {"after": [1, "b", "zz", 9, True]}, {"id": "a", "after": "c"}):
    part, after = TR.TeamRunner._plan_part(op, earlier, notes)
    earlier.append({"part": part, "after": after})
check("labels: given id, then position for a missing one, a duplicate id gets its position",
      [e["part"] for e in earlier] == ["a", "b", "p3", "p4"], earlier)
check("after: a label above, a 1-based position above", earlier[1]["after"] == ["a"] and earlier[2]["after"] == ["a", "b"],
      earlier)
check("after: unknown, out of range, forward and boolean refs are dropped with a note",
      earlier[3]["after"] == [] and len(notes) == 4, notes)

# ---------- A and B together, C waits for both ----------
ss, ts, tm, fake, r, T = world("join")
fake.expect_together("ag_minh", "ag_hoa")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", id="a", agent="ag_minh", brief="Nghiên cứu đối thủ")
         + directive(op="assign", id="b", agent="ag_hoa", brief="Lấy số liệu bán hàng")
         + directive(op="assign", id="c", agent="ag_tu", brief="Viết kế hoạch", after=["a", "b"]))
fake.say("ag_minh", "work", "ĐỐI THỦ: X giảm giá")
fake.say("ag_hoa", "work", "SỐ LIỆU: 120 đơn")
job = r.submit(T["team_id"], "Kế hoạch tháng", as_job=True, client_msg_id="j1")
run(r.dispatch_once(wait=True))
order = fake.order()
check("join: the two independent parts run in one wave", fake.peak == 2
      and sorted(order[1:3]) == [("ag_hoa", "work"), ("ag_minh", "work")], (fake.peak, order))
c_in = inputs_of(fake.call("ag_tu"))
check("join: C runs after both, with both results as inputs", order[3:4] == [("ag_tu", "work")]
      and "ĐỐI THỦ" in c_in and "SỐ LIỆU" in c_in, (order, c_in[-400:]))
check("join: the summary comes last and the job is done", order[-1] == ("ag_lan", "synthesize")
      and ts.get_task(job["task_id"])["status"] == "done", order)
check("join: no step left held", not [s for s in tm.steps(job["task_id"]) if s["status"] == "held"])

# ---------- B and C both wait only for A: they run together, each with A only ----------
ss, ts, tm, fake, r, T = world("fan")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", id="a", agent="ag_minh", brief="Lấy số liệu")
         + directive(op="assign", id="b", agent="ag_hoa", brief="Viết bài từ số liệu", after=["a"])
         + directive(op="assign", id="c", agent="ag_tu", brief="Làm ảnh từ số liệu", after=["a"]))
fake.say("ag_minh", "work", "SỐ LIỆU A")
fake.say("ag_hoa", "work", "BÀI B")
fake.expect_together("ag_hoa", "ag_tu")
job = r.submit(T["team_id"], "Bài và ảnh", as_job=True, client_msg_id="j2")
run(r.dispatch_once(wait=True))
order = fake.order()
check("fan: A first, alone", order[1:2] == [("ag_minh", "work")], order)
check("fan: B and C start together once A is done (a `wait` plan would run them one by one)",
      fake.peak == 2 and sorted(order[2:4]) == [("ag_hoa", "work"), ("ag_tu", "work")], (fake.peak, order))
check("fan: each gets A's result", "SỐ LIỆU A" in inputs_of(fake.call("ag_hoa"))
      and "SỐ LIỆU A" in inputs_of(fake.call("ag_tu")))
check("fan: a part's inputs hold only what it waited for (C does not read B)", "BÀI B" not in inputs_of(fake.call("ag_tu")))
check("fan: done", ts.get_task(job["task_id"])["status"] == "done")

# ---------- a retried part keeps its label, so the part waiting for it still starts ----------
ss, ts, tm, fake, r, T = world("retry")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", id="a", agent="ag_minh", brief="Lấy số liệu")
         + directive(op="assign", id="b", agent="ag_hoa", brief="Viết báo cáo", after=["a"]))
fake.say("ag_minh", "work", RuntimeError("engine hỏng"), "SỐ LIỆU sau khi sửa")
job = r.submit(T["team_id"], "Báo cáo", as_job=True, client_msg_id="j3")
run(r.dispatch_once(wait=True))
check("retry: A fails, the job stops for the owner and B is still held",
      ts.get_task(job["task_id"])["block_kind"] == "failed"
      and [s["status"] for s in tm.steps(job["task_id"]) if s["agent_key"] == "ag_hoa"] == ["held"])
r.unblock(job["task_id"], "retry")
run(r.dispatch_once(wait=True))
check("retry: the new A step keeps label 'a'", [s["part"] for s in tm.steps(job["task_id"])
                                                if s["agent_key"] == "ag_minh"] == ["a", "a"])
check("retry: B runs with the retried result and the job finishes",
      "SỐ LIỆU sau khi sửa" in inputs_of(fake.call("ag_hoa")) and ts.get_task(job["task_id"])["status"] == "done")

# ---------- a part that asked for help keeps its label through the continuation ----------
ss, ts, tm, fake, r, T = world("help")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", id="a", agent="ag_minh", brief="Tính giá vốn")
         + directive(op="assign", id="b", agent="ag_hoa", brief="Đặt giá bán", after=["a"]))
fake.say("ag_minh", "work", "Cần số nhập hàng." + directive(op="request_help", agent="ag_tu", question="Giá nhập?"),
         "GIÁ VỐN 50k")
fake.say("ag_tu", "help", "Nhập 40k")
job = r.submit(T["team_id"], "Định giá", as_job=True, client_msg_id="j4")
run(r.dispatch_once(wait=True))
order = fake.order()
check("help: A asks Tú, A continues, then B", order[1:5] == [("ag_minh", "work"), ("ag_tu", "help"),
                                                         ("ag_minh", "work"), ("ag_hoa", "work")], order)
check("help: B reads A's final result", "GIÁ VỐN 50k" in inputs_of(fake.call("ag_hoa")))
check("help: done", ts.get_task(job["task_id"])["status"] == "done")

# ---------- store: release rules and the safety net ----------
ss, ts, tm, fake, r, T = world("store")
tid = "t_store"
a = tm.add_step(tid, T["team_id"], "work", "ag_minh", 1, "A", [], part="a")
b = tm.add_step(tid, T["team_id"], "work", "ag_hoa", 1, "B", [], part="b", after=["a"])
old = tm.add_step(tid, T["team_id"], "work", "ag_tu", 1, "old held", [], held=True)
check("store: a step with `after` is held and keeps its label", tm.step(b["step_id"])["status"] == "held"
      and tm.step(b["step_id"])["after"] == ["a"] and tm.step(old["step_id"])["after"] is None)
check("store: nothing released while A is not done", tm.release_ready_steps(tid, 1) == [])
tm.finish_step(a["step_id"], "done", 77, True)
check("store: other revision's result does not count", tm.release_ready_steps(tid, 2) == [])
got = tm.release_ready_steps(tid, 1)
check("store: B released with A's result as input", [s["step_id"] for s in got] == [b["step_id"]]
      and 77 in tm.step(b["step_id"])["input_refs"] and tm.step(b["step_id"])["status"] == "queued")
check("store: the old held step is left to the old rule", tm.step(old["step_id"])["status"] == "held")
c = tm.add_step(tid, T["team_id"], "work", "ag_lan", 1, "C", [], part="c", after=["zz"])
check("store: legacy_only skips a dependency step", tm.release_held_step(tid, [], legacy_only=True)["step_id"]
      == old["step_id"])
check("store: the safety net still releases it", tm.release_held_step(tid, [])["step_id"] == c["step_id"])

# ---------- an old store gains the two columns ----------
p = STATE / "old" / "team.sqlite3"
p.parent.mkdir()
tm_old = team_store.TeamStore(p)
with sqlite3.connect(p) as con:
    con.execute("ALTER TABLE team_steps DROP COLUMN after_json")
    con.execute("ALTER TABLE team_steps DROP COLUMN part")
    con.execute("INSERT INTO team_steps(step_id,task_id,team_id,seq,kind,agent_key,job_revision,brief,input_refs_json,"
                "status,created_at,updated_at) VALUES('st_old','t1','tm',1,'work','ag_minh',1,'x','[]','held',0,0)")
tm_new = team_store.TeamStore(p)
s_old = tm_new.step("st_old")
check("migration: an old held row reads with no label and the old meaning", s_old["part"] == ""
      and s_old["after"] is None and s_old["status"] == "held")
check("migration: new steps can be added", tm_new.add_step("t1", "tm", "work", "ag_hoa", 1, "y", [], part="a",
                                                          after=["b"])["after"] == ["b"])

# ---------- the plan prompt explains it ----------
plan_prompt = TR.TeamRunner._body_core(r, {"kind": "plan"}, {})
check("prompt: the leader is told about id, after and wait",
      '"after"' in plan_prompt and '"id"' in plan_prompt and '"wait": true' in plan_prompt)

raise SystemExit(1 if fails else 0)
