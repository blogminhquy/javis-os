"""Nhóm chat team, GOAL T1 (exports/reviews/GOAL-TEAM-CHAT-T1-T4-COMPLETE.md mục 4.2, 9, 12.11, 12.12).

    python tests/run.py team_t1_goal -v

Bộ chạy và kho thật trên SQLite tạm, engine GIẢ theo kịch bản (không gọi model nào). Đồng thời kiểm bằng Event có hạn chờ,
không dựa vào sleep cố định ngắn. Các ca:
- G1 ghim quyền theo lượt: lượt cũ không hưởng quyền cấp lại (thu hồi rồi cấp lại giữa lượt, cấp khi lượt bắt đầu ở Quyền
  giới hạn, cả lượt trò chuyện lẫn bước lập kế hoạch); đối chứng: quyền không đổi thì lệnh áp, set_cap không đổi dòng.
- G2 Ưu tiên qua đường host: A đang chạy trong engine, B và C chờ, ưu tiên C thì thứ tự engine A, C, B; A một lần, không bị
  ngắt; kick thứ hai lúc A chạy không mở việc nào vượt pool.
- G3 khoá bận và hạn giữ việc được gia hạn suốt lượt dài, dừng khi lượt xong hay bị huỷ.
- G4 `running_jobs` là giới hạn máy chủ cố định, không còn là trần chỉnh được mà không có tác dụng.
- G5 bảng giới hạn và "Không giới hạn" cho trần của chủ.
- G6 luật `set_resonance` của trưởng nhóm (chỉ trợ lý do chính nhóm quản lý, dưới Toàn quyền).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-goal-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-goal-w-"))

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []
WAIT = 10.0   # hạn chờ của mọi Event: đủ rộng cho máy chậm, test đỏ thay vì treo


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


class Admin:
    """Thao tác host của lệnh quản trị, bản giả ghi lại lời gọi."""

    def __init__(self):
        self.agents = {s: {"name": s.capitalize(), "prompt": s} for s in ("lan", "minh", "hoa", "tu")}
        self.keys = {s: f"ag_{s}" for s in self.agents}
        self.calls = []
        self.resonance = {}

    def register(self, root, slug):
        self.keys.setdefault(slug, f"ag_{slug}")
        return {"agent_key": self.keys[slug], "slug": slug}

    def exists(self, root, slug):
        return slug in self.agents

    def create_agent(self, root, name, role, prompt):
        slug = name.lower()
        self.agents[slug] = {"name": name, "prompt": prompt}
        return slug

    def edit_prompt(self, root, slug, prompt):
        self.agents[slug]["prompt"] = prompt
        self.calls.append(("edit", slug))

    def set_resonance(self, root, slug, on, by):
        self.resonance[slug] = (on, by)
        self.calls.append(("resonance", slug, on, by))


class Fake:
    """Engine giả: mỗi (agent, vai) một hàng câu trả lời; câu trả lời là hàm async thì được gọi với request."""

    def __init__(self):
        self.script = {}
        self.calls = []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run_(req):
            self.calls.append(req)
            q = self.script.get((agent_key, role)) or []
            ans = q.pop(0) if q else f"{agent_key} {role} xong"
            if callable(ans):
                ans = await ans(req)
            return {"text": ans}
        return "aux", "fake-model", run_


_n = [0]


def world(label, members=("lan", "minh")):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake, admin = Fake(), Admin()

    def agent_info(root, key):
        slug = next((s for s, k in admin.keys.items() if k == key), None)
        if not slug or slug not in admin.agents:
            return None
        a = admin.agents[slug]
        return {"slug": slug, "name": a["name"], "system": a["prompt"], "model": "", "model_provider": ""}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info, admin=admin)

    def new_team(name, mem=members, leader="ag_lan"):
        tid = team_store.new_team_id()
        sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
        tm.create_team(str(d), name, "", sid, team_id=tid)
        for s in mem:
            tm.add_member(tid, admin.keys[s], s)
        if leader:
            tm.set_leader(tid, leader)
        return tm.get(tid)

    return r, tm, ts, ss, fake, admin, new_team(label), new_team


def run(coro):
    return asyncio.run(coro)


def msgs(ss, t):
    return ss.get_team_messages_page(t["session_id"], limit=200)["messages"]


def last_agent(ss, t, key="ag_lan"):
    return [m for m in msgs(ss, t) if m["author_kind"] == "agent" and m["author_ref"] == key][-1]


def lease_tasks(r):
    # Head cũ không có nhịp gia hạn: coi như rỗng (thiếu API), để các ca hành vi vẫn chạy và đỏ đúng chỗ.
    return getattr(r, "_lease_tasks", set())


def limits(r, t):
    return r.authority_view(t["team_id"]).get("limits") or []


def reply(r, t, text, cid):
    return run(r.run_replies(r.submit(t["team_id"], text, client_msg_id=cid)))


FULL = {"caps": {"task_turns": {"unlimited": True}},
        "ceilings": {"task_turns": {"unlimited": True}, "daily_turns": 200, "task_steps": 20, "help_depth": 3},
        "can_interrupt": False, "providers_unlimited": ["aux"], "billing": "subscription"}
PIN_NOTE = "đã đổi sau khi lượt này bắt đầu"

# ═════ G1: ghim quyền theo lượt (GOAL 9 "lượt cũ không hưởng quyền cấp lại", 12.12) ═════
# (a) Toàn quyền lúc lượt bắt đầu; giữa lượt chủ thu hồi rồi cấp lại: lệnh của lượt cũ bị từ chối kèm ghi chú.
r, tm, ts, ss, fake, admin, T, _ = world("regrant")
old_auth = r.grant_authority(T["team_id"], FULL, by="owner")


async def flip(req):
    r.revoke_authority(T["team_id"], by="owner", reason="thử")
    r.grant_authority(T["team_id"], FULL, by="owner")
    return "Được." + directive(op="add_member", slug="hoa")

fake.say("ag_lan", "leader_reply", flip)
reply(r, T, "Thêm người", "a1")
m = last_agent(ss, T)
turn = tm.turn(m["meta"]["turn_id"])
check("G1a thu hồi rồi cấp lại giữa lượt: lệnh add_member của lượt cũ KHÔNG áp", not tm.is_active_member(T["team_id"], "ag_hoa"))
check("G1a ghi chú trên tin nói rõ quyền đã đổi sau khi lượt bắt đầu",
      any(PIN_NOTE in n for n in m["meta"]["notes"]), m["meta"]["notes"])
check("G1a lượt ghim đúng dòng Toàn quyền lúc giữ chỗ (dòng cũ, khác dòng mới)",
      turn.get("authority_id") == old_auth["id"] and tm.active_authority(T["team_id"])["id"] != old_auth["id"], turn)
check("G1a không có sự kiện member_added nào của trưởng nhóm",
      not [e for e in tm.events(T["team_id"]) if e["kind"] == "member_added" and e["by"].startswith("leader:")])

# Lượt KẾ TIẾP (giữ chỗ sau khi cấp lại) dùng được quyền mới.
fake.say("ag_lan", "leader_reply", "Thêm lại." + directive(op="add_member", slug="hoa"))
reply(r, T, "Thêm người lần nữa", "a2")
check("G1a lượt mới sau khi cấp lại thì dùng được quyền mới", tm.is_active_member(T["team_id"], "ag_hoa"))

# (b) Lượt bắt đầu ở Quyền giới hạn, chủ cấp giữa lượt: lời nhắc không có khối Toàn quyền, lệnh bị từ chối.
r, tm, ts, ss, fake, admin, T, _ = world("grantmid")
seen = {}


async def grant_mid(req):
    seen["block"] = "## Toàn quyền" in req["prompt"]
    r.grant_authority(T["team_id"], FULL, by="owner")
    return "Được." + directive(op="add_member", slug="hoa")

fake.say("ag_lan", "leader_reply", grant_mid)
reply(r, T, "Thêm người", "b1")
m = last_agent(ss, T)
check("G1b lượt bắt đầu ở Quyền giới hạn: lời nhắc không có khối Toàn quyền", seen.get("block") is False, seen)
check("G1b chủ cấp giữa lượt: lệnh của lượt đó KHÔNG áp", not tm.is_active_member(T["team_id"], "ag_hoa"))
check("G1b ghi chú nói rõ lượt cũ không dùng quyền mới", any(PIN_NOTE in n for n in m["meta"]["notes"]), m["meta"]["notes"])
check("G1b lượt ghim None (Quyền giới hạn)", "authority_id" in tm.turn(m["meta"]["turn_id"]) and tm.turn(m["meta"]["turn_id"])["authority_id"] is None)

# (c) Đối chứng: quyền không đổi suốt lượt thì lệnh áp; set_cap đổi trần TRONG dòng không làm lệnh sau bị từ chối.
r, tm, ts, ss, fake, admin, T, _ = world("stable")
r.grant_authority(T["team_id"], FULL, by="owner")
fake.say("ag_lan", "leader_reply", "Được." + directive(op="set_cap", cap="task_steps", value=15)
         + directive(op="add_member", slug="hoa"))
reply(r, T, "Thêm người", "c1")
m = last_agent(ss, T)
check("G1c đối chứng: Toàn quyền không đổi thì set_cap và add_member cùng áp",
      tm.is_active_member(T["team_id"], "ag_hoa") and r.effective_caps(T["team_id"])["task_steps"] == 15
      and not any(PIN_NOTE in n for n in m["meta"]["notes"]), m["meta"]["notes"])
check("G1c lượt của thành viên không phải trưởng nhóm không mang ghim quyền",
      all(t.get("authority_id") is None for t in tm.turns(T["team_id"]) if t["agent_key"] != "ag_lan"))
# Prompt của lượt có ghim còn hiệu lực vẫn có khối Toàn quyền.
check("G1c lời nhắc của lượt có ghim còn hiệu lực có khối Toàn quyền", "## Toàn quyền" in fake.calls[-1]["prompt"])

# (d) Bước lập kế hoạch của việc nhóm (vai plan, đường _job_tick/_apply_step): cùng luật.
r, tm, ts, ss, fake, admin, T, _ = world("planpin")
r.grant_authority(T["team_id"], FULL, by="owner")


async def plan_flip(req):
    r.revoke_authority(T["team_id"], by="owner")
    r.grant_authority(T["team_id"], FULL, by="owner")
    return "Tôi tự làm: xong." + directive(op="add_member", slug="hoa")

fake.say("ag_lan", "plan", plan_flip)
job = r.submit(T["team_id"], "Lên kế hoạch tuần", as_job=True, client_msg_id="d1")["task_id"]
run(r.dispatch_once(wait=True))
pm = [x for x in msgs(ss, T) if x["author_kind"] == "agent" and x.get("task_id") == job][-1]
check("G1d bước plan: cấp lại giữa bước thì lệnh quản trị bị từ chối, việc vẫn xong bằng kết quả chữ",
      not tm.is_active_member(T["team_id"], "ag_hoa") and ts.get_task(job)["status"] == "done"
      and any(PIN_NOTE in n for n in pm["meta"]["notes"]), (ts.get_task(job)["status"], pm["meta"]["notes"]))

# ═════ G2: Ưu tiên qua đường host (GOAL 4.2, 12.11) ═════
r, tm, ts, ss, fake, admin, T, new_team = world("prio")
T2 = new_team("prio-khac", mem=("tu",), leader="ag_tu")
r.max_parallel_teams = 1
order = []
gate_box = {}


def prio_engine(team, key, role):
    async def run_(req):
        cur = req["prompt"].split("## Việc hiện tại", 1)[-1][:200]
        title = next((w for w in ("JOBA", "JOBB", "JOBC", "JOBD") if w in cur), "?")
        order.append(title)
        if title == "JOBA":
            gate_box["a_started"].set()
            await asyncio.wait_for(gate_box["gate"].wait(), WAIT)
        return {"text": f"{title} xong"}
    return "aux", "fake", run_

r.engine_for = prio_engine


async def prio_main():
    gate_box["gate"], gate_box["a_started"] = asyncio.Event(), asyncio.Event()
    ids = {n: r.submit(T["team_id"], n, mentions=["ag_minh"], as_job=True, client_msg_id=n)["task_id"]
           for n in ("JOBA", "JOBB", "JOBC")}
    first = await r.dispatch_once(wait=False)
    await asyncio.wait_for(gate_box["a_started"].wait(), WAIT)
    # Việc của nhóm khác tới SAU khi A đã chạy: pool một chỗ đang bận, kick thứ hai không được mở nó.
    ids["JOBD"] = r.submit(T2["team_id"], "JOBD", mentions=["ag_tu"], as_job=True, client_msg_id="JOBD")["task_id"]
    q = ts.team_queue(T["team_id"])
    ts.team_priority(ids["JOBC"], True, q["version"])
    waiting = [t["title"] for t in ts.team_queue(T["team_id"])["waiting"]]
    second = await r.dispatch_once(wait=False)    # kick thứ hai lúc A còn chạy
    running_during = sorted(t["id"] for t in ts.team_running_tasks())
    pool_during = dict(r._pool)
    gate_box["gate"].set()
    for _ in range(6):
        await r.wait_jobs()
        await r.dispatch_once(wait=True)
    return ids, first, waiting, second, running_during, pool_during

ids, first, waiting, second, running_during, pool_during = run(prio_main())
team1 = [x for x in order if x in ("JOBA", "JOBB", "JOBC")]
check("G2 ưu tiên C lúc A đang chạy: hàng chờ C trước B", waiting == ["JOBC", "JOBB"], waiting)
check("G2 thứ tự engine của nhóm: A, C, B", team1 == ["JOBA", "JOBC", "JOBB"], order)
check("G2 A chạy đúng một lần, không bị ngắt hay chạy lại",
      order.count("JOBA") == 1 and ts.get_task(ids["JOBA"])["status"] == "done"
      and [t["status"] for t in tm.turns(T["team_id"]) if t["task_id"] == ids["JOBA"]] == ["ok"]
      and not [s for s in tm.steps(ids["JOBA"]) if s["status"] in ("interrupted", "cancelled", "failed")],
      [t["status"] for t in tm.turns(T["team_id"]) if t["task_id"] == ids["JOBA"]])
check("G2 kick thứ hai lúc A chạy không mở thêm việc (pool 1: không C, không việc của nhóm khác)",
      first == [ids["JOBA"]] and second == [] and running_during == [ids["JOBA"]]
      and pool_during == {ids["JOBA"]: T["team_id"]}, (first, second, running_during, pool_during))
check("G2 mọi việc xong, mỗi việc một lượt engine", all(ts.get_task(i)["status"] == "done" for i in ids.values())
      and sorted(order) == ["JOBA", "JOBB", "JOBC", "JOBD"], order)

# ═════ G3: gia hạn khoá bận và hạn giữ việc trong lượt dài (heartbeat lớp 1) ═════
# Hạn ngắn để thấy hết hạn trong vài phần mười giây. Đặt cả hằng của module (bản cũ đọc hằng lúc gọi) lẫn thuộc tính.
TR.BUSY_LEASE_S = 0.3
r, tm, ts, ss, fake, admin, T, new_team = world("lease")
OTHER = new_team("lease-khac", mem=("minh",), leader=None)
r.busy_lease_s, r.job_lease_s, r.lease_renew_s = 0.3, 0.3, 0.05
lease = {}


async def wait_until(cond, timeout=WAIT, step=0.02):
    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            return False
        await asyncio.sleep(step)
    return True


def busy_row(key):
    with tm._conn() as c:
        # 0.257.0: a team turn holds the row `<agent>#<team>` (per thread), not the bare agent row.
        row = c.execute("SELECT * FROM agent_busy WHERE agent_key=? OR agent_key LIKE ?", (key, key + "#%")).fetchone()
        return dict(row) if row else None


async def long_step(req):
    b0, c0 = busy_row("ag_minh"), ts.get_task(req["task_id"])["claim_expires_at"]
    lease["b0"], lease["c0"] = b0, c0
    # Chờ tới khi đã quá hạn GỐC của cả khoá bận lẫn hạn giữ việc một khoảng (điều kiện, có hạn chờ).
    lease["waited"] = await wait_until(lambda: time.time() > max(b0["lease_until"], c0) + 0.25)
    now = time.time()
    lease["busy_now"] = tm.busy_of("ag_minh", now)
    lease["intruder"] = tm.acquire_busy("ag_minh", OTHER["team_id"], "tu_intruder", lease_s=10, now=now)
    lease["c1"] = ts.get_task(req["task_id"])["claim_expires_at"]
    lease["now"] = now
    return "Xong phần việc."

fake.say("ag_minh", "work", long_step)
job = r.submit(T["team_id"], "Việc dài", mentions=["ag_minh"], as_job=True, client_msg_id="l1")["task_id"]


async def lease_main():
    await r.dispatch_once(wait=True)
    done = await wait_until(lambda: not lease_tasks(r), timeout=WAIT)
    return done

drained = run(lease_main())
check("G3 bước dài: đã quá hạn gốc của khoá bận và hạn giữ việc", lease.get("waited") is True, lease)
check("G3 khoá bận được gia hạn: vẫn thuộc đúng lượt, tiến trình khác không giành được agent",
      lease.get("busy_now") is not None and lease["busy_now"]["turn_id"] == lease["b0"]["turn_id"]
      and lease.get("intruder") is False, lease)
check("G3 hạn giữ việc được gia hạn trong lúc bước chạy (không chỉ ở điểm điều phối)",
      lease.get("c1", 0) > lease.get("c0", 0) and lease["c1"] > lease["now"], lease)
check("G3 lượt xong: dừng gia hạn, khoá bận đã nhả, việc xong", drained and busy_row("ag_minh") is None
      and ts.get_task(job)["status"] == "done", (drained, busy_row("ag_minh")))
# Huỷ giữa lượt: dừng gia hạn, nhả khoá. (Head cũ để kẻ chen giữ khoá ở ca trên: gỡ để ca này vẫn chạy được.)
tm.release_busy("ag_minh", "tu_intruder")
gate = {}


async def blocked_step(req):
    gate["started"].set()
    await asyncio.wait_for(asyncio.Event().wait(), WAIT)
    return "không tới đây"

fake.say("ag_minh", "work", blocked_step)
job2 = r.submit(T["team_id"], "Việc bị huỷ", mentions=["ag_minh"], as_job=True, client_msg_id="l2")["task_id"]


async def cancel_main():
    gate["started"] = asyncio.Event()
    await r.dispatch_once(wait=False)
    await asyncio.wait_for(gate["started"].wait(), WAIT)
    during = len(lease_tasks(r))
    r.cancel_job(job2, "chủ huỷ")
    await r.wait_jobs()
    done = await wait_until(lambda: not lease_tasks(r), timeout=WAIT)
    return during, done

during, done = run(cancel_main())
check("G3 huỷ giữa lượt: có nhịp gia hạn lúc chạy, dừng sau khi huỷ, khoá bận đã nhả",
      during == 1 and done and busy_row("ag_minh") is None and ts.get_task(job2)["status"] == "cancelled",
      (during, done, busy_row("ag_minh"), ts.get_task(job2)["status"]))
TR.BUSY_LEASE_S = 900.0

# ═════ G4: running_jobs là giới hạn máy chủ cố định ═════
r, tm, ts, ss, fake, admin, T, _ = world("runjobs")
try:
    tm.set_caps(T["team_id"], {"running_jobs": 3})
    refused = False
except team_store.TeamError:
    refused = True
check("G4 chủ không đặt được running_jobs (giới hạn máy chủ, trước đây nhận mà không có tác dụng)", refused)
with tm._Tx(tm) as c:   # dòng cũ từng lưu running_jobs=3 trước bản này
    c.execute("UPDATE teams SET caps_json=? WHERE team_id=?", (json.dumps({"running_jobs": 3, "no_progress": 5}),
                                                                T["team_id"]))
check("G4 dòng cũ vẫn hiện giá trị đang áp (1 việc, 2 lần không tiến triển)",
      tm.get(T["team_id"])["caps"]["running_jobs"] == 1 and tm.get(T["team_id"])["caps"]["no_progress"] == 2)
r.max_parallel_teams = 3
for n in ("R1", "R2"):
    r.submit(T["team_id"], n, mentions=["ag_minh"], as_job=True, client_msg_id=n)


async def runjobs_main():
    got = await r.dispatch_once(wait=False)
    running = len(ts.team_queue(T["team_id"])["running"])
    again = await r.dispatch_once(wait=False)
    await r.wait_jobs()
    return got, running, again

claimed, running_n, again = run(runjobs_main())
check("G4 nhóm có hai việc chờ, pool 3: chỉ một việc chạy, kick lại cũng không mở việc thứ hai",
      len(claimed) == 1 and running_n == 1 and again == [], (claimed, running_n, again))
lim = {(x["category"], x["key"]): x for x in limits(r, T)}
check("G4 bảng giới hạn: running_jobs và no_progress thuộc máy chủ, không thuộc trần của chủ",
      ("server", "running_jobs") in lim and lim[("server", "running_jobs")]["value"] == 1 and lim[("server", "no_progress")]["value"] == 2
      and ("owner", "running_jobs") not in lim and ("owner", "no_progress") not in lim, sorted(lim))

# ═════ G5: bảng giới hạn, Không giới hạn cho trần của chủ ═════
r, tm, ts, ss, fake, admin, T, _ = world("limits")
rows = limits(r, T)
cats = {x["category"] for x in rows}
owner_rows = {x["key"]: x for x in rows if x["category"] == "owner"}
check("G5 bảng có đủ bốn nhóm: chủ, trưởng nhóm (Toàn quyền), máy chủ, nhà cung cấp",
      cats == {"owner", "leader", "server", "provider"}, cats)
check("G5 trần của chủ: bốn trần có Không giới hạn, @ mỗi tin và thời gian chờ thì không",
      # T3: judge_daily (phần J) và agent_daily_calls (phần L) cũng có Không giới hạn.
      bool(owner_rows) and {"task_turns", "task_steps", "help_depth", "daily_turns"}
      <= {k for k, x in owner_rows.items() if x["unlimited_ok"]}
      <= {"task_turns", "task_steps", "help_depth", "daily_turns", "judge_daily", "agent_daily_calls"}
      and not owner_rows["mentions"]["unlimited_ok"] and not owner_rows["busy_wait_s"]["unlimited_ok"], owner_rows)
check("G5 không dòng máy chủ hay nhà cung cấp nào có Không giới hạn (không quảng cáo bỏ mọi giới hạn)",
      rows and not [x for x in rows if x["category"] in ("server", "provider") and x["unlimited_ok"]])
check("G5 dòng trưởng nhóm: Quyền giới hạn thì chưa chỉnh được",
      rows and all(not x["granted"] and not x["editable"] for x in rows if x["category"] == "leader"))
r.grant_authority(T["team_id"], FULL, by="owner")
lead = {x["key"]: x for x in limits(r, T) if x["category"] == "leader"}
check("G5 Toàn quyền: dòng trưởng nhóm theo trần tối đa của chủ (Không giới hạn là null)",
      bool(lead) and lead["task_turns"]["value"] is None and lead["daily_turns"]["value"] == 200 and lead["task_turns"]["editable"]
      and lead["daily_turns"]["model_turns"] and not lead["help_depth"]["model_turns"], lead)
r.revoke_authority(T["team_id"])
try:
    tm.set_caps(T["team_id"], {"daily_turns": {"unlimited": True}, "task_steps": None})
except team_store.TeamError as ex:   # head cũ: chưa có Không giới hạn cho trần của chủ
    print(f"  (set_caps Không giới hạn bị từ chối: {ex})")
caps = tm.get(T["team_id"])["caps"]
check("G5 chủ đặt Không giới hạn: lưu null, không thay bằng số lớn", caps["daily_turns"] is None and caps["task_steps"] is None,
      caps)
check("G5 Không giới hạn của chủ có hiệu lực ở trần đang áp và dòng Hôm nay đã dùng",
      r.effective_caps(T["team_id"])["daily_turns"] is None and r.usage(T["team_id"])["cap"] is None)
reply(r, T, "Chào", "g5")
check("G5 lượt chạy được khi trần ngày là Không giới hạn", last_agent(ss, T)["meta"]["applied"])
for bad in ({"mentions": None}, {"busy_wait_s": {"unlimited": True}}, {"task_turns": True}, {"task_turns": -1}):
    try:
        tm.set_caps(T["team_id"], bad)
        ok = False
    except team_store.TeamError:
        ok = True
    check(f"G5 trần sai khuôn bị từ chối: {bad}", ok)
tm.set_caps(T["team_id"], {"daily_turns": 50})
check("G5 đặt lại số sau Không giới hạn", tm.get(T["team_id"])["caps"]["daily_turns"] == 50)

# ═════ G6: luật set_resonance của trưởng nhóm (GOAL 4.3, 9) ═════
r, tm, ts, ss, fake, admin, T, new_team = world("resonance", members=("lan", "minh", "hoa"))
admin.resonance["minh"] = (False, "owner")   # chủ đã tắt Auto của Minh
admin.resonance["hoa"] = (False, "owner")
r.grant_authority(T["team_id"], FULL, by="owner")
fake.say("ag_lan", "leader_reply", "Bật Auto." + directive(op="set_resonance", agent="minh", on=True))
reply(r, T, "Bật Auto cho Minh", "r1")
m = last_agent(ss, T)
check("G6 trợ lý chỉ tham gia (nhóm không quản lý), chủ đã tắt: trưởng nhóm Toàn quyền KHÔNG bật lại được",
      admin.resonance["minh"] == (False, "owner") and not [x for x in admin.calls if x[0] == "resonance"]
      and any("do nhóm này quản lý" in n for n in m["meta"]["notes"]), (admin.resonance, m["meta"]["notes"]))
OTHER = new_team("resonance-khac", mem=("hoa", "tu"), leader="ag_tu")
tm.set_managed(OTHER["team_id"], "ag_hoa", True)
fake.say("ag_lan", "leader_reply", "Bật Auto." + directive(op="set_resonance", agent="hoa", on=True))
reply(r, T, "Bật Auto cho Hoa", "r2")
check("G6 trợ lý do NHÓM KHÁC quản lý: trưởng nhóm này không bật được", admin.resonance["hoa"] == (False, "owner"))
tm.set_managed(T["team_id"], "ag_minh", True)
r.revoke_authority(T["team_id"])
fake.say("ag_lan", "leader_reply", "Bật Auto." + directive(op="set_resonance", agent="minh", on=True))
reply(r, T, "Bật Auto cho Minh", "r3")
check("G6 nhóm quản lý nhưng Quyền giới hạn: không bật được", admin.resonance["minh"] == (False, "owner"))
r.grant_authority(T["team_id"], FULL, by="owner")
fake.say("ag_lan", "leader_reply", "Bật Auto." + directive(op="set_resonance", agent="minh", on=True))
reply(r, T, "Bật Auto cho Minh", "r4")
ev = [e for e in tm.events(T["team_id"]) if e["kind"] == "agent_set_resonance"]
check("G6 nhóm quản lý và Toàn quyền: bật được, ghi by=leader và có nhật ký team_events",
      admin.resonance["minh"] == (True, "leader:ag_lan") and len(ev) == 1 and ev[0]["by"] == "leader:ag_lan", (admin.resonance, ev))

print(f"\n{len(fails)} FAIL" if fails else "\nALL OK")
raise SystemExit(1 if fails else 0)
