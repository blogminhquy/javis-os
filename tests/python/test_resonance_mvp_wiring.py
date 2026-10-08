"""Resonance M2: nối vào đường chat thật. Plugin javis-goal, sổ lượt đang chạy, định tuyến sau lượt.

    python tests/run.py resonance_mvp_wiring -v

Đi qua plugins_host thật (nạp plugin bundled từ system/plugins), sổ luot_dang_chay thật và kho
SQLite thật. Không gọi model: bộ não được giả bằng cách gọi thẳng tool như engine sẽ gọi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m2w-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import luot_dang_chay  # noqa: E402
import plugins_host  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-w-")).resolve())
OTHER = str(Path(tempfile.mkdtemp(prefix="brain-w2-")).resolve())
USER = "Mỗi sáng gom giúp anh việc đang dở vào một ghi chú, làm tới hết tuần này."


import turn_context  # noqa: E402
import _resonance_agent as RA  # noqa: E402  - A1: bật theo agent, danh tính lượt từ turn_context

AG = {}


def enable(brain, on=True):
    store0 = RS.GoalStore()
    if on:
        AG.update(RA.enable(store0, brain))
    else:
        AG.update(RA.disable(store0, brain))


def tools_for(brain):
    tools, route = plugins_host.plugin_tools("full", brain, scope_vault=False)
    return {t["fn"] for t in tools}, route


# ───────────── sổ lượt mang id tin nhắn và lời người dùng ─────────────
k1 = luot_dang_chay.bat_dau("web:s1", BRAIN, msg_id=41, user_text=USER)
lu = luot_dang_chay.doan_luot(BRAIN)
check("sổ lượt: trả đúng phiên, id tin và lời người dùng",
      lu and lu["chat_id"] == "web:s1" and lu["msg_id"] == 41 and lu["user_text"] == USER)
check("sổ lượt: chat_id cũ vẫn đoán được như trước", luot_dang_chay.doan_chat_id(BRAIN) == "web:s1")
k2 = luot_dang_chay.bat_dau("web:s2", BRAIN, msg_id=42, user_text="khác")
check("sổ lượt: hai khung chat cùng chạy trên một brain thì không đoán", luot_dang_chay.doan_luot(BRAIN) is None)
luot_dang_chay.ket_thuc(k2)
check("sổ lượt: gạch lượt kia thì đoán lại được", (luot_dang_chay.doan_luot(BRAIN) or {}).get("msg_id") == 41)
k3 = luot_dang_chay.bat_dau("web:s9", OTHER, msg_id=9, user_text="x")
check("sổ lượt: lượt của brain khác không lẫn vào", (luot_dang_chay.doan_luot(BRAIN) or {}).get("msg_id") == 41)
luot_dang_chay.ket_thuc(k3)
k_old = luot_dang_chay.bat_dau("web:s3", OTHER)
check("sổ lượt: gọi kiểu cũ (không id tin) vẫn chạy", (luot_dang_chay.doan_luot(OTHER) or {}).get("msg_id") == 0)
luot_dang_chay.ket_thuc(k_old)

# ───────────── tool chỉ hiện khi brain bật Resonance ─────────────
names, _ = tools_for(BRAIN)
check("tắt (mặc định): brain KHÔNG thấy tool javis_goal", "javis_goal" not in names)
check("tắt: các tool khác vẫn còn (javis_task)", "javis_task" in names)
enable(BRAIN)
names, route = tools_for(BRAIN)
check("bật: brain thấy tool javis_goal", "javis_goal" in names)
names_o, _ = tools_for(OTHER)
check("bật ở brain này không làm brain khác thấy tool", "javis_goal" not in names_o)
call = route["javis_goal"]["call"]
TURN = {"sid": "s1", "mid": 41, "text": USER}


def tool(args):
    """Gọi tool như bộ não gọi trong lượt của agent: ngữ cảnh lượt có agent, phiên, id tin (A1)."""
    with RA.turn(AG, TURN["sid"], TURN["mid"], TURN["text"], BRAIN):
        return asyncio.run(call(args))


PROPOSAL = {
    "understanding": "Ghi chú tổng hợp việc đang dở, cập nhật mỗi sáng",
    "criteria": [{"description": "Ghi chú tồn tại", "evaluator": "artifact_contract",
                  "params": {"path": "00 - Dashboard/viec-dang-do.md", "min_chars": 50}},
                 {"description": "Anh xác nhận dùng được", "evaluator": "human_confirmation", "params": {}}],
    "relevant_quote": "gom giúp anh việc đang dở vào một ghi chú",
    "horizon": {"kind": "deadline", "at_iso": "2026-10-11T23:00:00+07:00", "from_user": True,
                "quote": "hết tuần này"},
    "stage": "delivery", "mode": "maintain",
}

# ───────────── bộ não gọi javis_goal create ─────────────
out = tool({"op": "create", **PROPOSAL})
check("create: trả mã mục tiêu và revision", "g_" in out and "revision 1" in out and not out.startswith("ERROR"))
store = RS.GoalStore()
P = RS.Principal("owner", "owner", BRAIN)
goals = store.list_open(P)
check("create: đúng một mục tiêu trong kho, gắn đúng tin nhắn",
      len(goals) == 1 and goals[0].request_ref == R.message_ref("s1", 41) and goals[0].session_id == "s1")
out2 = tool({"op": "create", **PROPOSAL})
check("create lặp trong cùng tin nhắn: không tạo mục tiêu thứ hai", len(store.list_open(P)) == 1 and goals[0].id in out2)
# Đề xuất sai luật phải thử trên một TIN MỚI: cùng tin 41 đã có mục tiêu thì tool trả lại mục tiêu đó (chống trùng).
luot_dang_chay.ket_thuc(k1)
TURN["mid"] = 44
out3 = tool({"op": "create", **{**PROPOSAL, "relevant_quote": "em đề xuất dọn wiki"}})
check("create với căn cứ không có trong lời người dùng: ERROR, nói rõ vì sao",
      out3.startswith("ERROR") and "lời người dùng" in out3)
out4 = tool({"op": "create", **{**PROPOSAL, "criteria": []}})
check("create thiếu tiêu chí: ERROR nhắc M", out4.startswith("ERROR") and "tiêu chí" in out4)
check("đề xuất sai luật không để lại mục tiêu nào", store.find_by_key(P, R.message_ref("s1", 44)) is None
      and len(store.list_open(P)) == 1)

# ───────────── route sau lượt ─────────────
t0 = time.time() - 5
d = R.route_after_turn(store, P, R.message_ref("s1", 41), tasks=[], chat_id="web:s1", t0=t0)
check("route sau lượt có tạo mục tiêu: create_goal", d.kind == "create_goal" and d.goal_id == goals[0].id)
d = R.route_after_turn(store, P, R.message_ref("s1", 77), tasks=[], chat_id="web:s1", t0=t0)
check("route tin khác, không làm gì: answer_now", d.kind == "answer_now")
d = R.route_after_turn(store, P, R.message_ref("s1", 78),
                       tasks=[{"chat_id": "web:s1", "created_at": time.time()},
                              {"chat_id": "web:khac", "created_at": time.time()},
                              {"chat_id": "web:s1", "created_at": t0 - 100}],
                       chat_id="web:s1", t0=t0)
check("route có việc Kanban MỚI của đúng khung chat: task_now", d.kind == "task_now")
d = R.route_after_turn(store, P, R.message_ref("s1", 79), tasks=[{"chat_id": "web:s1", "created_at": t0 - 100}],
                       chat_id="web:s1", t0=t0)
check("việc Kanban cũ từ trước lượt không tính", d.kind == "answer_now")

# ───────────── bổ sung ý cho mục tiêu đang mở: update ─────────────
TURN.update(mid=43, text="Ý anh là có cả lịch tuần trong ghi chú đó.")
gid = goals[0].id
upd = {"op": "update", "goal_id": gid, "expected_revision": 1, "reason": "anh thêm lịch tuần",
       **{**PROPOSAL, "understanding": "Ghi chú việc đang dở kèm lịch tuần",
          "relevant_quote": "có cả lịch tuần",
          "horizon": {"kind": "review", "at_iso": "2026-10-09T08:00:00+07:00", "reason": "xem lại giữa tuần"}}}
out5 = tool(upd)
check("update: lên revision 2", "revision 2" in out5 and not out5.startswith("ERROR"))
check("update: route của tin bổ sung là continue_goal",
      R.route_after_turn(store, P, R.message_ref("s1", 43), tasks=[], chat_id="web:s1", t0=t0).kind == "continue_goal")
out6 = tool(upd)
check("update lặp với expected_revision cũ: ERROR xung đột, không đổi gì",
      out6.startswith("ERROR") and store.get(P, gid).revision == 2)
out7 = tool({**upd, "goal_id": "g_khong_co", "expected_revision": 2})
check("update mục tiêu không tồn tại: ERROR", out7.startswith("ERROR"))
out8 = tool({"op": "list"})
check("list: thấy mục tiêu đang mở", gid in out8 and "lịch tuần" in out8)

# ───────────── không có danh tính lượt thì không tạo (A1: không còn đoán lượt duy nhất) ─────────────
kA = luot_dang_chay.bat_dau("web:a", BRAIN, msg_id=50, user_text=USER)
out9 = asyncio.run(call({"op": "create", **PROPOSAL}))
check("gọi ngoài lượt (không có ngữ cảnh lượt), dù sổ có đúng một lượt: ERROR, không tạo",
      out9.startswith("ERROR") and len(store.list_open(P)) == 1)
luot_dang_chay.ket_thuc(kA)
_tok = turn_context.bind(turn_context.make("dashboard", chat_id="plain", la_chu=True, session_id="plain",
                                           message_id=60))
kP = luot_dang_chay.bat_dau("web:plain", BRAIN, msg_id=60, user_text=USER)
outP = asyncio.run(call({"op": "create", **PROPOSAL}))
luot_dang_chay.ket_thuc(kP)
turn_context.reset(_tok)
check("lượt chat thường (không thuộc agent): ERROR, không tạo", outP.startswith("ERROR")
      and "trợ lý" in outP and len(store.list_open(P)) == 1)
_tok = turn_context.bind(turn_context.make("telegram", sender_id="123", chat_id="123"))
outC = asyncio.run(call({"op": "create", **PROPOSAL}))
turn_context.reset(_tok)
check("lượt kênh khác, không phiên, không id tin: ERROR, không tạo",
      outC.startswith("ERROR") and len(store.list_open(P)) == 1)
TURN.update(mid=61, text=USER)
with RA.turn(AG, "s1", 61, USER, BRAIN):
    luot_dang_chay.ket_thuc(next(k for k, x in luot_dang_chay._DANG.items() if x["msg_id"] == 61))
    outG = asyncio.run(call({"op": "create", **PROPOSAL}))
check("lượt có ngữ cảnh nhưng sổ lượt không còn lời của đúng tin: ERROR, không tạo",
      outG.startswith("ERROR") and len(store.list_open(P)) == 1)

# ───────────── tắt lại giữa chừng ─────────────
_old_ag = dict(AG)
enable(BRAIN, on=False)
check("tắt lại: tool biến mất khỏi danh sách", "javis_goal" not in tools_for(BRAIN)[0])
with RA.turn(_old_ag, "s1", 62, USER, BRAIN):
    outD = asyncio.run(call({"op": "list"}))
check("tắt lại: gọi tool cũ còn giữ trong tay cũng bị từ chối", outD.startswith("ERROR"))

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
