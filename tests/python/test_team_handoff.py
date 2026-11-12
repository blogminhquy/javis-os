"""Chuyển việc giữa các nhóm sau khi chủ duyệt (handoff).

    python tests/python/test_team_handoff.py

(1) Luồng duyệt trong TeamRunner, hook giả: duyệt thì giao đúng 1 lần với mục tiêu đã duyệt, từ chối thì không giao,
giao lỗi thì báo trong chat nhóm và việc vẫn đi tiếp.
(2) TeamOps.handoff trên host thật: tìm nhóm đích, từ chối nhóm lưu trữ, nhóm brain khác, nhóm không có, chính nhóm đó;
gửi lại cùng một yêu cầu duyệt không tạo việc thứ hai.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-handoff-")
os.environ.setdefault("JAVIS_NO_REAL_TEAM_ENGINE", "1")
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_approval  # noqa: E402
import team_dispatch  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:400]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


def run(coro):
    return asyncio.run(coro)


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh")}
HOOK_FAIL = [False]


class Fake:
    def __init__(self):
        self.script = {}

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run_(req):
            q = self.script.get((agent_key, role)) or []
            ans = q.pop(0) if q else f"{agent_key} {role} xong"
            return {"text": ans, "tokens_in": 5, "tokens_out": 3}
        return "fake", "fake-model", run_


def world(name):
    d = STATE / name
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "sessions.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()
    inbox, calls = [], []

    def agent_info(brain, key):
        if key not in AGENTS:
            return None
        slug, nm = AGENTS[key]
        return {"slug": slug, "name": nm, "system": f"Bạn là {nm}."}

    def hook(team, h, ap):
        calls.append((team["team_id"], dict(h), ap["approval_id"]))
        if HOOK_FAIL[0]:
            raise RuntimeError("nhóm đích đã lưu trữ")
        return {"team_name": h["team"], "task_id": "t_dest", "created": True}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info,
                      publish=lambda ev: None, notify=lambda tid, text: inbox.append((tid, text)))
    r.handoff_hook = hook
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, "ag_lan")
    return r, tm, ts, ss, fake, tm.get(tid), calls, inbox


def job(r, team, text, key):
    return r.submit(team["team_id"], text, mentions=[], as_job=True, client_msg_id=key)["task_id"]


def drain(r, n=6):
    """Chạy các lượt nền cho tới khi hết việc (bước sửa brief sau duyệt chạy, job xong thì chuyển việc đi)."""
    for _ in range(n):
        run(r.dispatch_once())


def ask_handoff(fake):
    fake.say("ag_lan", "plan", "Phần của nhóm này xong, chuyển 3 bài sang nhóm Biên tập để dịch." + directive(
        op="ask_approval", title="Chuyển 3 bài sang nhóm Biên tập", action="Giao nhóm Biên tập dịch 3 bài",
        handoff={"team": "Nhóm Biên tập", "objective": "Dịch 3 bài đã duyệt sang tiếng Anh"}))


def chat_has(ss, team, text):
    msgs = ss.get_team_messages_page(team["session_id"], limit=300)["messages"]
    return any(text in str(m) for m in msgs)


# ═════ 0. Đọc yêu cầu: handoff hợp lệ được giữ, thiếu nhóm hay việc thì bỏ ═════
p = team_approval.parse_request({"title": "x", "handoff": {"team": " Biên tập ", "objective": "dịch"}})
check("parse: handoff giữ nhóm (đã cắt khoảng trắng) và việc", p["handoff"] == {"team": "Biên tập", "objective": "dịch"}, p)
check("parse: handoff thiếu việc thì bỏ", team_approval.parse_request({"title": "x", "handoff": {"team": "B"}})["handoff"] is None)
check("parse: không có handoff thì None", team_approval.parse_request({"title": "x"})["handoff"] is None)

# ═════ 1. Luồng duyệt: giữ đến khi chủ quyết, duyệt thì giao đúng 1 lần ═════
r, tm, ts, ss, fake, T, calls, inbox = world("approve")
ask_handoff(fake)
j = job(r, T, "Chuẩn bị 3 bài", "h-approve")
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
check("duyệt: yêu cầu có handoff nằm trong held_ops, chưa gửi gì",
      ap and {"kind": "handoff", "team": "Nhóm Biên tập", "objective": "Dịch 3 bài đã duyệt sang tiếng Anh"} in ap["held_ops"],
      ap and ap["held_ops"])
check("duyệt: trước khi chủ quyết thì chưa giao nhóm nào", calls == [], calls)
res = r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="hand-1", expected_rev=1)
check("duyệt: quyết định ok", res.get("ok"), res)
check("duyệt: chủ vừa duyệt thì CHƯA giao (đợi việc xong để có kết quả đã sửa)", calls == [], calls)
fake.say("ag_lan", "plan", "Brief đã sửa: 3 bài, dịch sang tiếng Anh, giữ giọng thương hiệu.")
drain(r)
check("việc xong: giao đúng 1 lần, mục tiêu là KẾT QUẢ ĐÃ SỬA, gắn với yêu cầu duyệt",
      len(calls) == 1 and "Brief đã sửa" in calls[0][1]["objective"]
      and calls[0][2] == ap["approval_id"], calls)
check("duyệt: chat nhóm ghi rõ đã chuyển sang nhóm kia", chat_has(ss, T, "Đã chuyển việc sang nhóm"))
check("duyệt: việc của nhóm này không còn đợi chủ", ts.get_task(j)["block_kind"] != "waiting_user",
      (ts.get_task(j)["status"], ts.get_task(j)["block_kind"]))

# ═════ 2. Từ chối: không giao nhóm nào ═════
r, tm, ts, ss, fake, T, calls, inbox = world("reject")
ask_handoff(fake)
j = job(r, T, "Chuẩn bị 3 bài", "h-reject")
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
r.decide_approval(T["team_id"], ap["approval_id"], "reject", note="chưa cần", decision_key="hand-r")
check("từ chối: không gọi hook, không giao nhóm nào", calls == [], calls)

# ═════ 3. Giao lỗi: báo trong chat nhóm, việc vẫn đi tiếp ═════
r, tm, ts, ss, fake, T, calls, inbox = world("fail")
ask_handoff(fake)
j = job(r, T, "Chuẩn bị 3 bài", "h-fail")
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
HOOK_FAIL[0] = True
r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="hand-f", expected_rev=1)
fake.say("ag_lan", "plan", "Brief đã sửa cho nhóm kia.")
drain(r)
HOOK_FAIL[0] = False
check("giao lỗi: hook được gọi và lỗi được ghi vào chat nhóm", len(calls) == 1
      and chat_has(ss, T, "Chưa chuyển được việc sang nhóm"), calls)
check("giao lỗi: việc không còn đợi chủ (không kẹt)", ts.get_task(j)["block_kind"] != "waiting_user",
      (ts.get_task(j)["status"], ts.get_task(j)["block_kind"]))

# ═════ 4. Host thật: TeamOps.handoff tìm nhóm đích, giao đúng 1 việc, từ chối các trường hợp sai ═════
import main  # noqa: E402
import team_api  # noqa: E402
import tempfile as _tf  # noqa: E402

BR = Path(_tf.mkdtemp(prefix="javis-handoff-brain-"))
BR2 = Path(_tf.mkdtemp(prefix="javis-handoff-brain2-"))
for root, slugs in ((BR, ("lan", "minh")), (BR2, ("xa",))):
    (root / "agents").mkdir()
    for slug in slugs:
        (root / "agents" / f"{slug}.md").write_text(f"---\nname: {slug}\nrole: Thành viên\n---\nBạn là {slug}.\n",
                                                    encoding="utf-8", newline="\n")

main._CHAT_RUNTIME.publish = lambda ev: asyncio.sleep(0)
main._TEAM_API.deps.spawn = lambda job_: job_.close() if asyncio.iscoroutine(job_) else None
main._TEAM_API.deps.engine_for = lambda team, key, role: (_ for _ in ()).throw(AssertionError("không chạy model trong test"))

ops = team_api.current()
R1, R2 = main._brain_key(str(BR)), main._brain_key(str(BR2))
A = ops.create(R1, R1, "Phòng nội dung", ["lan", "minh"], "lan")["team"]
B = ops.create(R1, R1, "Biên tập", ["lan", "minh"], "lan")["team"]
C = ops.create(R1, R1, "Nhóm cũ", ["lan"], "lan")["team"]
ops.update(R1, C["team_id"], status="archived")
X = ops.create(R2, R2, "Nhóm brain khác", ["xa"], "xa")["team"]
store = main.tasks_feature.store


def n_tasks(team):
    q = store.team_queue(team["team_id"])
    return len(q["waiting"]) + len(q["blocked"]) + len(q["running"]) + len(store.team_history(team["team_id"], 50))


out = ops.handoff(A, {"team": "Biên tập", "objective": "Dịch 3 bài"}, {"approval_id": "ap_host_1"})
check("host: giao sang nhóm đích tạo đúng 1 việc ở nhóm đích, không đụng nhóm nguồn",
      out["created"] and n_tasks(B) == 1 and n_tasks(A) == 0, (out, n_tasks(B), n_tasks(A)))
again = ops.handoff(A, {"team": "Biên tập", "objective": "Dịch 3 bài"}, {"approval_id": "ap_host_1"})
check("host: gửi lại cùng yêu cầu duyệt trả đúng việc cũ, không tạo việc thứ hai",
      not again["created"] and again["task_id"] == out["task_id"] and n_tasks(B) == 1, (again, n_tasks(B)))
for name, ref in (("nhóm lưu trữ", "Nhóm cũ"), ("nhóm brain khác", "Nhóm brain khác"),
                  ("không có nhóm", "Không có"), ("chính nhóm nguồn", "Phòng nội dung")):
    try:
        ops.handoff(A, {"team": ref, "objective": "x"}, {"approval_id": f"ap_bad_{len(name)}"})
        check(f"host: từ chối {name}", False, "không ném lỗi")
    except team_dispatch.DispatchError as ex:
        check(f"host: từ chối {name}", True, str(ex))
check("host: các lần từ chối không tạo việc nào", n_tasks(B) == 1 and n_tasks(C) == 0 and n_tasks(X) == 0
      and n_tasks(A) == 0, (n_tasks(B), n_tasks(A)))

# ═════ 5. Chủ CHỌN nhóm đích trên thẻ duyệt: không cần model, duyệt thì giao đúng 1 lần ═════
r, tm, ts, ss, fake, T, calls, inbox = world("picked")
fake.say("ag_lan", "plan", "Chuyển bài sang nhóm khác." + directive(
    op="ask_approval", title="Sửa brief rồi chuyển", action="Sửa brief theo hướng 1 và chuyển sang nhóm Biên tập"))
j = job(r, T, "Sửa brief", "h-picked")
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
check("chọn nhóm: yêu cầu không có handoff từ model (không tự chuyển)", ap and not ap.get("held_ops"), ap and ap.get("held_ops"))
r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="hand-pick", expected_rev=1,
                  handoff_to="Nhóm Biên tập")
check("chọn nhóm: duyệt chưa giao, đợi bước sửa brief chạy xong", calls == [], calls)
fake.say("ag_lan", "plan", "Brief đã sửa theo hướng 1, sẵn sàng cho nhóm Biên tập.")
drain(r)
check("chọn nhóm: việc xong thì giao đúng 1 lần, nhóm đích nhận brief ĐÃ SỬA",
      len(calls) == 1 and calls[0][1]["team"] == "Nhóm Biên tập"
      and "Brief đã sửa theo hướng 1" in calls[0][1]["objective"], calls)
drain(r)
r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="hand-pick", expected_rev=1,
                  handoff_to="Nhóm Biên tập")
check("chọn nhóm: bấm lại cùng lần bấm và chạy thêm lượt không giao lần hai", len(calls) == 1, calls)

r, tm, ts, ss, fake, T, calls, inbox = world("picked_none")
fake.say("ag_lan", "plan", "Chuyển bài." + directive(
    op="ask_approval", title="Chỉ duyệt", action="Làm tiếp, không chuyển"))
j = job(r, T, "Việc", "h-none")
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="hand-none", expected_rev=1)
check("không chọn nhóm: duyệt xong không giao nhóm nào", calls == [], calls)

# Route: chọn nhóm sai bị từ chối trước khi duyệt (đường host thật, cùng TeamOps ở trên)
try:
    ops.handoff_target(A, "Không có nhóm này")
    check("route: nhóm đích không tồn tại bị chặn trước khi duyệt", False, "không ném lỗi")
except team_dispatch.DispatchError:
    check("route: nhóm đích không tồn tại bị chặn trước khi duyệt", True)
check("route: nhóm đích hợp lệ được tìm thấy theo tên", ops.handoff_target(A, "Biên tập")["team_id"] == B["team_id"])

# ═════ 6. Việc dừng hoặc bị huỷ khi lượt chuyển đã duyệt chưa đi: báo trong chat, không giao gì ═════
r, tm, ts, ss, fake, T, calls, inbox = world("stopped")
ask_handoff(fake)
j = job(r, T, "Chuẩn bị 3 bài", "h-stop")
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="hand-stop", expected_rev=1)
r._block(j, "failed", "thử dừng giữa chừng", post=True)
check("dừng: chat báo lượt chuyển CHƯA đi và sẽ đi khi việc xong", chat_has(ss, T, "Chưa chuyển việc sang nhóm"), "")
check("dừng: vẫn chưa giao nhóm nào", calls == [], calls)
r2, tm2, ts2, ss2, fake2, T2, calls2, inbox2 = world("cancelled")
ask_handoff(fake2)
j2 = job(r2, T2, "Chuẩn bị 3 bài", "h-cancel")
run(r2.dispatch_once())
ap2 = r2.approvals.pending_for_task(j2)
r2.decide_approval(T2["team_id"], ap2["approval_id"], "approve", decision_key="hand-cancel", expected_rev=1)
r2.cancel_job(j2, reason="chủ nhóm huỷ", owner_cancel=True)
check("huỷ: chat báo đã bỏ chuyển việc", chat_has(ss2, T2, "Đã bỏ chuyển việc sang nhóm"), "")
drain(r2)
check("huỷ: không giao nhóm nào dù còn chạy nền", calls2 == [], calls2)

print("\n" + ("FAILED: " + ", ".join(fails) if fails else "ALL PASSED"))
sys.exit(1 if fails else 0)
