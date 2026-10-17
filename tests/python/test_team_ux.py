"""Nhóm chat team T5 (trang Nhóm gọn như app chat): phần server.

    python tests/run.py team_ux -v

Việc bị chặn vì hết lượt có MỘT nút giải quyết ("Cho thêm lượt": nâng đúng trần đã chạm rồi cho chạy tiếp), lý do chặn viết
bằng lời thường, số lần đã dùng hôm nay. Kho thật trên SQLite tạm, engine giả, không gọi model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-ux-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-ux-w-"))

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class Fake:
    def __init__(self):
        self.calls = []

    def engine_for(self, team, key, role):
        async def run_(req):
            self.calls.append(req)
            return {"text": f"{key} xong {len(self.calls)}"}
        return "fake", "fake", run_


_n = [0]


def world(label):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for,
                      agent_info=lambda root, key: {"slug": key, "name": key.title(), "system": ""})
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
    tm.create_team(str(d), label, "", sid, team_id=tid)
    for k in ("lan", "minh"):
        tm.add_member(tid, k, k)
    tm.set_leader(tid, "lan")
    return r, tm, ts, ss, fake, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


# ═════ Hết lượt trong ngày: Cho thêm lượt nâng trần ngày rồi chạy tiếp ═════
r, tm, ts, ss, fake, T = world("daily")
tm.set_caps(T["team_id"], {"daily_turns": 1})
run(r.run_replies(r.submit(T["team_id"], "Chào", client_msg_id="c1")))
job = r.submit(T["team_id"], "Viết bài", mentions=["minh"], as_job=True, client_msg_id="j1")["task_id"]
run(r.dispatch_once())
t = ts.get_task(job)
check("việc chặn vì hết lượt trong ngày, lý do bằng lời thường (không có chữ 'trần')",
      t["status"] == "team_blocked" and t["block_kind"] == "cap_reached" and "trần" not in t["block_reason"]
      and "hôm nay" in t["block_reason"], t["block_reason"])
out = r.extend_job(job)
check("Cho thêm lượt: nâng đúng trần ngày (+20), việc về hàng chờ", out and out["cap"] == "daily_turns"
      and out["value"] == 21 and tm.get(T["team_id"])["caps"]["daily_turns"] == 21
      and ts.get_task(job)["status"] == "team_queued", out)
check("Cho thêm lượt: có sự kiện và tin hệ thống nói rõ", any(e["kind"] == "caps_extended" for e in tm.events(T["team_id"]))
      and any(m["author_kind"] == "system" and "20" in m["content"]
              for m in ss.get_team_messages_page(T["session_id"], limit=50)["messages"]))
run(r.dispatch_once())
check("sau khi cho thêm lượt: việc chạy xong", ts.get_task(job)["status"] == "done")

# ═════ Hết lượt của việc: nâng trần lượt mỗi việc ═════
r, tm, ts, ss, fake, T = world("task")
tm.set_caps(T["team_id"], {"task_turns": 1})
job = r.submit(T["team_id"], "Việc nhiều bước", as_job=True, client_msg_id="j2")["task_id"]


async def planner(req):
    if req["role"] == "plan":
        return {"text": 'Chia.\n<!-- JAVIS_TEAM: {"op": "assign", "agent": "minh", "brief": "a"} -->'}
    return {"text": "Bài"}
r.engine_for = lambda team, key, role: ("fake", "fake", planner)
run(r.dispatch_once())
t = ts.get_task(job)
check("việc chặn vì hết lượt của việc", t["block_kind"] == "cap_reached"
      and t["block_reason"].startswith("Việc đã dùng hết số lần trả lời"), t["block_reason"])
out = r.extend_job(job)
check("Cho thêm lượt: nâng trần lượt mỗi việc (+6)", out and out["cap"] == "task_turns" and out["value"] == 7, out)
run(r.dispatch_once())
check("chạy tiếp tới xong", ts.get_task(job)["status"] == "done", ts.get_task(job)["status"])

# ═════ Review T5 C1: chặn vì trần bước thì bước bị từ chối được giữ lại; Cho thêm lượt thêm lại rồi chạy tới xong ═════
r, tm, ts, ss, fake, T = world("steps")
tm.set_caps(T["team_id"], {"task_steps": 2})


async def two_assign(req):
    if req["role"] == "plan":
        return {"text": 'Chia.\n<!-- JAVIS_TEAM: {"op": "assign", "agent": "minh", "brief": "a"} -->\n'
                        '<!-- JAVIS_TEAM: {"op": "assign", "agent": "lan", "brief": "b"} -->'}
    return {"text": "Phần " + req["role"]}
r.engine_for = lambda team, key, role: ("fake", "fake", two_assign)
job = r.submit(T["team_id"], "Việc hai người", as_job=True, client_msg_id="s1")["task_id"]
run(r.dispatch_once())
t = ts.get_task(job)
check("C1 kế hoạch giao hai người vượt trần 2 bước: chặn hết lượt", t["block_kind"] == "cap_reached"
      and t["block_reason"].startswith("Việc đã dùng hết"), t["block_reason"])
out = r.extend_job(job)
check("C1 Cho thêm lượt: nâng trần bước đủ chỗ cho hai bước bị từ chối (+4 trên số cần)", out and out["cap"] == "task_steps"
      and out["value"] == 3 + 4, out)
run(r.dispatch_once())
st = [(s["kind"], s["status"]) for s in tm.steps(job)]
check("C1 chạy tiếp tới xong: hai bước làm được thêm lại, có tổng hợp", ts.get_task(job)["status"] == "done"
      and st.count(("work", "done")) == 2 and ("synthesize", "done") in st, (ts.get_task(job)["status"], st))

# ═════ Review T5 I1: trần đã chạm không còn chặn nữa (sang ngày mới, chủ đã tự nâng) thì không nâng trần nào ═════
r, tm, ts, ss, fake, T = world("stale")
clock = {"t": time.time()}
r.clock = lambda: clock["t"]
tm.set_caps(T["team_id"], {"daily_turns": 1})
run(r.run_replies(r.submit(T["team_id"], "Chào", client_msg_id="d1")))
job = r.submit(T["team_id"], "Viết", mentions=["minh"], as_job=True, client_msg_id="d2")["task_id"]
run(r.dispatch_once())
check("I1 việc chặn vì hết lần trả lời hôm nay", ts.get_task(job)["block_kind"] == "cap_reached")
clock["t"] += 2 * 86400
before = dict(tm.get(T["team_id"])["caps"])
out = r.extend_job(job)
check("I1 hai ngày sau: Cho thêm lượt không nâng trần nào (kể cả trần bước), chỉ cho việc chạy tiếp",
      out is not None and out["cap"] is None and tm.get(T["team_id"])["caps"] == before
      and ts.get_task(job)["status"] == "team_queued"
      and not any(e["kind"] == "caps_extended" for e in tm.events(T["team_id"])), (out, tm.get(T["team_id"])["caps"]))

# ═════ Review T5 I2: trần bị hạ dưới số đã dùng: nâng từ số đã dùng, không phải từ trần ═════
r, tm, ts, ss, fake, T = world("below")
for i in range(3):
    run(r.run_replies(r.submit(T["team_id"], f"Tin {i}", client_msg_id=f"b{i}")))
tm.set_caps(T["team_id"], {"daily_turns": 1})
job = r.submit(T["team_id"], "Viết", mentions=["minh"], as_job=True, client_msg_id="b9")["task_id"]
run(r.dispatch_once())
out = r.extend_job(job)
check("I2 đã dùng 3, trần hạ còn 1: Cho thêm lượt đặt 3 + 20, việc chạy được ngay", out and out["value"] == 23, out)
run(r.dispatch_once())
check("I2 việc chạy tới xong, không chặn lại", ts.get_task(job)["status"] == "done", ts.get_task(job)["status"])

# ═════ Toàn quyền đặt số cho trần: nâng trần trong hộp cấp quyền (cả trần tối đa), không đụng trần nhóm ═════
r, tm, ts, ss, fake, T = world("auth")
r.grant_authority(T["team_id"], {"caps": {"daily_turns": 1}, "ceilings": {"daily_turns": 1}})
run(r.run_replies(r.submit(T["team_id"], "Chào", client_msg_id="a1")))
job = r.submit(T["team_id"], "Viết", mentions=["minh"], as_job=True, client_msg_id="a2")["task_id"]
run(r.dispatch_once())
check("Toàn quyền trần ngày 1: việc chặn hết lượt", ts.get_task(job)["block_kind"] == "cap_reached")
out = r.extend_job(job)
g = tm.active_authority(T["team_id"])["grant"]
check("Cho thêm lượt khi Toàn quyền: nâng trần trong hộp cấp quyền và trần tối đa, trần nhóm giữ nguyên",
      out["value"] == 21 and g["caps"]["daily_turns"] == 21 and g["ceilings"]["daily_turns"] == 21
      and tm.get(T["team_id"])["caps"]["daily_turns"] == 100, (out, g))
check("usage theo trần đang áp (Toàn quyền)", r.usage(T["team_id"])["cap"] == 21, r.usage(T["team_id"]))

# ═════ Không phải việc bị chặn vì hết lượt: không làm gì ═════
r, tm, ts, ss, fake, T = world("other")
job = r.submit(T["team_id"], "Việc", as_job=True, client_msg_id="j3")["task_id"]
check("việc không bị chặn hết lượt: Cho thêm lượt không làm gì", r.extend_job(job) is None
      and tm.get(T["team_id"])["caps"]["daily_turns"] == 100)

# ═════ Số lần đã dùng hôm nay ═════
r, tm, ts, ss, fake, T = world("usage")
run(r.run_replies(r.submit(T["team_id"], "Một", client_msg_id="u1")))
run(r.run_replies(r.submit(T["team_id"], "Hai", client_msg_id="u2")))
u = r.usage(T["team_id"])
check("số lần đã dùng hôm nay kèm giới hạn đang áp", u == {"today": 2, "cap": 100}, u)

# ═════ Lý do chặn bằng lời thường ═════
src = (ROOT / "server" / "team_runner.py").read_text(encoding="utf-8")
check("lý do chặn không còn chữ 'trần', 'Lượt lỗi', 'Server khởi động lại'",
      "Đã chạm trần" not in src and 'f"Lượt lỗi:' not in src and "Server khởi động lại khi bước" not in src)
check("tin hệ thống về quyền tự quyết bằng lời thường (không 'Toàn quyền', 'Quyền giới hạn', 'đặt trần')",
      "đã bật Toàn quyền" not in src and "Nhóm về Quyền giới hạn" not in src and "đã đặt trần" not in src)
r, tm, ts, ss, fake, T = world("authmsg")
r.grant_authority(T["team_id"], {"ceilings": {"daily_turns": 50}})
r.revoke_authority(T["team_id"])
sys_msgs = [m["content"] for m in ss.get_team_messages_page(T["session_id"], limit=50)["messages"] if m["author_kind"] == "system"]
check("bật rồi thu quyền tự quyết: hai tin hệ thống nói rõ", any("tự quyết" in s for s in sys_msgs)
      and any("thu lại" in s for s in sys_msgs), sys_msgs)

# ═════ Review b93c46bd #3: bản ghi chặn bị đẩy khỏi 500 sự kiện cuối của nhóm vẫn được tìm thấy theo việc ═════
r, tm, ts, ss, fake, T = world("cap500")
tm.set_caps(T["team_id"], {"task_steps": 2})
r.engine_for = lambda team, key, role: ("fake", "fake", two_assign)
job = r.submit(T["team_id"], "Việc hai người", as_job=True, client_msg_id="e1")["task_id"]
run(r.dispatch_once())
check("#3 chặn vì trần bước, giữ hai bước bị từ chối", ts.get_task(job)["block_kind"] == "cap_reached")
other = r.submit(T["team_id"], "Việc khác", as_job=True, client_msg_id="e2")["task_id"]
tm.log_event(T["team_id"], "cap_blocked", "host", None, {"task_id": other, "cap": "daily_turns", "specs": [], "continues": None})
for i in range(300):
    tm.set_pinned(T["team_id"], True)
    tm.set_pinned(T["team_id"], False)
check("#3 hơn 600 sự kiện khác sau lần chặn (đuôi 500 sự kiện không còn bản ghi)",
      not any(e["kind"] == "cap_blocked" and e["after"].get("task_id") == job for e in tm.events(T["team_id"], 500)))
rec = tm.cap_record(T["team_id"], job)
check("#3 kho tìm bản ghi chặn mới nhất của ĐÚNG việc đó, đủ hai bước bị từ chối",
      rec is not None and rec["cap"] == "task_steps" and len(rec["specs"]) == 2, rec)
check("#3 bản ghi của việc khác không lẫn sang", (tm.cap_record(T["team_id"], other) or {}).get("cap") == "daily_turns")
out = r.extend_job(job)
check("#3 Cho thêm lượt nâng trần bước", out and out["cap"] == "task_steps", out)
run(r.dispatch_once())
st = [(s["kind"], s["status"]) for s in tm.steps(job)]
check("#3 thêm lại đủ hai bước, việc chạy tới xong", ts.get_task(job)["status"] == "done"
      and st.count(("work", "done")) == 2, (ts.get_task(job)["status"], ts.get_task(job)["block_reason"], st))

# ═════ Review tích hợp 0.140.0: lời nhắc của MỌI lượt nhóm nói rõ lượt chỉ chữ, không có công cụ ═════
r, tm, ts, ss, fake, T = world("textonly")
r.agent_info = lambda root, key: {"slug": key, "name": key.title(),
                                  "system": "Bạn có toàn bộ bộ công cụ của hub, làm việc trong vault."}
run(r.run_replies(r.submit(T["team_id"], "Chào", client_msg_id="x1")))
job = r.submit(T["team_id"], "Viết", mentions=["minh"], as_job=True, client_msg_id="x2")["task_id"]
run(r.dispatch_once())
roles = {c["role"]: c["system"] for c in fake.calls}
# 0.194.0: chat replies keep the text-only note; a Work step of a job gets the tool note instead (its own toolkit).
check("lượt trả lời có đoạn chỉ chữ, đặt SAU lời nhắc của trợ lý (đè lời hứa bộ công cụ)",
      set(roles) >= {"leader_reply", "work"}
      and all(s.startswith("Bạn có toàn bộ bộ công cụ") and TR.TEXT_ONLY_NOTE in s and s.index(TR.TEXT_ONLY_NOTE) > 0
              for k, s in roles.items() if k not in TR.TOOL_ROLES),
      {k: v[-200:] for k, v in roles.items()})
check("lượt Làm của việc có đoạn CÓ công cụ thay đoạn chỉ chữ, đặt SAU lời nhắc của trợ lý",
      TR.WORK_TOOLS_NOTE in roles["work"] and TR.TEXT_ONLY_NOTE not in roles["work"]
      and roles["work"].index(TR.WORK_TOOLS_NOTE) > 0, roles["work"][-300:])
check("đoạn chỉ chữ nói rõ không có công cụ và gọi công cụ làm hỏng lượt", "không có công cụ" in TR.TEXT_ONLY_NOTE
      and "hỏng" in TR.TEXT_ONLY_NOTE)

# ═════ Review tích hợp 0.140.0: nhắc việc chặn quá 24 giờ chỉ một lần, kể cả khi nhóm có hơn 500 sự kiện sau đó ═════
r, tm, ts, ss, fake, T = world("remind")
notes_sent = []
r._notify = lambda team_id, text: notes_sent.append(text)
tm.set_caps(T["team_id"], {"daily_turns": 0})
job = r.submit(T["team_id"], "Việc chờ", mentions=["minh"], as_job=True, client_msg_id="r1")["task_id"]
run(r.dispatch_once())
check("việc chặn để thử nhắc", ts.get_task(job)["status"] == "team_blocked")
notes_sent.clear()   # bỏ tin báo lúc chặn, chỉ đếm tin nhắc
later = time.time() + 2 * 86400
check("nhắc lần đầu sau 24 giờ", r.remind_blocked(later) == 1 and len(notes_sent) == 1)
for i in range(300):
    tm.set_pinned(T["team_id"], True)
    tm.set_pinned(T["team_id"], False)
check("hơn 600 sự kiện sau đó: KHÔNG nhắc lại cùng lần chặn", r.remind_blocked(later + 3600) == 0 and len(notes_sent) == 1,
      notes_sent)

# ═════ Review tích hợp 0.140.0: việc nền của API nhóm được giữ tham chiếu tới khi xong (không bị dọn rác giữa chừng) ═════
import team_api  # noqa: E402


async def _spawn_probe():
    api = team_api.TeamApi(team_api.TeamApiDeps(
        brain_key=str, session_store=lambda: None, task_store=lambda: None, resonance_store=lambda: None,
        agents_meta=lambda root: [], agent_info=lambda root, key: None, engine_for=lambda *a: None))
    gate = asyncio.Event()

    async def job():
        await gate.wait()
    api._spawn(job())
    held = len(getattr(api, "_bg", ()))
    gate.set()
    await asyncio.sleep(0.01)
    return held, len(getattr(api, "_bg", ()))
held, after = run(_spawn_probe())
check("việc nền đang chạy nằm trong tập giữ tham chiếu, xong thì bỏ ra", held == 1 and after == 0, (held, after))

# ═════ Ghim nhóm lên đầu danh sách ═════
d = TEMP / "pin"
d.mkdir()
tm = team_store.TeamStore(d / "team.sqlite3")
ids = []
for i, nm in enumerate(["Cũ", "Giữa", "Mới"]):
    tid = team_store.new_team_id()
    tm.create_team("B", nm, "", f"s{i}", team_id=tid)
    ids.append(tid)
    time.sleep(0.01)
tm.touch(ids[2])
check("chưa ghim: mới cập nhật đứng đầu", [t["name"] for t in tm.list_teams("B")] == ["Mới", "Giữa", "Cũ"]
      and tm.get(ids[0])["pinned_at"] is None)
tm.set_pinned(ids[0], True)
rows = tm.list_teams("B")
check("ghim nhóm cũ: lên đầu trang đầu, có mốc ghim", [t["name"] for t in rows] == ["Cũ", "Mới", "Giữa"]
      and rows[0]["pinned_at"] is not None, [t["name"] for t in rows])
check("trang sau (con trỏ updated_at) không lặp nhóm đã ghim",
      [t["name"] for t in tm.list_teams("B", before=tm.get(ids[2])["updated_at"])] == ["Giữa"])
check("ghim ghi sự kiện", any(e["kind"] == "pinned" for e in tm.events(ids[0])))
tm.set_pinned(ids[0], False)
check("bỏ ghim: về đúng thứ tự cập nhật", [t["name"] for t in tm.list_teams("B")] == ["Mới", "Giữa", "Cũ"])

print(f"\n{'FAIL' if fails else 'PASS'} - test_team_ux: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
