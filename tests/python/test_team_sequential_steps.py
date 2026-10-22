"""A Team job whose steps depend on each other runs them in order (customer report 0.270, Code 23).

    python tests/python/test_team_sequential_steps.py        (fake engines, scratch stores)

Report: a job with three steps (1 member A writes a proposal; 2 member B quotes it and names two gaps "only after step 1
is done"; 3 A answers) ran step 2 in the same wave as step 1, so B saw nothing; the leader's summary, posted one second
after B's corrected answer, still said step 2 was not done; step 3 never ran, yet the card said Done. Pinned here:
  1. `asks_sequential` reads ordering words in Vietnamese (with or without diacritics) and English, and leaves plain
     requests alone.
  2. A sequential request: every part after the first is held, runs only when everything before it is done, one at a
     time, with the earlier results as inputs; the summary comes last and sees every result.
  3. `"wait": true` on one assign holds that part even when the request has no ordering words; parts without it still
     run side by side.
  4. A member posting again after the results the summary read: the summary becomes evidence and the leader
     summarises once more with the newer message.
  5. A job with a step left to run is never marked done: it stops with the reason, and resuming runs what is left.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-seq-")
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_store  # noqa: E402
import team_runner as TR  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra!r}" if not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh"), "ag_hoa": ("hoa", "Hoa")}


class Fake:
    def __init__(self):
        self.script = {}
        self.calls = []
        self.live = 0
        self.peak = 0

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run(req):
            self.calls.append(req)
            self.live += 1
            self.peak = max(self.peak, self.live)
            try:
                await asyncio.sleep(0.02)
                queue = self.script.get((agent_key, role)) or []
                ans = queue.pop(0) if queue else f"{agent_key} {role} xong"
                if callable(ans):
                    ans = await ans(req)
            finally:
                self.live -= 1
            return {"text": ans, "tokens_in": 1, "tokens_out": 1}
        return "fake", "fake-model", run

    def order(self):
        return [(c["agent_key"], c["role"]) for c in self.calls]


def world(name, leader="ag_hoa"):
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
                      publish=lambda e: None, notify=lambda team_id, text: None)
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "mô tả", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, leader)
    return ss, ts, tm, fake, r, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


# ================================================================
# 1. Ordering words
# ================================================================
for text in ("Bước 2 chỉ làm sau khi bước 1 xong", "buoc 2 chi lam sau khi buoc 1 hoan thanh",
             "Làm lần lượt từng người", "Làm TUẦN TỰ nhé", "Step 2 only after step 1 is done",
             "Run the parts one after another", "Do them sequentially"):
    check(f"sequential: {text}", TR.asks_sequential(text))
for text in ("Soạn kế hoạch ra mắt", "Viết bài và làm ảnh", "In order to launch, write a post", "Sau khi đọc, tóm tắt"):
    check(f"not sequential: {text}", not TR.asks_sequential(text))

# ================================================================
# 2. The report's job: three steps in order
# ================================================================
ss, ts, tm, fake, r, T = world("report")
REQUEST = ("Bước 1: Lan viết một đề xuất ngắn. Bước 2: chỉ sau khi bước 1 xong, Minh trích đề xuất của Lan và nêu 2 chỗ "
           "hở. Bước 3: Lan trả lời 2 chỗ hở đó.")
fake.say("ag_hoa", "plan", "Chia ba bước." + directive(op="assign", agent="ag_lan", brief="Viết đề xuất")
         + directive(op="assign", agent="ag_minh", brief="Trích đề xuất của Lan, nêu 2 chỗ hở")
         + directive(op="assign", agent="ag_lan", brief="Trả lời 2 chỗ hở của Minh"))
fake.say("ag_lan", "work", "ĐỀ XUẤT: mở quầy thứ hai")


async def minh_answers(req):
    return ("Trích: 'mở quầy thứ hai'. Hở 1: chi phí. Hở 2: nhân sự." if "ĐỀ XUẤT: mở quầy thứ hai" in req["prompt"]
            else "Chưa thấy đề xuất nào của Lan")


async def lan_replies(req):
    return "TRẢ LỜI: chi phí và nhân sự đã có" if "Hở 2: nhân sự" in req["prompt"] else "Chưa thấy chỗ hở nào"


fake.say("ag_minh", "work", minh_answers)
fake.say("ag_lan", "work", lan_replies)
fake.say("ag_hoa", "synthesize", "TỔNG HỢP: đủ ba bước")
job = r.submit(T["team_id"], REQUEST, as_job=True, client_msg_id="j1")
run(r.dispatch_once(wait=True))
check("report: plan, step 1, step 2, step 3, then the summary, in that order",
      fake.order() == [("ag_hoa", "plan"), ("ag_lan", "work"), ("ag_minh", "work"), ("ag_lan", "work"),
                       ("ag_hoa", "synthesize")], fake.order())
check("report: never two turns at once", fake.peak == 1, fake.peak)
minh_prompt = fake.calls[2]["prompt"] if len(fake.calls) > 2 else ""
check("report: step 2 receives step 1's result as input", "ĐỀ XUẤT: mở quầy thứ hai" in minh_prompt, minh_prompt[-600:])
lan2_prompt = fake.calls[3]["prompt"] if len(fake.calls) > 3 else ""
check("report: step 3 receives step 2's result as input", "Hở 2: nhân sự" in lan2_prompt)
synth_prompt = fake.calls[4]["prompt"] if len(fake.calls) > 4 else ""
check("report: the summary sees all three results",
      all(x in synth_prompt for x in ("ĐỀ XUẤT: mở quầy", "Hở 2: nhân sự", "TRẢ LỜI: chi phí")))
task = ts.get_task(job["task_id"])
check("report: the job is done with the summary", task["status"] == "done" and "TỔNG HỢP" in task["result"], task["status"])
check("report: no step left held or queued",
      not [s for s in tm.steps(job["task_id"]) if s["status"] in team_store.STEP_OPEN])
check("report: the plan prompt explains wait and one block per step",
      '"wait": true' in fake.calls[0]["prompt"] and "kể cả khi cùng một người làm hai bước" in fake.calls[0]["prompt"])

# ================================================================
# 3. `wait` on one assign
# ================================================================
ss, ts, tm, fake, r, T = world("wait", leader="ag_lan")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="Viết nội dung")
         + directive(op="assign", agent="ag_hoa", brief="Làm ảnh")
         + directive(op="assign", agent="ag_lan", brief="Duyệt nội dung và ảnh", wait=True))
fake.say("ag_minh", "work", "NỘI DUNG xong")
fake.say("ag_hoa", "work", "ẢNH xong")
job = r.submit(T["team_id"], "Soạn bài ra mắt", as_job=True, client_msg_id="j1")
run(r.dispatch_once(wait=True))
order = fake.order()
check("wait: the two free parts still run in one wave", fake.peak == 2
      and sorted(order[1:3]) == [("ag_hoa", "work"), ("ag_minh", "work")], (fake.peak, order))
check("wait: the waiting part runs after both, with both results",
      order[3:4] == [("ag_lan", "work")] and "NỘI DUNG xong" in fake.calls[3]["prompt"]
      and "ẢNH xong" in fake.calls[3]["prompt"], order)
check("wait: then the summary, and the job is done", order[-1] == ("ag_lan", "synthesize")
      and ts.get_task(job["task_id"])["status"] == "done", order)

# ================================================================
# 4. A member posts again after the results the summary read
# ================================================================
ss, ts, tm, fake, r, T = world("stale", leader="ag_lan")
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="phần A")
         + directive(op="assign", agent="ag_hoa", brief="phần B"))
fake.say("ag_minh", "work", "Minh: phần A chưa đủ dữ liệu")
fake.say("ag_hoa", "work", "Hoa: phần B xong")


async def first_summary(req):
    # While the leader writes the summary, Minh corrects his answer in the team chat (as a volunteer turn would).
    r._post(T, "Minh sửa: phần A đã xong với số liệu mới", author_kind="agent", author_ref="ag_minh")
    return "TỔNG HỢP CŨ: phần A chưa xong"


async def second_summary(req):
    return "TỔNG HỢP MỚI: cả hai phần xong" if "Minh sửa: phần A đã xong" in req["prompt"] else "TỔNG HỢP SAI"


fake.say("ag_lan", "synthesize", first_summary, second_summary)
job = r.submit(T["team_id"], "Hai phần", as_job=True, client_msg_id="j1")
run(r.dispatch_once(wait=True))
task = ts.get_task(job["task_id"])
check("stale: the leader summarises again with the newer message",
      [c for c in fake.order() if c[1] == "synthesize"] == [("ag_lan", "synthesize")] * 2, fake.order())
check("stale: the job result is the new summary", task["status"] == "done" and "TỔNG HỢP MỚI" in task["result"],
      (task["status"], task.get("result")))
_msgs = ss.get_team_messages_page(T["session_id"], limit=200)["messages"]
_old = next((m for m in _msgs if "TỔNG HỢP CŨ" in m["content"]), {})
check("stale: the old summary stays as evidence, not the job result",
      (_old.get("meta") or {}).get("superseded") is True and not (_old.get("meta") or {}).get("job_result"), _old.get("meta"))

# ================================================================
# 5. Never done with a step left
# ================================================================
ss, ts, tm, fake, r, T = world("guard", leader="ag_lan")


async def plan_and_stray_step(req):
    # A step appears while the leader plans (a stand-in for any path that leaves one behind).
    tm.add_step(req["task_id"], T["team_id"], "work", "ag_minh", 1, "phần còn lại", [], held=True)
    return "Việc nhỏ, em làm luôn: xong"


fake.say("ag_lan", "plan", plan_and_stray_step)
fake.say("ag_minh", "work", "Minh: phần còn lại xong")
job = r.submit(T["team_id"], "Việc nhỏ", as_job=True, client_msg_id="j1")
run(r.dispatch_once(wait=True))
task = ts.get_task(job["task_id"])
check("guard: a job with a step left is not done", task["status"] == "team_blocked" and task["block_kind"] == "failed",
      (task["status"], task.get("block_kind")))
check("guard: the reason says steps have not run", any(w in (task.get("block_reason") or "")
                                                       for w in ("bước chưa chạy", "have not run")), task.get("block_reason"))
_resumed = r.unblock(job["task_id"], "resume")
run(r.dispatch_once(wait=True))
check("guard: resuming runs what is left, then the job closes",
      _resumed and ts.get_task(job["task_id"])["status"] == "done" and ("ag_minh", "work") in fake.order(),
      (ts.get_task(job["task_id"])["status"], fake.order()))

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("ALL PASS")
