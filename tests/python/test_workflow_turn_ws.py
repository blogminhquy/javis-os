"""Lượt quy trình trong WebSocket: mỗi tin ở phiên workflow:<slug> là một lần chạy.

    python tests/run.py workflow_turn_ws
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-wfturn-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")

import main  # noqa: E402
import workflow_runs  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


store = main.get_store()
sid = store.create_session(brain=main._brain_key("brain"), engine="cli", channel="workflow:viet-bai")
goi = []


async def gia_execute(brain, slug, input="", tools=None, session_id="", source="other"):
    goi.append({"input": input, "source": source, "session_id": session_id})
    rid = workflow_runs.get_store().bat_dau(brain=main._brain_key(brain), slug=slug, name="Viết bài",
                                           input=input, source=source, session_id=session_id)
    yield {"type": "start", "workflow": "Viết bài", "steps": 1, "run_id": rid}
    yield {"type": "step_start", "i": 0, "agent": "Người viết", "task": "viết"}
    yield {"type": "step_done", "i": 0, "agent": "Người viết", "output": "BÀI 1"}
    workflow_runs.get_store().ket_thuc(rid, "done", output="BÀI 1")
    yield {"type": "done", "result": "BÀI 1"}


main.execute_workflow = gia_execute   # _luot_quy_trinh tra cứu qua module lúc gọi


def run(msg, resume=None):
    frames = []

    async def emit(f):
        frames.append(f)
    store.append_message(sid, "user", msg)
    text = asyncio.run(main._luot_quy_trinh(store, sid, msg, "brain", "viet-bai", emit, resume=resume))
    return text, frames


text, fr = run("viết về A")
check("tin tra loi co dong dau + ket qua", text.startswith("Lần chạy #1 · 1 bước · ") and text.endswith("\n\nBÀI 1"))
check("emit status, wf_event, stream (khong turn_done: closure lo)",
      [f["type"] for f in fr].count("status") == 1 and any(f["type"] == "wf_event" for f in fr)
      and fr[-1]["type"] == "stream" and fr[-1]["content"] == text)
msgs = store.get_messages(sid)
check("phien luu tin assistant", msgs[-1]["role"] == "assistant" and msgs[-1]["content"] == text)
check("lan dau khong noi ket qua truoc", goi[0]["input"] == "viết về A" and goi[0]["source"] == "web"
      and goi[0]["session_id"] == sid)

text2, _ = run("sửa ngắn lại")
check("lan hai noi ket qua truoc + dem lan chay", goi[1]["input"].startswith("sửa ngắn lại\n\n# Kết quả lần trước\nBÀI 1")
      and text2.startswith("Lần chạy #2"))


async def gia_loi(brain, slug, input="", tools=None, session_id="", source="other"):
    yield {"type": "start", "workflow": "Viết bài", "steps": 1}
    yield {"type": "step_start", "i": 0, "agent": "Người viết", "task": "viết"}
    yield {"type": "error", "content": "engine chết"}

main.execute_workflow = gia_loi
text3, fr3 = run("lại đi")
check("loi van thanh tin trong chat", text3 == "Quy trình dừng ở bước 1 (Người viết): engine chết"
      and store.get_messages(sid)[-1]["content"] == text3)


async def gia_cho(brain, slug, input="", tools=None, session_id="", source="other"):
    yield {"type": "start", "workflow": "Viết bài", "steps": 2}
    yield {"type": "wait_user", "node": "dang", "prompt": "đăng?", "task_id": "tk9", "code": "ZZ"}

main.execute_workflow = gia_cho
text4, fr4 = run("đăng bài")
check("cho duyet thanh tin + wf_event mang code", "chờ duyệt bước \"dang\"" in text4
      and any(f["type"] == "wf_event" and f["event"].get("code") == "ZZ" for f in fr4))


async def gia_resume(brain, slug, task_id, node_id, code, tools=None, session_id="", source="other"):
    goi.append({"resume": (task_id, node_id, code)})
    yield {"type": "start", "workflow": "Viết bài", "steps": 2}
    yield {"type": "step_start", "i": 1, "agent": "Người đăng", "task": "đăng"}
    yield {"type": "step_done", "i": 1, "agent": "Người đăng", "output": "ĐÃ ĐĂNG"}
    yield {"type": "done", "result": "ĐÃ ĐĂNG"}

main.execute_workflow_resume = gia_resume
text5, _ = run("Đã duyệt bước dang.", resume={"task_id": "tk9", "node": "dang", "code": "ZZ"})
check("resume goi execute_workflow_resume dung tham so", goi[-1].get("resume") == ("tk9", "dang", "ZZ")
      and text5.endswith("ĐÃ ĐĂNG"))

# Canh mã vòng nhận tin. @app.get("/tts/voices") nằm TRƯỚC websocket_endpoint trong file này
# (đã kiểm bằng grep), nên dùng mốc chắc chắn nằm SAU: dòng chú thích mở khối phiên hội thoại.
src = (SERVER / "main.py").read_text(encoding="utf-8")
_mo = "async def websocket_endpoint("
_dong = "# Phiên hội thoại - list / view / search"
ws = src[src.index(_mo):src.index(_dong)] if _dong in src else src[src.index(_mo):]
check("vong nhan tin re nhanh workflow", "run_workflow_turn(" in ws and 'action == "wf_resume"' in ws)

print("\nFAIL:" if fails else "\nOK - workflow_turn_ws", fails or "")
sys.exit(1 if fails else 0)
