"""Nhóm chat team T1, nhiệm vụ 5: bộ chạy nhóm (spec 2026-10-13-team-chat-design mục 7, 8, 9, 11.2, 12).

    python tests/run.py team_runner

Chỉ engine giả, không gọi model. Ca TC6 tới TC13, TC17 tới TC23 và khối JAVIS_TEAM sai khuôn (Review Focus 5).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-runner-")
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_store  # noqa: E402
import team_runner as TR  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    import json
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh"), "ag_hoa": ("hoa", "Hoa"), "ag_tu": ("tu", "Tú")}


class Fake:
    """Engine giả theo kịch bản: (agent_key, role) -> danh sách câu trả lời (chuỗi hay hàm async nhận req)."""

    def __init__(self):
        self.script = {}
        self.calls = []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        if agent_key in getattr(self, "boom", set()):
            raise RuntimeError("database is locked")

        async def run(req):
            self.calls.append(req)
            queue = self.script.get((agent_key, role)) or []
            ans = queue.pop(0) if queue else f"{agent_key} {role} xong"
            if isinstance(ans, Exception):
                raise ans
            if callable(ans):
                ans = await ans(req)
            return {"text": ans, "tokens_in": 11, "tokens_out": 7}
        return "fake", "fake-model", run

    def by(self, agent=None, role=None):
        return [c for c in self.calls if (agent is None or c["agent_key"] == agent) and (role is None or c["role"] == role)]


def world(name):
    d = STATE / name
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "sessions.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()
    published, inbox = [], []
    gone = set()

    def agent_info(brain, key):
        if key in gone or key not in AGENTS:
            return None
        slug, nm = AGENTS[key]
        return {"slug": slug, "name": nm, "system": f"Bạn là {nm}."}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info,
                      publish=published.append, notify=lambda team_id, text: inbox.append((team_id, text)))
    return ss, ts, tm, fake, r, published, inbox, gone


def make_team(tm, ss, name, members=("ag_lan", "ag_minh", "ag_hoa"), leader="ag_lan"):
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    t = tm.create_team("B", name, "mô tả " + name, sid, team_id=tid)
    for k in members:
        tm.add_member(tid, k, AGENTS[k][0])
    if leader:
        tm.set_leader(tid, leader)
    return tm.get(tid)


def msgs(ss, team):
    return ss.get_team_messages_page(team["session_id"], limit=200)["messages"]


def run(coro):
    return asyncio.run(coro)


# ---------- TC6 tới TC9: định tuyến tin trò chuyện ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("route")
T = make_team(tm, ss, "Ra mắt")
sub = r.submit(T["team_id"], "Chào cả nhóm", client_msg_id="c1")
check("TC6 tin không @: trưởng nhóm trả lời", sub["replies"] == ["ag_lan"] and sub["created"])
run(r.run_replies(sub))
check("TC6 đúng một lượt, của trưởng nhóm", [c["agent_key"] for c in fake.calls] == ["ag_lan"]
      and fake.calls[0]["role"] == "leader_reply")
last = msgs(ss, T)[-1]
check("TC6 câu trả lời có tác giả là agent", last["author_kind"] == "agent" and last["author_ref"] == "ag_lan"
      and last["reply_to"] == sub["message_id"])
check("lượt trò chuyện ghi sổ lượt có token, đã chốt", [(t["role"], t["status"], t["tokens_in"])
                                                         for t in tm.turns(T["team_id"])] == [("leader_reply", "ok", 11)])
check("đăng tin qua WS", any(e.get("type") == "team_message" and e.get("team_id") == T["team_id"] for e in pub))

N = make_team(tm, ss, "Không trưởng", leader=None)
s2 = r.submit(N["team_id"], "Có ai không", client_msg_id="c1")
run(r.run_replies(s2))
check("TC6 nhóm chưa có trưởng nhóm: 0 lượt, có ghi chú", s2["replies"] == [] and "no_leader" in s2["notes"]
      and len(fake.calls) == 1)

fake.calls.clear()
s3 = r.submit(T["team_id"], "Minh ơi", mentions=["ag_minh"], client_msg_id="c2")
run(r.run_replies(s3))
check("TC7 một @: chỉ người được @ trả lời", [c["agent_key"] for c in fake.calls] == ["ag_minh"]
      and fake.calls[0]["role"] == "member_reply")
fake.calls.clear()
fake.say("ag_minh", "member_reply", "Minh nói: số liệu tuần là 42")
# 0.260.0: several @ answer at the same time by default; the team's `reply_parallel` 0 keeps the old order.
tm.set_caps(T["team_id"], {"reply_parallel": 0})
s4 = r.submit(T["team_id"], "Hai bạn xem", mentions=["ag_minh", "ag_hoa"], client_msg_id="c3")
run(r.run_replies(s4))
check("TC7 lần lượt: đúng thứ tự @", [c["agent_key"] for c in fake.calls] == ["ag_minh", "ag_hoa"])
check("TC7 lần lượt: người sau thấy câu trả lời của người trước", "số liệu tuần là 42" in fake.calls[1]["prompt"])
tm.set_caps(T["team_id"], {"reply_parallel": 1})
before = len(msgs(ss, T))
try:
    r.submit(T["team_id"], "Đông quá", mentions=["ag_minh", "ag_hoa", "ag_lan", "ag_tu"], client_msg_id="c4")
    check("TC7 quá trần @: từ chối gửi", False)
except TR.TeamError as ex:
    check("TC7 quá trần @: từ chối gửi, nói rõ trần, không lưu tin", "3" in str(ex) and len(msgs(ss, T)) == before)
tm.remove_member(T["team_id"], "ag_hoa")
fake.calls.clear()
s5 = r.submit(T["team_id"], "Hai bạn", mentions=["ag_hoa", "ag_minh"], client_msg_id="c5")
run(r.run_replies(s5))
# 0.142.0: ghi chú là câu cho chủ đọc, KHÔNG kèm mã agent (mã có "_" làm khung soạn ẩn cả câu, chủ không thấy gì).
check("TC7 @ người đã rời: bỏ qua người đó, có ghi chú bằng tên, người hợp lệ vẫn trả lời",
      s5["replies"] == ["ag_minh"] and any("không còn trong nhóm" in n and "ag_hoa" not in n for n in s5["notes"]), s5["notes"])
tm.add_member(T["team_id"], "ag_hoa", "hoa")

fake.calls.clear()
fake.say("ag_lan", "leader_reply", "Để @Hoa @ag_hoa làm nhé")
run(r.run_replies(r.submit(T["team_id"], "Ai làm?", client_msg_id="c6")))
check("TC8 chữ @ trong câu trả lời của agent không đánh thức ai", [c["agent_key"] for c in fake.calls] == ["ag_lan"])

n_tasks = len(ts.team_queue(T["team_id"])["waiting"])
check("TC9 tin thường không tạo việc", n_tasks == 0)
fake.calls.clear()
dup = r.submit(T["team_id"], "Chào cả nhóm", client_msg_id="c1")
run(r.run_replies(dup))
check("TC9 gửi lại cùng client_msg_id: không thêm tin, không thêm lượt", dup["created"] is False
      and dup["replies"] == [] and fake.calls == [])
j1 = r.submit(T["team_id"], "Soạn kế hoạch ra mắt", as_job=True, client_msg_id="j1")
j1b = r.submit(T["team_id"], "Soạn kế hoạch ra mắt", as_job=True, client_msg_id="j1")
q = ts.team_queue(T["team_id"])
check("TC9 Giao việc tạo đúng một việc; gửi lại không tạo thêm", j1["task_id"] and j1b["task_id"] == j1["task_id"]
      and len(q["waiting"]) == 1 and j1["replies"] == [])

# Đề xuất việc của trưởng nhóm (D2): chỉ là thẻ, chủ bấm mới có việc
fake.say("ag_lan", "leader_reply", "Nên làm bản tin tuần." + directive(op="propose_job", title="Bản tin tuần",
                                                                       brief="Soạn bản tin tuần"))
sp = r.submit(T["team_id"], "Tuần này làm gì?", client_msg_id="c7")
run(r.run_replies(sp))
card = msgs(ss, T)[-1]
check("D2 đề xuất việc thành thẻ, chưa có việc", card["meta"].get("proposal", {}).get("title") == "Bản tin tuần"
      and "JAVIS_TEAM" not in card["content"] and len(ts.team_queue(T["team_id"])["waiting"]) == 1)
tid_p = r.accept_proposal(T["team_id"], card["id"])
check("D2 chủ bấm Tạo việc: một việc, bấm lại không thêm", tid_p and r.accept_proposal(T["team_id"], card["id"]) == tid_p
      and len(ts.team_queue(T["team_id"])["waiting"]) == 2)
ts.team_cancel(tid_p)
ts.team_cancel(j1["task_id"])

# ---------- TC10: giao chung ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("general")
T = make_team(tm, ss, "Ra mắt")
fake.say("ag_lan", "plan", "Chia việc." + directive(op="assign", agent="ag_minh", brief="Viết nội dung")
         + directive(op="assign", agent="hoa", brief="Làm ảnh"))
fake.say("ag_minh", "work", "Nội dung xong")
fake.say("ag_hoa", "work", "Ảnh xong")
fake.say("ag_lan", "synthesize", "Tổng hợp: nội dung và ảnh đã xong")
job = r.submit(T["team_id"], "Soạn kế hoạch ra mắt", as_job=True, client_msg_id="j1")
started = run(r.dispatch_once(wait=True))
check("TC10 điều phối nhận đúng việc", started == [job["task_id"]])
# 0.260.0: the two Work steps run side by side in one wave, so their order is free; plan first, synthesis last.
calls = [(c["agent_key"], c["role"]) for c in fake.calls]
check("TC10 thứ tự lượt: plan, hai bước Làm (cùng đợt), synthesize", len(calls) == 4 and calls[0] == ("ag_lan", "plan")
      and sorted(calls[1:3]) == [("ag_hoa", "work"), ("ag_minh", "work")] and calls[3] == ("ag_lan", "synthesize"), calls)
task = ts.get_task(job["task_id"])
check("TC10 việc xong, kết quả là bản tổng hợp", task["status"] == "done" and "Tổng hợp" in task["result"])
agent_msgs = [m for m in msgs(ss, T) if m["author_kind"] == "agent"]
check("TC10 mỗi tin có tác giả, nhãn việc, bước, vai", all(m["task_id"] == job["task_id"] and m["step_id"]
                                                          and m["meta"].get("role") for m in agent_msgs)
      and [m["author_ref"] for m in agent_msgs][0] == "ag_lan" and [m["author_ref"] for m in agent_msgs][-1] == "ag_lan"
      and sorted(m["author_ref"] for m in agent_msgs[1:3]) == ["ag_hoa", "ag_minh"])
check("TC10 bản tổng hợp gắn nhãn Kết quả việc", agent_msgs[-1]["meta"].get("job_result") is True
      and agent_msgs[-1]["meta"].get("applied") is True)
check("TC10 khối chỉ dẫn không lọt vào tin", all("JAVIS_TEAM" not in m["content"] for m in agent_msgs))
check("TC10 brief của bước đến đúng người làm", "Viết nội dung" in fake.by("ag_minh", "work")[0]["prompt"]
      and "Làm ảnh" in fake.by("ag_hoa", "work")[0]["prompt"])
check("TC10 bước cùng đợt được báo đồng đội đang làm song song", "Hoa" in fake.by("ag_minh", "work")[0]["prompt"]
      and "CÙNG LÚC" in fake.by("ag_hoa", "work")[0]["prompt"])
check("TC10 tổng hợp thấy kết quả các bước", "Nội dung xong" in fake.calls[3]["prompt"] and "Ảnh xong" in fake.calls[3]["prompt"])
check("TC10 lượt không cầm khoá bận sau khi xong", all(tm.busy_of(k) is None for k in AGENTS))

# Kế hoạch không giao ai: trưởng nhóm tự làm, việc xong với kết quả kế hoạch
fake.calls.clear()
fake.say("ag_lan", "plan", "Việc nhỏ, em làm luôn: xong rồi")
j2 = r.submit(T["team_id"], "Đặt tên chiến dịch", as_job=True, client_msg_id="j2")
run(r.dispatch_once(wait=True))
check("kế hoạch không giao ai: một lượt, việc xong", len(fake.calls) == 1 and ts.get_task(j2["task_id"])["status"] == "done")

# ---------- TC11: giao trực tiếp ----------
fake.calls.clear()
j3 = r.submit(T["team_id"], "Minh viết bài", mentions=["ag_minh"], as_job=True, client_msg_id="j3")
check("TC11 việc @ vẫn vào hàng chung", [t["id"] for t in ts.team_queue(T["team_id"])["waiting"]] == [j3["task_id"]])
run(r.dispatch_once(wait=True))
check("TC11 bắt đầu bằng work của người được @, trưởng nhóm không làm lại",
      [(c["agent_key"], c["role"]) for c in fake.calls] == [("ag_minh", "work")]
      and ts.get_task(j3["task_id"])["status"] == "done")
fake.calls.clear()
j4 = r.submit(T["team_id"], "Hai bạn làm", mentions=["ag_minh", "ag_hoa"], as_job=True, client_msg_id="j4")
run(r.dispatch_once(wait=True))
calls = [(c["agent_key"], c["role"]) for c in fake.calls]
check("TC11 nhiều @: mỗi người một work (cùng đợt, thứ tự tự do) rồi trưởng nhóm tổng hợp", len(calls) == 3
      and sorted(calls[:2]) == [("ag_hoa", "work"), ("ag_minh", "work")] and calls[2] == ("ag_lan", "synthesize"), calls)

# ---------- TC12: nhờ hỗ trợ, nhờ ngược, độ sâu, không tiến triển ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("help")
T = make_team(tm, ss, "Hỗ trợ", members=("ag_lan", "ag_minh", "ag_hoa", "ag_tu"))
fake.say("ag_minh", "work", "Cần số liệu." + directive(op="request_help", agent="ag_hoa", question="Doanh thu tháng 9?"),
         "Bài viết dùng doanh thu 120 triệu")
fake.say("ag_hoa", "help", "Doanh thu tháng 9 là 120 triệu")
j = r.submit(T["team_id"], "Minh viết báo cáo", mentions=["ag_minh"], as_job=True, client_msg_id="h1")
run(r.dispatch_once(wait=True))
check("TC12 A nhờ B, B trả lời, A làm tiếp", [(c["agent_key"], c["role"]) for c in fake.calls] == [
    ("ag_minh", "work"), ("ag_hoa", "help"), ("ag_minh", "work")])
check("TC12 câu hỏi đến B, câu trả lời của B đến lượt tiếp của A", "Doanh thu tháng 9?" in fake.calls[1]["prompt"]
      and "120 triệu" in fake.calls[2]["prompt"] and ts.get_task(j["task_id"])["status"] == "done")
fake.calls.clear()
fake.say("ag_minh", "work", "Hỏi Hoa." + directive(op="request_help", agent="ag_hoa", question="Ảnh?"), "Xong bài")
fake.say("ag_hoa", "help", "Hỏi lại Minh." + directive(op="request_help", agent="ag_minh", question="Ảnh nào?"))
j = r.submit(T["team_id"], "Minh làm bài 2", mentions=["ag_minh"], as_job=True, client_msg_id="h2")
run(r.dispatch_once(wait=True))
helpmsg = [m for m in msgs(ss, T) if m["task_id"] == j["task_id"] and m["meta"].get("role") == "help"][0]
check("TC12 B nhờ ngược A bị chặn, có ghi chú, không thêm lượt", [(c["agent_key"], c["role"]) for c in fake.calls] == [
    ("ag_minh", "work"), ("ag_hoa", "help"), ("ag_minh", "work")]
      and any("ngược" in n for n in helpmsg["meta"].get("notes", [])))
fake.calls.clear()
fake.say("ag_minh", "work", "Hỏi Hoa." + directive(op="request_help", agent="ag_hoa", question="q1"), "A xong")
fake.say("ag_hoa", "help", "Hỏi Tú." + directive(op="request_help", agent="ag_tu", question="q2"), "B xong")
fake.say("ag_tu", "help", "Hỏi Lan." + directive(op="request_help", agent="ag_lan", question="q3"))
j = r.submit(T["team_id"], "Minh làm bài 3", mentions=["ag_minh"], as_job=True, client_msg_id="h3")
run(r.dispatch_once(wait=True))
check("TC12 độ sâu 3 bị chặn: Tú không nhờ tiếp được", not fake.by("ag_lan")
      and [(c["agent_key"], c["role"]) for c in fake.calls] == [("ag_minh", "work"), ("ag_hoa", "help"), ("ag_tu", "help"),
                                                                ("ag_hoa", "help"), ("ag_minh", "work")])
fake.calls.clear()
fake.say("ag_minh", "work", "Hỏi Hoa." + directive(op="request_help", agent="ag_hoa", question="q"), "Hỏi Hoa." + directive(
    op="request_help", agent="ag_hoa", question="q"))
j = r.submit(T["team_id"], "Minh làm bài 4", mentions=["ag_minh"], as_job=True, client_msg_id="h4")
run(r.dispatch_once(wait=True))
t4 = ts.get_task(j["task_id"])
check("TC12 hai lượt liền của cùng bước ra cùng kết quả: chặn no_progress", t4["status"] == "team_blocked"
      and t4["block_kind"] == "no_progress", str((t4["status"], t4["block_kind"])))

# ---------- TC13: trần ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("caps")
T = make_team(tm, ss, "Trần")
tm.set_caps(T["team_id"], {"task_turns": 2})
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="a")
         + directive(op="assign", agent="ag_hoa", brief="b"))
j = r.submit(T["team_id"], "Việc lớn", as_job=True, client_msg_id="k1")
run(r.dispatch_once(wait=True))
t = ts.get_task(j["task_id"])
check("TC13 chạm trần lượt mỗi việc: cap_reached, không gọi thêm", t["status"] == "team_blocked"
      and t["block_kind"] == "cap_reached" and len(fake.calls) == 2 and tm.count_task_turns(j["task_id"]) == 2)
check("TC18 việc bị chặn có tin hộp thư", any(x[0] == T["team_id"] for x in inbox))
tm.set_caps(T["team_id"], {"task_turns": 12, "task_steps": 2})
fake.calls.clear()
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="a")
         + directive(op="assign", agent="ag_hoa", brief="b"))
j = r.submit(T["team_id"], "Việc lớn 2", as_job=True, client_msg_id="k2")
run(r.dispatch_once(wait=True))
t = ts.get_task(j["task_id"])
check("TC13 chạm trần bước mỗi việc: cap_reached", t["status"] == "team_blocked" and t["block_kind"] == "cap_reached"
      and len(tm.steps(j["task_id"])) <= 2)
tm.set_caps(T["team_id"], {"task_steps": 8, "daily_turns": len(tm.turns(T["team_id"]))})
fake.calls.clear()
sd = r.submit(T["team_id"], "Còn lượt không?", client_msg_id="k3")
run(r.run_replies(sd))
check("TC13 hết lượt ngày của nhóm: tin vẫn lưu, không có lượt", sd["created"] and sd["replies"] == []
      and "daily_cap" in sd["notes"] and fake.calls == [])
tm.set_caps(T["team_id"], {"daily_turns": 100})

# ---------- TC18: bị chặn rời chỗ chạy, hàng đi tiếp, nhắc sau 24 giờ ----------
fake.calls.clear()
inbox.clear()
fake.say("ag_minh", "work", RuntimeError("engine hỏng"))
ja = r.submit(T["team_id"], "Việc A", mentions=["ag_minh"], as_job=True, client_msg_id="b1")
jb = r.submit(T["team_id"], "Việc B", mentions=["ag_hoa"], as_job=True, client_msg_id="b2")
run(r.dispatch_once(wait=True))
run(r.dispatch_once(wait=True))
check("TC18 việc lỗi rời chỗ chạy, việc sau vẫn chạy", ts.get_task(ja["task_id"])["status"] == "team_blocked"
      and ts.get_task(ja["task_id"])["block_kind"] == "failed" and ts.get_task(jb["task_id"])["status"] == "done")
check("TC18 lượt lỗi sau mốc engine vẫn tính", [t["status"] for t in tm.turns(T["team_id"])
                                              if t["task_id"] == ja["task_id"]] == ["error"])
n0 = len(inbox)
n_blocked = len(ts.team_queue(T["team_id"])["blocked"])
check("TC18 nhắc sau 24 giờ: mỗi việc bị chặn một lần", r.remind_blocked(now=time.time() + 25 * 3600) == n_blocked
      and r.remind_blocked(now=time.time() + 26 * 3600) == 0 and len(inbox) == n0 + n_blocked and n_blocked >= 1)
check("tin nhắc xưng hô trung tính (bạn), không cố định anh", all("chờ bạn" in x[1] and " anh " not in x[1]
                                                                for x in inbox[n0:]), str(inbox[n0:]))
fake.say("ag_minh", "work", "Lần này được")
r.unblock(ja["task_id"], "retry")
run(r.dispatch_once(wait=True))
check("gỡ chặn chạy lại bước: việc xong", ts.get_task(ja["task_id"])["status"] == "done")

# ---------- TC19, TC20: bỏ thành viên, đổi trưởng nhóm, sửa, huỷ giữa chừng ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("late")
r.job_parallel = 1   # these cases time an event between two steps, so the steps run one by one (as before 0.260.0)
T = make_team(tm, ss, "Muộn")
TID = T["team_id"]


async def hoa_removes_minh(req):
    tm.remove_member(TID, "ag_minh")
    return "Phần của Hoa xong"


fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_hoa", brief="b")
         + directive(op="assign", agent="ag_minh", brief="a"),
         "Giao lại cho Hoa." + directive(op="assign", agent="ag_hoa", brief="a"))
fake.say("ag_hoa", "work", hoa_removes_minh)
j = r.submit(TID, "Việc 1", as_job=True, client_msg_id="l1")
run(r.dispatch_once(wait=True))
check("TC19 bỏ thành viên trước mốc engine: không gọi, hoàn lượt, trưởng nhóm phân công lại",
      not fake.by("ag_minh") and [(c["agent_key"], c["role"]) for c in fake.calls] == [
          ("ag_lan", "plan"), ("ag_hoa", "work"), ("ag_lan", "plan"), ("ag_hoa", "work"), ("ag_lan", "synthesize")]
      and ts.get_task(j["task_id"])["status"] == "done"
      and [t["status"] for t in tm.turns(TID) if t["agent_key"] == "ag_minh"] == ["refunded"],
      str([(c["agent_key"], c["role"]) for c in fake.calls]))
tm.add_member(TID, "ag_minh", "minh")
fake.calls.clear()


async def minh_leaves(req):
    tm.remove_member(TID, "ag_minh")
    return "Minh làm xong nhưng đã rời"


fake.say("ag_minh", "work", minh_leaves)
j = r.submit(TID, "Việc 2", mentions=["ag_minh"], as_job=True, client_msg_id="l2")
run(r.dispatch_once(wait=True))
late = [m for m in msgs(ss, T) if m["task_id"] == j["task_id"] and m["author_ref"] == "ag_minh"][0]
check("TC19 bỏ thành viên sau mốc engine: kết quả lưu, applied=0, có nhãn; việc trực tiếp vào assignee_removed",
      late["meta"]["applied"] is False and late["meta"]["status"] == "member_left"
      and ts.get_task(j["task_id"])["block_kind"] == "assignee_removed")
tm.add_member(TID, "ag_minh", "minh")
fake.calls.clear()


async def leader_swapped(req):
    tm.set_leader(TID, "ag_hoa")
    return "Chia." + directive(op="assign", agent="ag_minh", brief="a")


fake.say("ag_lan", "plan", leader_swapped)
fake.say("ag_hoa", "plan", "Hoa tự làm: xong")
j = r.submit(TID, "Việc 3", as_job=True, client_msg_id="l3")
run(r.dispatch_once(wait=True))
plan_old = [m for m in msgs(ss, T) if m["task_id"] == j["task_id"] and m["author_ref"] == "ag_lan"][0]
check("TC19 đổi trưởng nhóm giữa lượt điều phối: kế hoạch cũ không áp dụng, trưởng nhóm mới điều phối",
      plan_old["meta"]["applied"] is False and plan_old["meta"]["status"] == "leader_changed"
      and not fake.by("ag_minh") and fake.by("ag_hoa", "plan") and ts.get_task(j["task_id"])["status"] == "done"
      and any(e["kind"] == "coordinator_changed" for e in tm.events(TID)))
tm.set_leader(TID, None)
j = r.submit(TID, "Việc 4", as_job=True, client_msg_id="l4")
run(r.dispatch_once(wait=True))
check("TC19 không có trưởng nhóm: việc chung vào no_leader, không âm thầm mất",
      ts.get_task(j["task_id"])["block_kind"] == "no_leader")
jd = r.submit(TID, "Việc 5", mentions=["ag_minh"], as_job=True, client_msg_id="l5")
run(r.dispatch_once(wait=True))
check("TC19 không có trưởng nhóm: việc @ trực tiếp vẫn chạy", ts.get_task(jd["task_id"])["status"] == "done")
tm.set_leader(TID, "ag_lan")
check("chọn trưởng nhóm mới: việc no_leader về hàng", r.resume_no_leader(TID) == 1
      and ts.get_task(j["task_id"])["status"] == "team_queued")
ts.team_cancel(j["task_id"])
fake.calls.clear()


async def amended(req):
    ts.team_amend(req["task_id"], "thêm bản tiếng Anh")
    return "Bài theo yêu cầu cũ"


fake.say("ag_minh", "work", amended, "Bài theo yêu cầu mới")
j = r.submit(TID, "Việc 6", mentions=["ag_minh"], as_job=True, client_msg_id="l6")
run(r.dispatch_once(wait=True))
mm = [m for m in msgs(ss, T) if m["task_id"] == j["task_id"]]
check("TC20 sửa yêu cầu giữa bước: kết quả cũ applied=0 nhãn theo yêu cầu cũ, làm lại theo bản mới",
      mm[0]["meta"]["status"] == "old_revision" and mm[0]["meta"]["applied"] is False
      and "tiếng Anh" in fake.calls[1]["prompt"] and ts.get_task(j["task_id"])["result"] == "Bài theo yêu cầu mới")
fake.calls.clear()


async def cancelled(req):
    ts.team_cancel(req["task_id"])
    return "Xong nhưng đã huỷ"


fake.say("ag_lan", "plan", cancelled)
j = r.submit(TID, "Việc 7", as_job=True, client_msg_id="l7")
run(r.dispatch_once(wait=True))
mm = [m for m in msgs(ss, T) if m["task_id"] == j["task_id"]]
check("TC20 huỷ giữa bước: kết quả đến sau lưu với nhãn, không chạy thêm", len(fake.calls) == 1
      and mm[-1]["meta"]["status"] == "late_cancelled" and ts.get_task(j["task_id"])["status"] == "cancelled")

# ---------- TC21, TC22: cùng agent ở hai nhóm, không lẫn ngữ cảnh ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("busy")
X = make_team(tm, ss, "Nhóm X")
Y = make_team(tm, ss, "Nhóm Y", members=("ag_hoa", "ag_minh"), leader="ag_hoa")
ss.append_team_message(Y["session_id"], "user", "BÍ MẬT NHÓM Y", author_kind="owner", client_msg_id="y0")
private = ss.create_session(brain="B", channel="web")
ss.append_message(private, "user", "CHUYỆN RIÊNG CỦA CHỦ")
gate = asyncio.Event()
order = []


async def slow_minh(req):
    order.append(("start", req["team_id"]))
    await gate.wait()
    order.append(("end", req["team_id"]))
    return "Minh xong ở " + req["team_id"]


async def fast_minh(req):
    order.append(("start", req["team_id"]))
    return "Minh xong ở " + req["team_id"]


fake.say("ag_minh", "work", slow_minh, fast_minh)


async def both():
    r.submit(X["team_id"], "Việc X", mentions=["ag_minh"], as_job=True, client_msg_id="x1")
    await r.dispatch_once(wait=False)
    await asyncio.sleep(0.05)
    r.submit(Y["team_id"], "Việc Y", mentions=["ag_minh"], as_job=True, client_msg_id="y1")
    await r.dispatch_once(wait=False)
    # Wait for the condition, not a fixed time: on a loaded machine Y's turn needs several thread hops to start.
    for _ in range(300):
        if ("start", Y["team_id"]) in order:
            break
        await asyncio.sleep(0.01)
    waiting = r.busy_view(Y["team_id"])
    gate.set()
    await r.wait_jobs()
    return waiting


waiting = run(both())
# 0.257.0: the busy lock is per thread (agent + team); 0.260.0: tool turns share a slot of the folder, TOOL_SLOTS wide.
# So Minh's Work step in Y starts while the one in X is still running.
check("TC21 cùng agent làm việc ở hai nhóm cùng lúc", order[:2] == [("start", X["team_id"]), ("start", Y["team_id"])]
      and ("end", X["team_id"]) in order, str(order))
check("TC21 khoá bận theo mạch: nhóm Y không thấy agent bị nhóm X giữ", waiting == {}, str(waiting))
rx = [m for m in msgs(ss, X) if m["author_kind"] == "agent"]
ry = [m for m in msgs(ss, Y) if m["author_kind"] == "agent"]
check("TC21 mỗi kết quả về đúng nhóm", [m["content"] for m in rx] == ["Minh xong ở " + X["team_id"]]
      and [m["content"] for m in ry] == ["Minh xong ở " + Y["team_id"]])
px = [c for c in fake.calls if c["team_id"] == X["team_id"]][0]
check("TC22 lời nhắc nhóm X không chứa tin nhóm Y, chat riêng", "BÍ MẬT NHÓM Y" not in px["prompt"] + px["system"]
      and "CHUYỆN RIÊNG" not in px["prompt"] + px["system"] and "Nhóm X" in px["prompt"])
check("TC21 mạch thành viên riêng theo nhóm", px["thread"] == f"teammate:{X['team_id']}:ag_minh")
# 0.194.0: chat replies, plans and summaries stay text only; a Work/Help step of a job gets the member's own toolkit.
check("TC23 lượt trò chuyện, lập kế hoạch, tổng hợp chỉ chữ: không có công cụ (không javis_goal)",
      all(c.get("tools") == [] and not c.get("tool_turn") for c in fake.calls if c["role"] not in TR.TOOL_ROLES))
check("TC23 lượt Làm/Hỗ trợ của việc có bộ công cụ của trợ lý",
      all(c.get("tools") is None and c.get("tool_turn") for c in fake.calls if c["role"] in TR.TOOL_ROLES))

tm.set_caps(X["team_id"], {"busy_wait_s": 0.05})
fake.say("ag_minh", "work", "không bao giờ tới")
# A hold on the whole agent (agent pulse, review) still blocks every team turn of that agent (0.257.0).
check("dòng giữ trọn agent chặn lượt nhóm", tm.acquire_busy("ag_minh", "pulse", "tu_pulse", lease_s=60))
check("nhóm X thấy agent đang bị giữ trọn", r.busy_view(X["team_id"]).get("ag_minh") == "pulse")


async def long_wait():
    jx2 = r.submit(X["team_id"], "Chờ Minh", mentions=["ag_minh"], as_job=True, client_msg_id="x2")
    await r.dispatch_once(wait=False)
    await r.wait_jobs()
    return jx2


jx2 = run(long_wait())
tm.release_busy("ag_minh", "tu_pulse")
tx2 = ts.get_task(jx2["task_id"])
check("chờ khoá bận quá hạn: agent_busy_long, lượt hoàn", tx2["block_kind"] == "agent_busy_long"
      and [t["status"] for t in tm.turns(X["team_id"]) if t["task_id"] == jx2["task_id"]] == ["refunded"])

# ---------- 0.257.0: cùng agent trả lời ở hai nhóm cùng lúc; cùng nhóm vẫn lần lượt; trần theo engine ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("parallel")
X = make_team(tm, ss, "Song song X", members=("ag_lan", "ag_minh"), leader="ag_lan")
Y = make_team(tm, ss, "Song song Y", members=("ag_hoa", "ag_minh"), leader="ag_hoa")
live = {"now": 0, "peak": 0}


def gated(gate):
    async def answer(req):
        live["now"] += 1
        live["peak"] = max(live["peak"], live["now"])
        try:
            await asyncio.wait_for(gate.wait(), 2)
        finally:
            live["now"] -= 1
        return "Minh trả lời ở " + req["team_id"]
    return answer


async def two_teams():
    gate = asyncio.Event()
    fake.say("ag_minh", "member_reply", gated(gate), gated(gate))
    sx = r.submit(X["team_id"], "Minh ơi bên X", mentions=["ag_minh"], client_msg_id="px1")
    sy = r.submit(Y["team_id"], "Minh ơi bên Y", mentions=["ag_minh"], client_msg_id="py1")
    tasks = [asyncio.ensure_future(r.run_replies(sx)), asyncio.ensure_future(r.run_replies(sy))]
    for _ in range(100):
        if live["now"] == 2:
            break
        await asyncio.sleep(0.01)
    seen = r.busy_view(Y["team_id"])
    gate.set()
    outs = await asyncio.gather(*tasks)
    return outs, seen

outs, seen = run(two_teams())
check("0.257.0 cùng agent trả lời ở hai nhóm CÙNG LÚC", live["peak"] == 2, live)
check("0.257.0 hai lượt đều đăng tin", all(o and o[0].get("message_id") for o in outs), outs)
check("0.257.0 nhóm Y không báo agent bận ở nhóm X", seen == {}, seen)
check("0.257.0 lượt xong thì không còn dòng khoá nào", tm.busy_of("ag_minh") is None)

live.update(now=0, peak=0)


async def same_team():
    gate = asyncio.Event()
    fake.say("ag_minh", "member_reply", gated(gate), gated(gate))
    s1 = r.submit(X["team_id"], "Câu một", mentions=["ag_minh"], client_msg_id="px2")
    s2 = r.submit(X["team_id"], "Câu hai", mentions=["ag_minh"], client_msg_id="px3")
    tasks = [asyncio.ensure_future(r.run_replies(s1)), asyncio.ensure_future(r.run_replies(s2))]
    for _ in range(300):   # first turn started (condition, not a fixed time), then give a second turn room to start
        if live["now"] >= 1:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.2)
    first = live["now"]
    gate.set()
    await asyncio.gather(*tasks)
    return first

check("0.257.0 cùng agent trong CÙNG nhóm vẫn một lượt một lúc (một mạch)", run(same_team()) == 1 and live["peak"] == 1,
      live)

live.update(now=0, peak=0)
r.engine_slots_api = 1


async def one_slot():
    gate = asyncio.Event()
    fake.say("ag_lan", "leader_reply", gated(gate))
    fake.say("ag_hoa", "leader_reply", gated(gate))
    sx = r.submit(X["team_id"], "Lan ơi", client_msg_id="px4")
    sy = r.submit(Y["team_id"], "Hoa ơi", client_msg_id="py4")
    tasks = [asyncio.ensure_future(r.run_replies(sx)), asyncio.ensure_future(r.run_replies(sy))]
    for _ in range(300):   # first turn started (condition, not a fixed time), then give a second turn room to start
        if live["now"] >= 1:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.2)
    first = live["now"]
    gate.set()
    outs = await asyncio.gather(*tasks)
    return first, outs

first, outs = run(one_slot())
check("0.257.0 trần theo engine: một chỗ thì hai nhóm lần lượt, không mất lượt nào",
      first == 1 and live["peak"] == 1 and all(o and o[0].get("message_id") for o in outs), (first, live, outs))
lim = {row["key"]: row["value"] for row in r.limits_table(X["team_id"])}
check("0.257.0 bảng giới hạn có trần theo engine và số nhóm song song",
      lim.get("engine_slots_api") == 1 and lim.get("engine_slots_cli") == TR.ENGINE_SLOTS_CLI
      and lim.get("max_parallel_teams") == TR.MAX_PARALLEL_TEAMS, lim)
check("0.257.0 engine gói đăng ký dùng trần CLI, engine khác dùng trần API",
      r.slots_for("anthropic-cli") == TR.ENGINE_SLOTS_CLI and r.slots_for("openrouter") == 1)

# ---------- TC20: huỷ việc khi lượt đang gọi engine ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("cancel")
T = make_team(tm, ss, "Huỷ")


async def never(req):
    await asyncio.Event().wait()


fake.say("ag_minh", "work", never)
jq = r.submit(T["team_id"], "Việc dài", mentions=["ag_minh"], as_job=True, client_msg_id="q1")


async def cancel_mid_turn():
    await r.dispatch_once(wait=False)
    # Chờ tới khi lượt ĐANG ở engine (không ngủ một khoảng cố định: I/O ở luồng phụ, máy bận thì lâu hơn 50 ms).
    for _ in range(500):
        if fake.by("ag_minh"):
            break
        await asyncio.sleep(0.01)
    prev = r.cancel_job(jq["task_id"])
    await r.wait_jobs()
    return prev


prev = run(cancel_mid_turn())
st = tm.steps(jq["task_id"])
check("TC20 huỷ giữa lượt: ngắt lượt, lượt tính một lần (interrupted), bước huỷ, nhả khoá, không đăng kết quả",
      prev == "team_running" and ts.get_task(jq["task_id"])["status"] == "cancelled"
      and [t["status"] for t in tm.turns(T["team_id"])] == ["interrupted"] and [s["status"] for s in st] == ["cancelled"]
      and tm.busy_of("ag_minh") is None and not [m for m in msgs(ss, T) if m["author_kind"] == "agent"])
check("huỷ việc chờ (không chạy): trả trạng thái trước", r.cancel_job(r.submit(
    T["team_id"], "Việc chờ", as_job=True, client_msg_id="q2")["task_id"]) == "team_queued")

# ---------- TC17: restart ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("restart")
T = make_team(tm, ss, "Restart")
j1 = r.submit(T["team_id"], "Trước mốc", mentions=["ag_minh"], as_job=True, client_msg_id="r1")
ts.claim_team_next(T["team_id"], "old-worker")
r.start_job_steps(j1["task_id"])
st1 = tm.next_queued_step(j1["task_id"])
tm.claim_step(st1["step_id"])
tu1 = tm.reserve_turn(T["team_id"], j1["task_id"], st1["step_id"], "ag_minh", "work")
tm.acquire_busy("ag_minh", T["team_id"], tu1)
rep = r.recover()
check("TC17 restart trước mốc engine: hoàn lượt, bước về chờ, việc tiếp tục", tm.turn(tu1)["status"] == "refunded"
      and tm.step(st1["step_id"])["status"] == "queued" and j1["task_id"] in rep["resumed"]
      and tm.busy_of("ag_minh") is None)
run(r.resume_jobs(rep["resumed"]))
check("TC17 việc tiếp tục chạy xong", ts.get_task(j1["task_id"])["status"] == "done")
j2 = r.submit(T["team_id"], "Sau mốc", mentions=["ag_hoa"], as_job=True, client_msg_id="r2")
ts.claim_team_next(T["team_id"], "old-worker")
r.start_job_steps(j2["task_id"])
st2 = tm.next_queued_step(j2["task_id"])
tm.claim_step(st2["step_id"])
tu2 = tm.reserve_turn(T["team_id"], j2["task_id"], st2["step_id"], "ag_hoa", "work")
tm.mark_engine(tu2, "fake", "fake-model")
fake.calls.clear()
rep = r.recover()
check("TC17 restart sau mốc engine: lượt interrupted tính một lần, việc chặn interrupted, không tự chạy lại",
      tm.turn(tu2)["status"] == "interrupted" and ts.get_task(j2["task_id"])["block_kind"] == "interrupted"
      and tm.step(st2["step_id"])["status"] == "interrupted" and fake.calls == [])

# ---------- Review Focus 5: khối JAVIS_TEAM sai khuôn ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("badops")
T = make_team(tm, ss, "Khối sai")
fake.say("ag_lan", "plan", "Chia.\n<!-- JAVIS_TEAM: {hỏng -->" + directive(op="fly") + directive(
    op="peter_feedback_placeholder_removed", message_id=1, note="x") + directive(
    op="assign", agent="ag_nguoi_ngoai", brief="x") + directive(op="assign", agent="ag_minh", brief="ok"))
j = r.submit(T["team_id"], "Việc", as_job=True, client_msg_id="z1")
run(r.dispatch_once(wait=True))
plan = [m for m in msgs(ss, T) if m["meta"].get("role") == "plan"][0]
notes = " ".join(plan["meta"].get("notes", []))
# Pilot 2026-10-16 (0.171.3): tên lệnh model tự bịa không chép vào ghi chú cho chủ đọc; hai lệnh lạ chỉ một dòng.
check("khối hỏng, op lạ, giao người ngoài nhóm: bỏ op, ghi chú; op đúng vẫn chạy",
      "JSON" in notes and "ag_nguoi_ngoai" in notes and "fly" not in notes and "peter_feedback" not in notes
      and plan["meta"].get("notes", []).count(TR.UNKNOWN_OP_NOTE) == 1
      and [(c["agent_key"], c["role"]) for c in fake.calls] == [("ag_lan", "plan"), ("ag_minh", "work")]
      and "JAVIS_TEAM" not in plan["content"])
fake.calls.clear()
fake.say("ag_minh", "member_reply", "Giao luôn." + directive(op="assign", agent="ag_hoa", brief="x"))
run(r.run_replies(r.submit(T["team_id"], "Minh?", mentions=["ag_minh"], client_msg_id="z2")))
check("lượt trò chuyện không được giao việc hay nhờ người khác", len(fake.calls) == 1
      and not ts.team_queue(T["team_id"])["waiting"])

# ---------- Sửa sau review cuối T1 ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("review")
T = make_team(tm, ss, "Review")
TID = T["team_id"]
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="minh", brief="a")
         + directive(op="assign", agent="Hoa", brief="b"))
j = r.submit(TID, "Việc tên hiển thị", as_job=True, client_msg_id="v1")
run(r.dispatch_once(wait=True))
check("review I1: giao theo tên hiển thị (khác hoa thường) vẫn tới đúng người",
      [(c["agent_key"], c["role"]) for c in fake.calls][0] == ("ag_lan", "plan")
      and sorted((c["agent_key"], c["role"]) for c in fake.calls[1:3]) == [("ag_hoa", "work"), ("ag_minh", "work")],
      str([(c["agent_key"], c["role"]) for c in fake.calls]))
fake.calls.clear()
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="Người lạ", brief="a"))
j = r.submit(TID, "Việc giao người lạ", as_job=True, client_msg_id="v2")
run(r.dispatch_once(wait=True))
tj = ts.get_task(j["task_id"])
check("review I1: kế hoạch có lệnh giao mà mọi lệnh đều bị bỏ thì việc bị chặn, không báo xong",
      tj["status"] == "team_blocked" and tj["block_kind"] == "failed", str((tj["status"], tj["block_kind"])))
ts.team_cancel(j["task_id"])

fake.calls.clear()


async def amend_mid(req):
    ts.team_amend(req["task_id"], "thêm bản tiếng Anh")
    return "Minh bản cũ"


fake.say("ag_minh", "work", amend_mid, "Minh bản mới")
fake.say("ag_hoa", "work", "Hoa bản mới")
j = r.submit(TID, "Hai bạn làm", mentions=["ag_minh", "ag_hoa"], as_job=True, client_msg_id="v3")
run(r.dispatch_once(wait=True))
done_rev2 = sorted(s["agent_key"] for s in tm.steps(j["task_id"])
                   if s["kind"] == "work" and s["status"] == "done" and s["job_revision"] == 2)
check("review I2: sửa yêu cầu việc @ nhiều người: mọi người được giao đều làm lại theo bản mới",
      done_rev2 == ["ag_hoa", "ag_minh"] and ts.get_task(j["task_id"])["status"] == "done", str(done_rev2))

fake.calls.clear()


async def pause_in_plan(req):
    tm.update(TID, status="paused")
    return "Chia." + directive(op="assign", agent="ag_minh", brief="a")


fake.say("ag_lan", "plan", pause_in_plan)
j = r.submit(TID, "Việc tạm dừng nhanh", as_job=True, client_msg_id="v4")


async def pause_then_resume():
    await r.dispatch_once(wait=False)
    for _ in range(50):
        await asyncio.sleep(0.02)
        if all(t.done() for t in r._jobs.values()):
            break
    tm.update(TID, status="active")
    await r.resume_team(TID)
    await r.wait_jobs()


run(pause_then_resume())
check("review I3: tạm dừng rồi tiếp tục ngay: việc chạy tiếp tới xong, không kẹt",
      ts.get_task(j["task_id"])["status"] == "done", ts.get_task(j["task_id"])["status"])

fake.boom = {"ag_hoa"}
j = r.submit(TID, "Hoa làm", mentions=["ag_hoa"], as_job=True, client_msg_id="v5")
run(r.dispatch_once(wait=True))
tj = ts.get_task(j["task_id"])
hoa_turns = [t["status"] for t in tm.turns(TID) if t["task_id"] == j["task_id"]]
check("review I4: lỗi bất ngờ trước mốc engine: hoàn lượt, việc bị chặn failed, bước không treo running",
      tj["status"] == "team_blocked" and tj["block_kind"] == "failed" and hoa_turns == ["refunded"]
      and all(s["status"] != "running" for s in tm.steps(j["task_id"])), str((tj["status"], hoa_turns)))
fake.boom = set()
ts.team_cancel(j["task_id"])

fake.calls.clear()
sp = r.submit(TID, "Ai đó trả lời", mentions=["ag_minh", "ag_hoa"], client_msg_id="v6")
tm.update(TID, status="paused")
run(r.run_replies(sp))
check("review: nhóm tạm dừng sau khi gửi: lượt trả lời chưa chạy thì không chạy, không tốn lượt",
      fake.calls == [] and not [t for t in tm.turns(TID) if t["role"] == "member_reply" and t["status"] != "refunded"])
tm.update(TID, status="active")

fake.say("ag_minh", "work", "Hỏi Hoa." + directive(op="request_help", agent="ag_hoa", question="q"), "Hỏi Hoa."
         + directive(op="request_help", agent="ag_hoa", question="q"), "Lần này có kết quả")
j = r.submit(TID, "Minh lặp", mentions=["ag_minh"], as_job=True, client_msg_id="v7")
run(r.dispatch_once(wait=True))
np_step = [s for s in tm.steps(j["task_id"]) if s["note"] and "tiến triển" in s["note"]]
check("review: bước không tiến triển không được áp dụng, thành bước lỗi để Chạy lại",
      ts.get_task(j["task_id"])["block_kind"] == "no_progress" and np_step and np_step[0]["status"] == "failed"
      and np_step[0]["applied"] is False, str(np_step))
r.unblock(j["task_id"], "retry")
run(r.dispatch_once(wait=True))
check("review: Chạy lại sau không tiến triển: chạy lại bước, việc xong với kết quả mới",
      ts.get_task(j["task_id"])["status"] == "done" and ts.get_task(j["task_id"])["result"] == "Lần này có kết quả",
      ts.get_task(j["task_id"])["result"])


async def lock_leak():
    tm.acquire_busy("ag_tu", "tm_khac", "tu_khac", lease_s=60)
    t = asyncio.ensure_future(r._acquire(dict(T, caps=dict(T["caps"], busy_wait_s=5)), "ag_tu", "tu_x"))
    await asyncio.sleep(0.1)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
    return r._lock_for(tm.busy_slot("ag_tu", T["team_id"])).locked()


check("review: huỷ lúc đang chờ khoá bận trong kho không giữ khoá trong tiến trình", run(lock_leak()) is False)
tm.release_busy("ag_tu", "tu_khac")

# ---------- 0.260.0: trả lời song song trong một nhóm, bước Làm chạy theo đợt ----------
ss, ts, tm, fake, r, pub, inbox, gone = world("wave")
T = make_team(tm, ss, "Đợt")
TID = T["team_id"]
live = {"now": 0, "peak": 0}


def slow(text, gate=None):
    async def answer(req):
        live["now"] += 1
        live["peak"] = max(live["peak"], live["now"])
        try:
            if gate is not None:
                await asyncio.wait_for(gate.wait(), 2)
            else:
                await asyncio.sleep(0.1)
        finally:
            live["now"] -= 1
        return text
    return answer


fake.say("ag_minh", "member_reply", slow("Minh trả lời"))
fake.say("ag_hoa", "member_reply", slow("Hoa trả lời"))
s1 = r.submit(TID, "Hai bạn xem giúp", mentions=["ag_minh", "ag_hoa"], client_msg_id="w1")
outs = run(r.run_replies(s1))
check("0.260.0 nhiều @ trong một tin: trả lời CÙNG LÚC", live["peak"] == 2 and len(outs) == 2, (live, outs))
check("0.260.0 cả hai lượt có kết cục done", [x["status"] for x in tm.replies_of(TID, s1["message_id"])] == ["done", "done"],
      tm.replies_of(TID, s1["message_id"]))

live.update(now=0, peak=0)


async def cancel_replies():
    gate = asyncio.Event()
    fake.say("ag_minh", "member_reply", slow("không tới", gate))
    fake.say("ag_hoa", "member_reply", slow("không tới", gate))
    sub = r.submit(TID, "Rồi huỷ", mentions=["ag_minh", "ag_hoa"], client_msg_id="w2")
    t = asyncio.ensure_future(r.run_replies(sub))
    for _ in range(100):
        if live["now"] == 2:
            break
        await asyncio.sleep(0.01)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
    return sub

sub = run(cancel_replies())
rows = tm.replies_of(TID, sub["message_id"])
check("0.260.0 huỷ giữa lúc trả lời song song: mọi lượt thành lỗi có Thử lại, không treo",
      [x["status"] for x in rows] == ["error", "error"] and all(x["reason"] == "interrupted" for x in rows), rows)
check("0.260.0 huỷ xong không còn dòng khoá bận", tm.busy_of("ag_minh") is None and tm.busy_of("ag_hoa") is None)

# Một bước của đợt lỗi: bước kia vẫn được áp dụng; Chạy lại chỉ chạy lại bước lỗi, rồi tổng hợp đủ hai kết quả.
fake.calls.clear()
live.update(now=0, peak=0)
# The failing step comes FIRST in the wave, so this also checks that clean results are applied before the failure.
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_hoa", brief="phần B")
         + directive(op="assign", agent="ag_minh", brief="phần A"))
fake.say("ag_minh", "work", slow("Phần A xong"))
fake.say("ag_hoa", "work", RuntimeError("engine hỏng"))
fake.say("ag_hoa", "work", "Phần B xong")
fake.say("ag_lan", "synthesize", "Tổng hợp A và B")
j = r.submit(TID, "Việc chia đôi", as_job=True, client_msg_id="w3")
run(r.dispatch_once(wait=True))
steps = {(st["agent_key"], st["kind"]): st for st in tm.steps(j["task_id"])}
check("0.260.0 đợt có một bước lỗi: việc dừng failed", ts.get_task(j["task_id"])["block_kind"] == "failed")
check("0.260.0 bước tốt cùng đợt vẫn được áp dụng, không thành đến muộn",
      steps[("ag_minh", "work")]["status"] == "done" and steps[("ag_minh", "work")]["applied"] is True, steps)
r.unblock(j["task_id"], "retry")
run(r.dispatch_once(wait=True))
check("0.260.0 Chạy lại: chỉ bước lỗi chạy lại, việc xong bằng bản tổng hợp hai kết quả",
      ts.get_task(j["task_id"])["status"] == "done" and len(fake.by("ag_minh", "work")) == 1
      and len(fake.by("ag_hoa", "work")) == 2 and "Phần A xong" in fake.by("ag_lan", "synthesize")[0]["prompt"]
      and "Phần B xong" in fake.by("ag_lan", "synthesize")[0]["prompt"], ts.get_task(j["task_id"]))

# Hai bước cùng đợt đều lỗi: bước dừng việc chờ Chạy lại, bước kia về hàng chờ (không mất), Chạy lại thì cả hai làm lại.
fake.calls.clear()
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="phần C")
         + directive(op="assign", agent="ag_hoa", brief="phần D"))
fake.say("ag_minh", "work", RuntimeError("hỏng 1"), "Phần C xong")
fake.say("ag_hoa", "work", RuntimeError("hỏng 2"), "Phần D xong")
fake.say("ag_lan", "synthesize", "Tổng hợp C và D")
j = r.submit(TID, "Việc hai lỗi", as_job=True, client_msg_id="w4")
run(r.dispatch_once(wait=True))
st = [x for x in tm.steps(j["task_id"]) if x["kind"] == "work"]
check("0.260.0 hai bước lỗi: một bước failed, bước kia về hàng chờ",
      sorted(x["status"] for x in st) == ["failed", "queued"] and ts.get_task(j["task_id"])["status"] == "team_blocked",
      [(x["agent_key"], x["status"]) for x in st])
r.unblock(j["task_id"], "retry")
run(r.dispatch_once(wait=True))
synth = fake.by("ag_lan", "synthesize")
check("0.260.0 Chạy lại sau hai lỗi: cả hai phần làm lại, tổng hợp đủ", ts.get_task(j["task_id"])["status"] == "done"
      and synth and "Phần C xong" in synth[0]["prompt"] and "Phần D xong" in synth[0]["prompt"],
      (ts.get_task(j["task_id"]), [(c["agent_key"], c["role"]) for c in fake.calls]))

# Huỷ việc giữa đợt: mọi lượt đang chạy bị ngắt, việc huỷ.
fake.calls.clear()
live.update(now=0, peak=0)


async def cancel_wave():
    gate = asyncio.Event()
    fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="E")
             + directive(op="assign", agent="ag_hoa", brief="F"))
    fake.say("ag_minh", "work", slow("không tới", gate))
    fake.say("ag_hoa", "work", slow("không tới", gate))
    jj = r.submit(TID, "Việc bị huỷ giữa đợt", as_job=True, client_msg_id="w5")
    await r.dispatch_once(wait=False)
    for _ in range(200):
        if live["now"] == 2:
            break
        await asyncio.sleep(0.01)
    peak = live["peak"]
    r.cancel_job(jj["task_id"], "chủ huỷ")
    await r.wait_jobs()
    return jj, peak

jj, peak = run(cancel_wave())
check("0.260.0 hai bước Làm của một việc chạy cùng lúc", peak == 2, peak)
check("0.260.0 huỷ giữa đợt: việc huỷ, hai lượt đang chạy đều bị ngắt và tính một lần",
      ts.get_task(jj["task_id"])["status"] == "cancelled"
      and sorted(t["status"] for t in tm.turns(TID) if t["task_id"] == jj["task_id"] and t["role"] == "work")
      == ["interrupted", "interrupted"], [t["status"] for t in tm.turns(TID) if t["task_id"] == jj["task_id"]])
check("0.260.0 huỷ xong không còn dòng khoá bận", all(tm.busy_of(k) is None for k in AGENTS))

# JAVIS_TEAM_JOB_PARALLEL=1: lần lượt như trước.
fake.calls.clear()
live.update(now=0, peak=0)
r.job_parallel = 1
fake.say("ag_lan", "plan", "Chia." + directive(op="assign", agent="ag_minh", brief="G")
         + directive(op="assign", agent="ag_hoa", brief="H"))
fake.say("ag_minh", "work", slow("G xong"))
fake.say("ag_hoa", "work", slow("H xong"))
j = r.submit(TID, "Việc lần lượt", as_job=True, client_msg_id="w6")
run(r.dispatch_once(wait=True))
check("0.260.0 một chỗ mỗi việc: bước Làm chạy lần lượt", live["peak"] == 1
      and ts.get_task(j["task_id"])["status"] == "done", live)
raise SystemExit(1 if fails else 0)
