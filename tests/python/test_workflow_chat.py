"""workflow_chat: phần thuần của "chạy quy trình như một lượt chat".

    python tests/run.py workflow_chat
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import sys

import workflow_chat as wc  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# persona
check("persona agent", wc.persona_cua_phien({"channel": "agent:nguoi-viet"}) == ("agent", "nguoi-viet"))
check("persona workflow", wc.persona_cua_phien({"channel": "workflow:viet-bai"}) == ("workflow", "viet-bai"))
check("persona web/None/rong", wc.persona_cua_phien({"channel": "web"}) is None and wc.persona_cua_phien(None) is None
      and wc.persona_cua_phien({"channel": "agent:"}) is None)

# ghép đầu vào
check("ghep khong co ket qua truoc", wc.ghep_dau_vao("viết về A", "") == "viết về A")
g = wc.ghep_dau_vao("sửa đoạn 2", "x" * 9000)
check("ghep co ket qua truoc, cat 8000", g.startswith("sửa đoạn 2\n\n# Kết quả lần trước\n") and g.endswith("x" * 8000)
      and len(g) == len("sửa đoạn 2\n\n# Kết quả lần trước\n") + 8000)

# tin
check("tin_xong", wc.tin_xong(2, 3, 42, "bài") == "Lần chạy #2 · 3 bước · 42 giây\n\nbài")
check("tin_xong rong", "không có nội dung" in wc.tin_xong(1, 1, 0, ""))
check("tin_loi", wc.tin_loi(1, "Người viết", "engine chết") == "Quy trình dừng ở bước 2 (Người viết): engine chết")
check("tin_loi khong ro buoc", wc.tin_loi(None, "", "hỏng") == "Quy trình dừng vì lỗi: hỏng")
check("tin_cho_duyet", wc.tin_cho_duyet("dang", "đăng bài?") ==
      "Quy trình đang chờ duyệt bước \"dang\": đăng bài?. Bấm Duyệt ở cột phải để chạy tiếp.")
check("tin_cho_duyet khong prompt", wc.tin_cho_duyet("dang", "") ==
      "Quy trình đang chờ duyệt bước \"dang\". Bấm Duyệt ở cột phải để chạy tiếp.")


# chay(): tiêu thụ sự kiện, emit đúng khung
async def gia(evs):
    for e in evs:
        yield e


def run(evs):
    frames = []

    async def emit(f):
        frames.append(f)
    kq = asyncio.run(wc.chay(gia(evs), emit))
    return kq, frames


kq, fr = run([
    {"type": "start", "workflow": "W", "steps": 2, "run_id": "r1"},
    {"type": "step_start", "i": 0, "agent": "A", "task": "t"},
    {"type": "step_text", "i": 0, "content": "abc"},
    {"type": "step_done", "i": 0, "agent": "A", "output": "o0"},
    {"type": "step_start", "i": 1, "agent": "B", "task": "t2"},
    {"type": "step_done", "i": 1, "agent": "B", "output": "o1"},
    {"type": "done", "result": "o1"},
])
check("chay done", kq["trang_thai"] == "done" and kq["ket_qua"] == "o1" and kq["so_buoc"] == 2 and kq["run_id"] == "r1")
loai = [f["type"] for f in fr]
check("chay emit wf_event cho moi su kien tru step_text", loai.count("wf_event") == 6
      and not any(f.get("type") == "wf_event" and f.get("event", {}).get("type") == "step_text" for f in fr))
st = [f for f in fr if f["type"] == "status"]
check("chay emit status moi buoc", [f["content"] for f in st] == ["Bước 1/2: A đang làm...", "Bước 2/2: B đang làm..."])

kq, fr = run([
    {"type": "start", "workflow": "W", "steps": 1},
    {"type": "step_start", "i": 0, "agent": "A", "task": "t"},
    {"type": "step_error", "i": 0, "content": "engine chết"},
    {"type": "error", "content": "dừng"},
])
check("chay error giu buoc + agent", kq["trang_thai"] == "error" and kq["loi"] == {"i": 0, "agent": "A", "content": "dừng"})

kq, fr = run([
    {"type": "start", "workflow": "W", "steps": 2},
    {"type": "wait_user", "node": "dang", "prompt": "?", "task_id": "tk", "code": "AB"},
])
check("chay waiting", kq["trang_thai"] == "waiting" and kq["wait"]["task_id"] == "tk" and kq["wait"]["code"] == "AB")

kq, fr = run([{"type": "start", "workflow": "W", "steps": 1}])
check("chay luong dut -> error", kq["trang_thai"] == "error" and "không kết thúc" in kq["loi"]["content"])


# chay() đóng generator khi bị huỷ
class Dem:
    dong = False


async def gia_cham():
    try:
        yield {"type": "start", "workflow": "W", "steps": 1}
        await asyncio.sleep(10)
        yield {"type": "done", "result": ""}
    finally:
        Dem.dong = True


async def huy():
    async def emit(f):
        pass
    t = asyncio.ensure_future(wc.chay(gia_cham(), emit))
    await asyncio.sleep(0.05)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        return True
    return False

check("chay bi huy thi dong generator", asyncio.run(huy()) and Dem.dong)

print("\nFAIL:" if fails else "\nOK - workflow_chat", fails or "")
sys.exit(1 if fails else 0)
