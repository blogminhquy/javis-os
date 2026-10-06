"""Resonance M2: phần nối trong main.py. Phân nhánh sau lượt và dòng gợi ý trong system prompt.

    python tests/run.py resonance_mvp_main -v

Brain chưa bật thì không có gì chạy, không tạo kho, prompt không dài thêm chữ nào.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m2m-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import luot_dang_chay  # noqa: E402
import plugins_host  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import asyncio  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-m-")).resolve())
USER = "Theo dõi giúp anh thư mục Inbox, mỗi khi có ghi chú mới thì gom vào bản tổng hợp."
SID, MID = "sess_m2", 7

# ───────────── brain chưa bật ─────────────
check("tắt: _resonance_after_turn không làm gì", main._resonance_after_turn(SID, BRAIN, MID, time.time(), None) is None)
check("tắt: không tạo kho resonance.sqlite3", not (Path(_STATE) / "resonance.sqlite3").exists())
p_off = main.build_system_prompt(BRAIN)
check("tắt: system prompt không nhắc javis_goal", "javis_goal" not in p_off)

# ───────────── bật ─────────────
(Path(BRAIN) / "Javis").mkdir(parents=True, exist_ok=True)
(Path(BRAIN) / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
p_on = main.build_system_prompt(BRAIN)
check("bật: system prompt có dòng gợi ý javis_goal", "javis_goal op=create" in p_on)
check("bật: dòng gợi ý ngắn (dưới 450 ký tự)", 0 < len(p_on) - len(p_off) < 450)

t0 = time.time() - 1
d = main._resonance_after_turn(SID, BRAIN, MID, t0, None)
check("bật, lượt không gọi tool: answer_now", d is not None and d.kind == "answer_now")
check("không có id tin nhắn thì không phân nhánh", main._resonance_after_turn(SID, BRAIN, 0, t0, None) is None)

# Bộ não gọi javis_goal trong lượt (như engine sẽ gọi qua hub), rồi main phân nhánh sau lượt
k = luot_dang_chay.bat_dau(f"{main.WEB_CHAT_PREFIX}{SID}", BRAIN, msg_id=MID, user_text=USER)
tools, route = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
out = asyncio.run(route["javis_goal"]["call"]({
    "op": "create", "understanding": "Bản tổng hợp ghi chú mới trong Inbox",
    "criteria": [{"description": "Bản tổng hợp có mặt", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/tong-hop.md"}}],
    "relevant_quote": "mỗi khi có ghi chú mới thì gom vào bản tổng hợp",
    "horizon": {"kind": "event", "event": "có ghi chú mới trong Inbox"}, "mode": "maintain"}))
luot_dang_chay.ket_thuc(k)
check("tool trong lượt: lập được mục tiêu", "Đã lập mục tiêu" in out)
d = main._resonance_after_turn(SID, BRAIN, MID, t0, None)
check("sau lượt có lập mục tiêu: create_goal", d is not None and d.kind == "create_goal" and d.goal_id)
g = main._resonance_store().get(RS.Principal("owner", "owner", main._brain_key(BRAIN)), d.goal_id)
check("mục tiêu thuộc đúng brain theo _brain_key", g is not None and g.request_ref == R.message_ref(SID, MID))
check("vùng đầu ra nằm trong brain", Path(g.output_root).resolve().is_relative_to(Path(BRAIN)))

# Việc Kanban giao trong lượt cho đúng khung chat
tid = main.tasks_feature.store.enqueue(BRAIN, "Gom ghi chú", "gom", chat_id=f"{main.WEB_CHAT_PREFIX}{SID}")
check("tạo được việc Kanban thử", bool(tid))
d2 = main._resonance_after_turn(SID, BRAIN, MID + 1, t0, None)
check("lượt giao việc Kanban cho đúng khung chat: task_now", d2 is not None and d2.kind == "task_now")
d3 = main._resonance_after_turn(SID, BRAIN, MID + 2, time.time() + 5, None)
check("việc Kanban tạo trước lượt không tính", d3 is not None and d3.kind == "answer_now")

# Lỗi trong khâu phân nhánh không được làm hỏng lượt chat
_old = main._resonance_store
main._resonance_store = lambda: (_ for _ in ()).throw(RuntimeError("kho hỏng"))
try:
    check("kho lỗi: _resonance_after_turn nuốt lỗi, trả None", main._resonance_after_turn(SID, BRAIN, 99, t0, None) is None)
finally:
    main._resonance_store = _old

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
