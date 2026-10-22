"""Nhóm chat team, các điểm của review độc lập T1 (exports/reviews/team-adaptive, review-t1.md) sau head af85ad71.

    python tests/run.py team_t1_review_fixes -v

Bộ chạy và kho thật trên SQLite tạm, engine GIẢ (không gọi model nào). Các ca:
- F1 mất quyền giữ giữa lượt: khoá bận đã sang lượt khác, việc đã đổi người giữ, kho lỗi kéo dài quá kỳ hạn. Đầu ra cũ
  không ghi bài học, không áp lệnh quản trị hay kết quả bước. Đối chứng: kho lỗi tạm một nhịp KHÔNG làm mất quyền.
- F2 hạn giữ việc được gia hạn trong lúc lượt còn chờ khoá bận; khoá agent của lượt khác không bị đụng.
- F3 bảng giới hạn đọc trần lượt gọi của máy chủ bằng đúng `resonance_store.call_ceiling()` (rỗng, số, +10, -5, chuỗi hỏng).
- F4 bật Auto thành công mà đánh thức mục tiêu lỗi: vẫn có nhật ký nhóm, ghi lỗi đánh thức, không báo cả lệnh chưa áp.
- F5 `set_caps` từ chối NaN, vô cực và kiểu sai TRƯỚC khi ghi, kể cả busy_wait_s và trần trong hộp quyền.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import math
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-t1fix-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-t1fix-w-"))

import resonance_store  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []
WAIT = 10.0


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


class Admin:
    def __init__(self):
        self.agents = {s: {"name": s.capitalize(), "prompt": s} for s in ("lan", "minh", "hoa")}
        self.keys = {s: f"ag_{s}" for s in self.agents}
        self.calls = []
        self.wake_error = ""

    def register(self, root, slug):
        self.keys.setdefault(slug, f"ag_{slug}")
        return {"agent_key": self.keys[slug], "slug": slug}

    def exists(self, root, slug):
        return slug in self.agents

    def edit_prompt(self, root, slug, prompt):
        self.calls.append(("edit", slug))

    def set_resonance(self, root, slug, on, by):
        self.calls.append(("resonance", slug, on, by))
        if self.wake_error:
            return {"enabled": True, "wake_error": self.wake_error}
        return {"enabled": bool(on)}


class Fake:
    """Engine giả: câu trả lời là chuỗi, dict (text, commit...) hay hàm async trả một trong hai."""

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
            return ans if isinstance(ans, dict) else {"text": ans}
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
    r.busy_lease_s, r.job_lease_s, r.lease_renew_s = 0.3, 0.3, 0.05

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


def last_agent(ss, t, key):
    got = [m for m in msgs(ss, t) if m["author_kind"] == "agent" and m["author_ref"] == key]
    return got[-1] if got else None


async def wait_until(cond, timeout=WAIT, step=0.02):
    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            return False
        await asyncio.sleep(step)
    return True


def reply(r, t, text, cid):
    return run(r.run_replies(r.submit(t["team_id"], text, client_msg_id=cid)))


FULL = {"caps": {}, "ceilings": {"task_turns": 24, "daily_turns": 200, "task_steps": 20, "help_depth": 3},
        "can_interrupt": False, "providers_unlimited": [], "billing": "subscription"}

# ═════ F1a: khoá bận sang lượt khác giữa lượt trò chuyện của trưởng nhóm ═════
r, tm, ts, ss, fake, admin, T, new_team = world("busy-taken")
OTHER = new_team("khac", mem=("lan",), leader=None)
r.grant_authority(T["team_id"], FULL, by="owner")
committed = []


async def steal(req):
    # Kho mất dòng khoá của lượt này (hạn hết lúc kho lỗi) và một lượt khác lấy agent; chờ nhịp gia hạn thấy điều đó.
    tm.release_busy("ag_lan", req["turn_id"])
    tm.acquire_busy("ag_lan", OTHER["team_id"], "tu_other", lease_s=30)
    await wait_until(lambda: False, timeout=0.4)
    return {"text": "Đã thêm Hoa." + directive(op="add_member", slug="hoa"),
            "commit": lambda: committed.append("lesson")}

fake.say("ag_lan", "leader_reply", steal)
reply(r, T, "Thêm Hoa vào nhóm", "f1a")
m = last_agent(ss, T, "ag_lan")
check("F1a khoá bận đã sang lượt khác: lệnh add_member của đầu ra cũ KHÔNG áp",
      not tm.is_active_member(T["team_id"], "ag_hoa"))
check("F1a không ghi bài học của lượt đã mất quyền giữ", committed == [], committed)
check("F1a tin vẫn đăng làm bằng chứng, trạng thái lease_lost, nói rõ lý do",
      m is not None and m["meta"]["status"] == "lease_lost" and m["meta"]["applied"] is False
      and m["meta"].get("lease_lost") == "busy_taken" and any("mất quyền giữ" in n for n in m["meta"]["notes"]),
      m and m["meta"])
row = tm.busy_turn("ag_lan")
check("F1a lượt cũ không nhả hay ghi đè khoá của lượt khác", row == "tu_other", row)
tm.release_busy("ag_lan", "tu_other")

# ═════ F1b: kho lỗi tạm một nhịp: KHÔNG mất quyền, đầu ra được áp ═════
r, tm, ts, ss, fake, admin, T, _ = world("transient")
r.grant_authority(T["team_id"], FULL, by="owner")
orig_renew = tm.renew_busy
flaky = {"n": 0}


def renew_flaky(*a, **k):
    flaky["n"] += 1
    if flaky["n"] == 1:
        raise RuntimeError("database is locked")
    return orig_renew(*a, **k)


tm.renew_busy = renew_flaky


async def slow_ok(req):
    await wait_until(lambda: flaky["n"] >= 3, timeout=WAIT)
    return "Đã thêm Hoa." + directive(op="add_member", slug="hoa")

fake.say("ag_lan", "leader_reply", slow_ok)
reply(r, T, "Thêm Hoa", "f1b")
m = last_agent(ss, T, "ag_lan")
check("F1b kho lỗi một nhịp rồi gia hạn lại được: lượt vẫn giữ quyền, lệnh được áp",
      flaky["n"] >= 3 and m["meta"]["status"] == "done" and tm.is_active_member(T["team_id"], "ag_hoa"),
      (flaky, m["meta"]))
tm.renew_busy = orig_renew

# ═════ F1c: kho lỗi kéo dài quá kỳ hạn: coi là mất quyền (hạn đã hết, tiến trình khác có thể đã lấy) ═════
r, tm, ts, ss, fake, admin, T, _ = world("store-down")
r.grant_authority(T["team_id"], FULL, by="owner")
down = {"n": 0}


def renew_down(*a, **k):
    down["n"] += 1
    raise RuntimeError("disk I/O error")


tm.renew_busy = renew_down


async def outlast(req):
    await wait_until(lambda: False, timeout=0.6)   # dài hơn busy_lease_s = 0.3 giây
    return "Đã thêm Hoa." + directive(op="add_member", slug="hoa")

fake.say("ag_lan", "leader_reply", outlast)
reply(r, T, "Thêm Hoa", "f1c")
m = last_agent(ss, T, "ag_lan")
check("F1c kho lỗi suốt quá kỳ hạn khoá: mất quyền (store_error), lệnh không áp",
      m["meta"]["status"] == "lease_lost" and m["meta"].get("lease_lost") == "store_error"
      and not tm.is_active_member(T["team_id"], "ag_hoa"), (down, m["meta"]))
tm.renew_busy = orig_renew

# ═════ F1d: việc đã đổi người giữ giữa bước: không áp kết quả, không đụng bước, vòng của tiến trình này dừng ═════
r, tm, ts, ss, fake, admin, T, _ = world("job-lost")


async def job_stolen(req):
    with ts._lock:
        ts._db.execute("UPDATE tasks SET claimed_by='worker-khac' WHERE id=?", (req["task_id"],))
        ts._db.commit()
    await wait_until(lambda: False, timeout=0.3)
    return {"text": "Xong phần việc.", "commit": lambda: committed.append("step-lesson")}

committed.clear()
fake.say("ag_minh", "work", job_stolen)
job = r.submit(T["team_id"], "Việc bị giành", mentions=["ag_minh"], as_job=True, client_msg_id="f1d")["task_id"]


async def job_main():
    await r.dispatch_once(wait=True)
    await r.wait_jobs()

run(job_main())
m = last_agent(ss, T, "ag_minh")
steps = tm.steps(job)
check("F1d việc đổi người giữ: tin bằng chứng mang lease_lost=job_lost, không áp",
      m is not None and m["meta"]["status"] == "lease_lost" and m["meta"].get("lease_lost") == "job_lost", m and m["meta"])
check("F1d không ghi bài học bước, không chốt bước (tiến trình đang giữ việc quyết)",
      committed == [] and all(s["status"] != "done" for s in steps), (committed, [s["status"] for s in steps]))
check("F1d việc vẫn thuộc tiến trình kia, không bị chuyển trạng thái bởi kết quả cũ",
      ts.get_task(job)["claimed_by"] == "worker-khac" and ts.get_task(job)["status"] == "team_running",
      ts.get_task(job))

# ═════ F1e: chỉ mất khoá agent, việc vẫn của mình: bước chạy lại, chỉ áp đúng một lần ═════
r, tm, ts, ss, fake, admin, T, new_team = world("busy-step")
OTHER = new_team("khac2", mem=("minh",), leader=None)
runs = []


async def steal_step(req):
    runs.append(req["turn_id"])
    tm.release_busy("ag_minh", req["turn_id"])
    tm.acquire_busy("ag_minh", OTHER["team_id"], "tu_x", lease_s=0.2)
    await wait_until(lambda: False, timeout=0.35)
    return "Bản đầu (không dùng)."


async def second_ok(req):
    runs.append(req["turn_id"])
    return "Bản chạy lại."

fake.say("ag_minh", "work", steal_step, second_ok)
job = r.submit(T["team_id"], "Việc mất khoá", mentions=["ag_minh"], as_job=True, client_msg_id="f1e")["task_id"]
run(job_main())
outs = [m for m in msgs(ss, T) if m["author_kind"] == "agent" and m["author_ref"] == "ag_minh"]
check("F1e mất khoá agent giữa bước: bước chạy lại ở lượt sau, việc xong",
      len(runs) == 2 and ts.get_task(job)["status"] == "done", (runs, ts.get_task(job)["status"]))
check("F1e chỉ bản chạy lại được áp, bản đầu là bằng chứng lease_lost",
      [x["meta"]["status"] for x in outs] == ["lease_lost", "done"], [x["meta"]["status"] for x in outs])

# ═════ F2: gia hạn hạn giữ việc trong lúc chờ khoá bận, không đụng khoá của lượt khác ═════
r, tm, ts, ss, fake, admin, T, new_team = world("wait-renew")
OTHER = new_team("khac3", mem=("minh",), leader=None)
tm.acquire_busy("ag_minh", OTHER["team_id"], "tu_holder", lease_s=30)
holder_until = tm.busy_of("ag_minh")["lease_until"]
seen = {}


async def waited(req):
    return "Xong sau khi chờ."

fake.say("ag_minh", "work", waited)
job = r.submit(T["team_id"], "Việc phải chờ", mentions=["ag_minh"], as_job=True, client_msg_id="f2")["task_id"]


async def wait_main():
    await r.dispatch_once(wait=False)
    ok = await wait_until(lambda: (ts.get_task(job) or {}).get("status") == "team_running", timeout=WAIT)
    c0 = ts.get_task(job)["claim_expires_at"]
    # Chờ quá hạn gốc của việc một khoảng: không gia hạn thì hạn đã hết.
    await wait_until(lambda: time.time() > c0 + 0.3, timeout=WAIT)
    seen["c0"], seen["c1"], seen["now"] = c0, ts.get_task(job)["claim_expires_at"], time.time()
    seen["holder"] = tm.busy_of("ag_minh")
    tm.release_busy("ag_minh", "tu_holder")
    await r.wait_jobs()
    return ok

ok = run(wait_main())
check("F2 lượt đang chờ khoá bận: hạn giữ việc vẫn được gia hạn (quá hạn gốc mà hạn mới còn)",
      ok and seen["c1"] > seen["c0"] and seen["c1"] > seen["now"], seen)
check("F2 chưa sở hữu khoá agent: khoá của lượt đang giữ không bị gia hạn hay giành",
      seen["holder"] and seen["holder"]["turn_id"] == "tu_holder" and seen["holder"]["lease_until"] == holder_until,
      seen.get("holder"))
check("F2 nhả khoá xong: bước chạy và việc xong", ts.get_task(job)["status"] == "done", ts.get_task(job)["status"])

# ═════ F3: trần lượt gọi của máy chủ trong bảng giới hạn = call_ceiling() ═════
r, tm, ts, ss, fake, admin, T, _ = world("ceiling")


def server_row():
    return next(x for x in r.limits_table(T["team_id"]) if x["key"] == "server_call_ceiling")


old_env = os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
cases = [("", None, "rule"), ("7", 7, "count"), ("+10", 10, "count"), ("-5", 0, "count"), ("abc", 0, "count"),
         (" 12 ", 12, "count")]
for raw, want, unit in cases:
    if raw == "":
        os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
    else:
        os.environ["JAVIS_RESONANCE_CALL_CEILING"] = raw
    row = server_row()
    check(f"F3 trần máy chủ {raw!r}: bảng hiện {want} ({unit}), khớp call_ceiling()",
          row["value"] == want and row["unit"] == unit and row["value"] == resonance_store.call_ceiling(), row)
if old_env is None:
    os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
else:
    os.environ["JAVIS_RESONANCE_CALL_CEILING"] = old_env

# ═════ F4: bật Auto được ghi, đánh thức lỗi ═════
r, tm, ts, ss, fake, admin, T, _ = world("wake-fail")
r.grant_authority(T["team_id"], FULL, by="owner")
tm.set_managed(T["team_id"], "ag_minh", True, by="owner")
admin.wake_error = "RuntimeError: database is locked"
fake.say("ag_lan", "leader_reply", "Bật Auto cho Minh." + directive(op="set_resonance", agent="minh", on=True))
reply(r, T, "Bật Auto cho Minh", "f4")
m = last_agent(ss, T, "ag_lan")
kinds = [e["kind"] for e in tm.events(T["team_id"])]
check("F4 lệnh bật Auto đã gọi host đúng một lần", [c for c in admin.calls if c[0] == "resonance"] ==
      [("resonance", "minh", True, f"leader:ag_lan")], admin.calls)
check("F4 nhật ký nhóm có cả sự kiện bật Auto lẫn lỗi đánh thức",
      "agent_set_resonance" in kinds and "agent_wake_failed" in kinds, kinds)
wake_ev = [e for e in tm.events(T["team_id"]) if e["kind"] == "agent_wake_failed"]
check("F4 sự kiện lỗi đánh thức ghi trợ lý và nguyên nhân",
      wake_ev and wake_ev[-1]["after"]["agent_key"] == "ag_minh" and "locked" in wake_ev[-1]["after"]["error"], wake_ev)
check("F4 ghi chú nói Auto ĐÃ bật, chỉ chưa đánh thức ngay (không báo cả lệnh thất bại)",
      any("Auto đã bật" in n for n in m["meta"]["notes"]) and not any("không áp" in n.lower() for n in m["meta"]["notes"]),
      m["meta"]["notes"])
sysmsgs = [x for x in msgs(ss, T) if x["author_kind"] == "system"]
check("F4 tin hệ thống báo trưởng nhóm đã bật Auto", any("bật Auto cho" in x["content"] for x in sysmsgs),
      [x["content"] for x in sysmsgs])

# ═════ F5: set_caps chặn NaN, vô cực, kiểu sai trước khi ghi ═════
r, tm, ts, ss, fake, admin, T, _ = world("caps-nan")
before = tm.get(T["team_id"])["caps"]
bad_inputs = [{"busy_wait_s": float("nan")}, {"busy_wait_s": float("inf")}, {"task_turns": float("-inf")},
              {"task_steps": float("nan")}, {"daily_turns": "1e400"}, {"mentions": "NaN"}, ["task_turns", 3],
              {"task_turns": [3]}, {"task_turns": True}]
for bad in bad_inputs:
    try:
        tm.set_caps(T["team_id"], bad)
        got = "accepted"
    except team_store.TeamError:
        got = "rejected"
    except Exception as ex:  # noqa: BLE001
        got = f"crash {type(ex).__name__}"
    check(f"F5 set_caps({bad!r}) bị từ chối bằng TeamError (4xx), không lỗi khác", got == "rejected", got)
after = tm.get(T["team_id"])["caps"]
check("F5 không có giá trị hỏng nào được ghi", after == before and all(
    v is None or (isinstance(v, (int, float)) and math.isfinite(v)) for v in after.values()), after)
check("F5 caps_json vẫn là JSON chuẩn (không NaN/Infinity)", "NaN" not in json.dumps(after, allow_nan=True)
      and "Infinity" not in json.dumps(after, allow_nan=True), after)
for bad in (float("nan"), float("inf")):
    try:
        TR.TeamRunner._cap_value(bad)
        got = "accepted"
    except team_store.TeamError:
        got = "rejected"
    except Exception as ex:  # noqa: BLE001
        got = f"crash {type(ex).__name__}"
    check(f"F5 trần trong hộp quyền {bad!r} bị từ chối bằng TeamError", got == "rejected", got)
check("F5 đối chứng: số hữu hạn hợp lệ vẫn lưu", tm.set_caps(T["team_id"], {"busy_wait_s": 60.5})["caps"]["busy_wait_s"]
      == 60.5)

# ═════ F6 (review vòng 2 #1): huỷ lần hai đúng lúc kiểm khoá lần cuối vẫn nhả khoá ═════
r, tm, ts, ss, fake, admin, T, _ = world("double-cancel")
r.busy_lease_s, r.job_lease_s, r.lease_renew_s = 5, 5, 1
orig_bt = tm.busy_turn
in_check = {"n": 0}


def slow_busy_turn(k, *rest):
    in_check["n"] += 1
    time.sleep(0.5)
    return orig_bt(k, *rest)


tm.busy_turn = slow_busy_turn


async def hang(req):
    await asyncio.sleep(30)
    return "không tới đây"

fake.say("ag_minh", "work", hang)
dc = {}


async def double_cancel():
    job = r.submit(T["team_id"], "Việc treo", mentions=["ag_minh"], as_job=True, client_msg_id="f6")["task_id"]
    await r.dispatch_once(wait=False)
    await wait_until(lambda: len(fake.calls) >= 1, timeout=WAIT)
    j = r._jobs[job]
    j.cancel()
    await wait_until(lambda: in_check["n"] >= 1, timeout=WAIT)   # đang ở lần kiểm cuối (đọc kho chậm)
    j.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(j), WAIT)
    except BaseException:  # noqa: BLE001
        pass
    await wait_until(lambda: tm.busy_of("ag_minh") is None, timeout=WAIT)
    lk = r._locks.get("ag_minh")
    dc["locked"] = bool(lk and lk.locked())
    dc["row"] = tm.busy_of("ag_minh")

run(double_cancel())
tm.busy_turn = orig_bt
check("F6 huỷ lần hai giữa lần kiểm cuối: khoá trong tiến trình và dòng khoá đều đã nhả",
      in_check["n"] >= 1 and dc.get("locked") is False and dc.get("row") is None, (in_check, dc))

# ═════ F7 (review vòng 2 #3): việc mất người giữ ngay lúc chờ khoá thì không gọi engine ═════
r, tm, ts, ss, fake, admin, T, new_team = world("lost-in-wait")
OTHER = new_team("khac4", mem=("minh",), leader=None)
tm.acquire_busy("ag_minh", OTHER["team_id"], "tu_hold", lease_s=30)
fake.say("ag_minh", "work", "Không được gọi.")
job = r.submit(T["team_id"], "Việc mất khi chờ", mentions=["ag_minh"], as_job=True, client_msg_id="f7")["task_id"]
lw = {}


async def lost_in_wait():
    await r.dispatch_once(wait=False)
    await wait_until(lambda: (ts.get_task(job) or {}).get("status") == "team_running", timeout=WAIT)
    with ts._lock:
        ts._db.execute("UPDATE tasks SET claimed_by='worker-khac' WHERE id=?", (job,))
        ts._db.commit()
    await wait_until(lambda: False, timeout=0.3)   # vài nhịp gia hạn thấy việc đã sang người khác
    tm.release_busy("ag_minh", "tu_hold")
    await r.wait_jobs()
    lw["turns"] = [t for t in tm.turns(T["team_id"]) if t["agent_key"] == "ag_minh"]

run(lost_in_wait())
check("F7 mất việc lúc chờ khoá: engine không được gọi, lượt được hoàn",
      not fake.calls and all(t["status"] == "refunded" for t in lw["turns"]) and lw["turns"],
      (len(fake.calls), [t["status"] for t in lw.get("turns", [])]))
check("F7 khoá agent đã nhả sau khi bỏ lượt", tm.busy_of("ag_minh") is None, tm.busy_of("ag_minh"))

# ═════ F8 (review vòng 2 #4): mất khoá agent lặp lại thì chặn việc, không chạy lại mãi ═════
r, tm, ts, ss, fake, admin, T, new_team = world("requeue-cap")
OTHER = new_team("khac5", mem=("minh",), leader=None)
tm.set_caps(T["team_id"], {"task_turns": {"unlimited": True}})
steals = []


async def always_steal(req):
    steals.append(req["turn_id"])
    tm.release_busy("ag_minh", req["turn_id"])
    tm.acquire_busy("ag_minh", OTHER["team_id"], f"tu_s{len(steals)}", lease_s=0.15)
    await wait_until(lambda: False, timeout=0.3)
    return "Bản bị mất."

fake.say("ag_minh", "work", *([always_steal] * 6))
job = r.submit(T["team_id"], "Việc mất khoá lặp", mentions=["ag_minh"], as_job=True, client_msg_id="f8")["task_id"]
run(job_main())
task8 = ts.get_task(job)
check(f"F8 mất khoá lặp lại: chạy tối đa {TR.LEASE_REQUEUE_MAX + 1} lần rồi chặn việc (Không giới hạn vẫn không chạy mãi)",
      len(steals) == TR.LEASE_REQUEUE_MAX + 1 and task8["status"] != "team_running" and task8["status"] != "done",
      (len(steals), task8["status"]))

print(f"\n{len(fails)} FAIL" if fails else "\nALL OK")
raise SystemExit(1 if fails else 0)
