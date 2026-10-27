"""Javis Core giao việc cho một nhóm có sẵn và nhận kết quả về đúng khung chat (0.357.0, issue #826).

    python tests/run.py team_core_dispatch

Chạy qua host thật (`main` + `team_api.current()`), không gọi model: trạng thái việc được đẩy thẳng bằng kho Kanban, như
bộ chạy nhóm vẫn làm. Giữ các tiêu chí của issue: đúng 1 việc, gửi lại không tạo việc thứ hai, sai quyền hay nhóm của
brain khác bị từ chối TRƯỚC khi tạo việc, báo về đúng khung chat, XONG khác ĐẠT, cổng duyệt vẫn là của chủ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-core-dispatch-")
BR = Path(tempfile.mkdtemp(prefix="javis-core-dispatch-brain-"))
BR2 = Path(tempfile.mkdtemp(prefix="javis-core-dispatch-brain2-"))
for root, slugs in ((BR, ("lan", "minh")), (BR2, ("xa",))):
    (root / "agents").mkdir()
    for slug in slugs:
        (root / "agents" / f"{slug}.md").write_text(f"---\nname: {slug}\nrole: Thành viên\n---\nBạn là {slug}.\n",
                                                    encoding="utf-8", newline="\n")

import main  # noqa: E402
import team_api  # noqa: E402
import team_dispatch  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


async def _publish(ev):
    return None


main._CHAT_RUNTIME.publish = _publish
main._TEAM_API.deps.spawn = lambda job: job.close() if asyncio.iscoroutine(job) else None


def _no_engine(team, key, role):
    raise AssertionError("giao việc không được tự mở lượt nhóm trong test")


main._TEAM_API.deps.engine_for = _no_engine
SENT = []
REPORT_OK = [True]


def _fake_report(owner_chat, text, **kw):
    SENT.append({"to": owner_chat, "text": text, **kw})
    return (REPORT_OK[0], "" if REPORT_OK[0] else "kênh hỏng")


main._TEAM_API.deps.report = _fake_report

spec = importlib.util.spec_from_file_location("javis_team_plugin", ROOT / "system" / "plugins" / "javis-team" / "plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
regs = []


class Ctx:
    def __init__(self, vault_root):
        self.vault_root = vault_root
        self.slug = "javis-team"

    def register_tool(self, *a, **kw):
        regs.append((a, kw))

    def register_hook(self, *a, **k):
        pass


plugin.register(Ctx(str(BR)))
handler = regs[0][0][2]
desc, schema = regs[0][0][1], regs[0][1]["schema"]


def run(args, turn=None, root=BR):
    tok = turn_context.bind(turn)
    try:
        return asyncio.run(handler(args, Ctx(str(root))))
    finally:
        turn_context.reset(tok)


ops = team_api.current()
store = main.tasks_feature.store
R1, R2 = main._brain_key(str(BR)), main._brain_key(str(BR2))
A = ops.create(R1, R1, "Phòng nội dung", ["lan", "minh"], "lan")["team"]
B = ops.create(R1, R1, "Nhóm không trưởng", ["lan", "minh"])["team"]
C = ops.create(R1, R1, "Nhóm cũ", ["lan"], "lan")["team"]
ops.update(R1, C["team_id"], status="archived")
X = ops.create(R2, R2, "Nhóm brain khác", ["xa"], "xa")["team"]


def n_tasks(team):
    return len(main.tasks_feature.store.team_queue(team["team_id"])["waiting"]) + len(
        store.team_history(team["team_id"], 50)) + len(store.team_queue(team["team_id"])["blocked"]) + len(
        store.team_queue(team["team_id"])["running"])


OWNER = turn_context.make("dashboard", chat_id="sess_web_1", la_chu=True, session_id="sess_web_1", message_id=41)

# ---- 1. quyền: từ chối TRƯỚC khi tạo việc ----
check("tool mô tả op dispatch và job, schema có objective/assignee/request_id/task",
      "op=dispatch" in desc and "op=job" in desc and all(k in schema["properties"] for k in
                                                          ("objective", "assignee", "request_id", "task")))
r = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "Viết 3 bài"}, turn=None)
check("không có lượt (không rõ ai giao): từ chối", r.startswith("ERROR") and n_tasks(A) == 0, r)
r = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "Viết 3 bài"},
        turn=turn_context.make("team", chat_id=A["team_id"], team_gate="g1"))
check("một bước việc nhóm không được giao việc sang nhóm", r.startswith("ERROR") and n_tasks(A) == 0, r)
r = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "Viết 3 bài"},
        turn=turn_context.make("telegram", sender_id="99", chat_id="99", la_chu=False))
check("người không phải chủ (bot chăm khách): từ chối", r.startswith("ERROR") and n_tasks(A) == 0, r)
r = run({"op": "dispatch", "team": X["team_id"], "objective": "Lấy dữ liệu"}, turn=OWNER)
check("nhóm của brain khác (theo mã): coi như không có, không tạo việc", r.startswith("ERROR") and n_tasks(X) == 0, r)
r = run({"op": "dispatch", "team": "Nhóm cũ", "objective": "Viết 3 bài"}, turn=OWNER)
check("nhóm đã lưu trữ: từ chối, không tự mở lại", r.startswith("ERROR") and "lưu trữ" in r and n_tasks(C) == 0, r)
r = run({"op": "dispatch", "team": "Nhóm không trưởng", "objective": "Viết 3 bài"}, turn=OWNER)
check("nhóm chưa có trưởng nhóm và không chỉ người nhận: từ chối, nói cách sửa",
      r.startswith("ERROR") and "assignee" in r and n_tasks(B) == 0, r)
r = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "Viết 3 bài", "assignee": "khong-co"}, turn=OWNER)
check("người nhận không có trong nhóm: từ chối", r.startswith("ERROR") and n_tasks(A) == 0, r)
r = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "  "}, turn=OWNER)
check("thiếu objective: từ chối", r.startswith("ERROR") and n_tasks(A) == 0, r)

# ---- 2. giao đúng 1 việc, gửi lại không tạo thêm ----
r = run({"op": "dispatch", "team": "phòng nội dung", "objective": "Viết 3 bài về nước mắm\n\nMỗi bài 500 chữ"},
        turn=OWNER)
check("chủ giao trong web chat: tạo 1 việc nhóm", r.startswith("Đã giao việc cho nhóm Phòng nội dung")
      and n_tasks(A) == 1, r)
t1 = store.team_queue(A["team_id"])["waiting"][0]
core = (t1.get("metadata") or {}).get("core") or {}
check("việc nhớ nơi báo là đúng khung chat web đang hỏi", core.get("report_to") == "web:sess_web_1"
      and core.get("kenh") == "dashboard", core)
check("tiêu đề là đoạn đầu của mục tiêu, cả mục tiêu là yêu cầu", t1["title"] == "Viết 3 bài về nước mắm"
      and "500 chữ" in t1["intent"], t1)
check("trả về mã việc và mã đối chiếu", t1["id"] in r and core.get("correlation_id", "x") in r, r)
check("lời trả không hứa sẽ chờ: kết quả tự báo về", "tự báo về" in r, r)
msg = main.get_store().message_by_client_id(A["session_id"], "core:" + core["correlation_id"]) or {}
check("tin giao việc nằm trong khung chat nhóm, của chủ, ghi rõ qua Javis Core",
      t1["source_ref"] == f"msg:{A['session_id']}:{msg.get('id')}"
      and (msg.get("meta") or {}).get("via_core", {}).get("correlation_id") == core["correlation_id"], msg)
r2 = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "Viết 3 bài về nước mắm\n\nMỗi bài 500 chữ"},
         turn=OWNER)
check("gọi lại y hệt trong cùng lượt (thử lại): KHÔNG tạo việc thứ hai, trả đúng việc cũ",
      "KHÔNG tạo việc thứ hai" in r2 and t1["id"] in r2 and n_tasks(A) == 1, r2)
r3 = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "Một việc khác hẳn", "request_id": "kh-001"},
         turn=OWNER)
r4 = run({"op": "dispatch", "team": "Phòng nội dung", "objective": "Một việc khác hẳn", "request_id": "kh-001"},
         turn=turn_context.make("dashboard", chat_id="sess_web_2", la_chu=True, session_id="sess_web_2", message_id=3))
check("cùng request_id từ lượt khác: vẫn một việc, nơi báo giữ nơi giao đầu",
      "Đã giao" in r3 and "KHÔNG tạo việc thứ hai" in r4 and n_tasks(A) == 2
      and (store.team_core_find(A["team_id"], "kh-001")["metadata"]["core"]["report_to"] == "web:sess_web_1"), (r3, r4))
r = run({"op": "dispatch", "team": "Nhóm không trưởng", "objective": "Soát lỗi chính tả", "assignee": "minh"},
        turn=OWNER)
check("nhóm không trưởng nhưng chỉ đích danh người nhận: giao được", r.startswith("Đã giao") and n_tasks(B) == 1, r)

# ---- 3. đọc trạng thái ----
r = run({"op": "job", "team": "Phòng nội dung", "task": t1["id"]}, turn=OWNER)
check("job theo mã việc: trạng thái chờ, nghiệm thu nói rõ nhóm không bật", "Đang chờ tới lượt" in r
      and "nhóm không bật nghiệm thu" in r, r)
r = run({"op": "job", "team": "Phòng nội dung", "task": "kh-001"}, turn=OWNER)
check("job theo mã đối chiếu", "Một việc khác hẳn" in r, r)
r = run({"op": "job", "team": "Nhóm không trưởng", "task": t1["id"]}, turn=OWNER)
check("job của nhóm khác: không lộ việc", r.startswith("ERROR"), r)

# ---- 4. báo về ----
api = main._TEAM_API
check("việc còn chờ: chưa báo gì", asyncio.run(api.core_reports()) == 0 and not SENT, SENT)
got = store.claim_team_next(A["team_id"], "test-worker")
check("nhận đúng việc đầu hàng", got and got["id"] == t1["id"], got)
check("đang làm: chưa báo", asyncio.run(api.core_reports()) == 0 and not SENT, SENT)
store.team_finish(t1["id"], "Đây là 3 bài viết KẾT-QUẢ-ABC")
n = asyncio.run(api.core_reports())
check("xong: báo đúng một tin về đúng khung chat web", n == 1 and len(SENT) == 1 and SENT[0]["to"] == "web:sess_web_1", SENT)
check("tin báo có kết quả, nói XONG nhưng chưa ai xác nhận ĐẠT", "KẾT-QUẢ-ABC" in SENT[0]["text"]
      and "không bật nghiệm thu" in SENT[0]["text"] and "KẾT-QUẢ-ABC" in SENT[0]["ngan"], SENT[0])
check("tin báo đi vào hòm thư với khoá chống trùng và đúng brain", SENT[0]["dedup"].startswith(f"teamcore:{t1['id']}:")
      and SENT[0]["brain"] == R1, SENT[0])
check("báo một lần: vòng sau không báo lại", asyncio.run(api.core_reports()) == 0 and len(SENT) == 1, SENT)
check("việc đã báo lần cuối thôi được theo dõi", all(t["id"] != t1["id"] for t in store.team_core_watch()))

t2 = store.team_core_find(A["team_id"], "kh-001")
store.claim_team_next(A["team_id"], "test-worker")
store.team_block(t2["id"], "waiting_user", "cần chủ duyệt đăng bài")
REPORT_OK[0] = False
SENT.clear()
check("kênh hỏng: không đánh dấu đã báo", asyncio.run(api.core_reports()) == 0 and len(SENT) == 1)
REPORT_OK[0] = True
SENT.clear()
n = asyncio.run(api.core_reports())
check("chờ chủ quyết: báo về, nói rõ Javis không tự duyệt", n == 1 and "Javis không tự duyệt" in SENT[0]["text"]
      and "cần chủ duyệt đăng bài" in SENT[0]["text"], SENT)
check("cổng duyệt vẫn là của chủ: việc vẫn bị chặn sau khi báo", store.get_task(t2["id"])["status"] == "team_blocked")
check("việc còn chờ chủ: vẫn theo dõi tiếp", any(t["id"] == t2["id"] for t in store.team_core_watch()))
store.team_cancel(t2["id"], "chủ huỷ")
SENT.clear()
n = asyncio.run(api.core_reports())
check("huỷ: báo một tin rồi thôi theo dõi", n == 1 and "huỷ" in SENT[0]["text"].lower()
      and all(t["id"] != t2["id"] for t in store.team_core_watch()), SENT)

# ---- 5. XONG khác ĐẠT ----
done = {"status": "done", "block_kind": "", "result": "x"}
check("có nghiệm thu và đạt: XONG và ĐẠT", team_dispatch.phase(done, {"completion_valid": True})[0] == "done_pass")
check("có nghiệm thu nhưng chưa đạt: không bao giờ nói ĐẠT",
      team_dispatch.phase(done, {"completion_valid": False})[0] == "done_unverified")
check("đang kiểm nghiệm thu: chưa báo", team_dispatch.phase({"status": "team_blocked", "block_kind": "acceptance_checking"},
                                                            None)[2] is False)
check("nghiệm thu không đạt: báo", team_dispatch.phase({"status": "team_blocked", "block_kind": "acceptance_failed"},
                                                       None)[0] == "acceptance_failed")

# ---- 6. kênh khác và việc nền ----
tg = turn_context.make("telegram", sender_id="123", chat_id="123", la_chu=True)
check("Telegram của chủ: báo về đúng chat Telegram đó", team_dispatch.report_to(tg) == "123")
check("Zalo của chủ: giữ tiền tố zalo:", team_dispatch.report_to(
    turn_context.make("zalo", sender_id="a", chat_id="zalo:abc", la_chu=True)) == "zalo:abc")
kb = turn_context.make("kanban", chat_id="web:sess_9", job="kanban:t_1")
check("việc nền chủ đã lên lịch: được giao, báo về nơi của việc nền", team_dispatch.check_caller(kb) is kb
      and team_dispatch.report_to(kb) == "web:sess_9")
check("việc nền: cùng lần chạy ra cùng mã đối chiếu", team_dispatch.correlation(kb, "tm1", "x")
      == team_dispatch.correlation(kb, "tm1", "x"))
check("không mã tin: gửi lại trong 30 phút cùng mã, qua mốc khác mã",
      team_dispatch.correlation(tg, "tm1", "x", now=1000) == team_dispatch.correlation(tg, "tm1", "x", now=1500)
      and team_dispatch.correlation(tg, "tm1", "x", now=1000) != team_dispatch.correlation(tg, "tm1", "x", now=5000))
check("mã đối chiếu từ model bị lọc ký tự lạ", team_dispatch.correlation(tg, "tm1", "x", given="a b/../c") == "ab..c")

# ---- 7. giao diện ----
JS = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
EN = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
check("khung chat nhóm ghi 'qua Javis Core' trên tin Core gửi", "meta.via_core" in JS
      and VI.get("teams.via_core") == "qua Javis Core" and EN.get("teams.via_core") == "via Javis Core")
check("host nối báo về bằng _notify_owner", main._TEAM_API.deps.report is _fake_report
      and "report=_notify_owner" in (SERVER / "main.py").read_text(encoding="utf-8"))

print()
if fails:
    print("FAILED: " + ", ".join(fails))
    raise SystemExit(1)
print("All passed")
