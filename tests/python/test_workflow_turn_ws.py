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


async def gia_execute(brain, slug, input="", tools=None, session_id="", source="other", input_luu=None):
    goi.append({"input": input, "source": source, "session_id": session_id, "input_luu": input_luu})
    rid = workflow_runs.get_store().bat_dau(brain=main._brain_key(brain), slug=slug, name="Viết bài",
                                           input=input, source=source, session_id=session_id)
    yield {"type": "start", "workflow": "Viết bài", "steps": 1, "run_id": rid}
    yield {"type": "step_start", "i": 0, "agent": "Người viết", "task": "viết"}
    yield {"type": "step_done", "i": 0, "agent": "Người viết", "output": "BÀI 1"}
    workflow_runs.get_store().ket_thuc(rid, "done", output="BÀI 1")
    yield {"type": "done", "result": "BÀI 1"}


_execute_that = main.execute_workflow   # giữ bản THẬT để kiểm đường ghi lịch sử ở cuối file
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


# Tài liệu người dùng gắn vào cuộc phải TỚI ĐỘNG CƠ, nhưng KHÔNG được nằm trong câu ghi vào
# kho lần chạy: cột `input` chính là dòng tóm tắt ở lịch sử chạy (cắt 60 ký tự đầu), nên dính
# khối tài liệu vào là lịch sử không còn thấy người dùng đã yêu cầu gì.
from unittest.mock import patch
with patch.object(main, "_session_block", return_value="\n\nATTACHED_FILE_AND_LINK") as context:
    run("đọc tài liệu đã gắn")
    check("dong co nhan duoc khoi tai lieu", "ATTACHED_FILE_AND_LINK" in goi[-1]["input"])
    check("khoi tai lieu lay dung phien dang mo", context.call_args.args == (sid,))
    check("cau ghi vao lich su chi la loi nguoi go",
          goi[-1]["input_luu"].startswith("đọc tài liệu đã gắn")
          and "ATTACHED_FILE_AND_LINK" not in goi[-1]["input_luu"])

# Kiểm tới TẬN KHO: chỉ sửa _luot_quy_trinh mà quên đầu execute_workflow thì cột `input` của
# bản ghi vẫn là chuỗi đưa cho động cơ. Ở đây chỉ giả `_execute_workflow_raw`, còn đường ghi
# lịch sử là bản thật.
brain_that = Path(_TMP) / "brain-that"
(brain_that / "workflows").mkdir(parents=True, exist_ok=True)
(brain_that / "workflows" / "viet-bai.md").write_text(
    "---\ntype: workflow\nname: Viết bài\nslug: viet-bai\nstatus: active\nsteps: []\n---\nmô tả\n",
    encoding="utf-8")
sid2 = store.create_session(brain=main._brain_key(str(brain_that)), engine="cli",
                            channel="workflow:viet-bai")
tho = {}


async def gia_raw(brain, slug, input="", tools=None, session_id=""):
    tho["input"] = input
    yield {"type": "start", "workflow": "Viết bài", "steps": 1}
    yield {"type": "done", "result": "XONG"}


async def _im(_frame):
    pass


_raw_that = main._execute_workflow_raw   # bản THẬT, dùng lại ở khối "bước hỏng" cuối file
main._execute_workflow_raw = gia_raw
main.execute_workflow = _execute_that
with patch.object(main, "_session_block", return_value="\n\nATTACHED_FILE_AND_LINK"):
    asyncio.run(main._luot_quy_trinh(store, sid2, "viết về B", str(brain_that), "viet-bai", _im))
dong = workflow_runs.get_store().gan_nhat(main._brain_key(str(brain_that)), slug="viet-bai", limit=1)
check("duong that: dong co van nhan khoi tai lieu", "ATTACHED_FILE_AND_LINK" in tho.get("input", ""))
check("duong that: cot input cua ban ghi khong dinh khoi tai lieu",
      len(dong) == 1 and dong[0]["input"] == "viết về B")
main.execute_workflow = gia_execute


async def gia_loi(brain, slug, input="", tools=None, session_id="", source="other", input_luu=None):
    yield {"type": "start", "workflow": "Viết bài", "steps": 1}
    yield {"type": "step_start", "i": 0, "agent": "Người viết", "task": "viết"}
    yield {"type": "error", "content": "engine chết"}

main.execute_workflow = gia_loi
text3, fr3 = run("lại đi")
check("loi van thanh tin trong chat", text3 == "Quy trình dừng ở bước 1 (Người viết): engine chết"
      and store.get_messages(sid)[-1]["content"] == text3)


async def gia_cho(brain, slug, input="", tools=None, session_id="", source="other", input_luu=None):
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


# ============================================================
# Bước HỎNG không bao giờ được báo là bước XONG
# ============================================================
# Chuyện thật ngày 15/09: một lần chạy 7 bước hiện đủ 7 tích xanh "Đã hoàn tất", còn thứ người
# dùng đọc được làm KẾT QUẢ lại là nguyên văn câu tiếng Anh của nhà cung cấp ("You've hit your
# session limit - resets 12pm (UTC)"). Hai lỗi chồng lên nhau: động cơ báo lỗi mà vẫn chảy
# xuống `step_done`, và câu báo hết lượt về theo đường câu trả lời bình thường nên không ai
# nhận ra nó là lỗi. Khối này canh cả hai, chạy bản THẬT của _execute_workflow_raw với một
# động cơ giả.
import workflow_chat  # noqa: E402

wf_loi = Path(_TMP) / "brain-loi"
(wf_loi / "workflows").mkdir(parents=True, exist_ok=True)
(wf_loi / "workflows" / "hai-buoc.md").write_text(
    "---\ntype: workflow\nname: Hai bước\nslug: hai-buoc\nstatus: active\n"
    "steps:\n"
    "  - agent: nguoi-viet\n    task: viết bài\n"
    "  - agent: nguoi-sua\n    task: 'sửa: {{prev}}'\n"
    "---\nmô tả\n", encoding="utf-8")


async def _khong_graph(brain, slug, input="", tools=None, session_id=""):
    """Đường Phase 10 không nhận lần chạy này (allocation 0) - rơi về runner cũ như thật."""
    if False:
        yield {}

main.execute_workflow_graph = _khong_graph
da_hoi = []


class _EngineGia:
    def __init__(self, evs):
        self._evs = evs

    async def query(self, prompt):
        da_hoi.append(prompt)
        for ev in self._evs:
            yield ev


def _gan_engine(kich_ban, prov="anthropic-cli"):
    """Mỗi lần workflow dựng engine cho một bước thì lấy kịch bản sự kiện kế tiếp."""
    hang = list(kich_ban)
    del da_hoi[:]

    def _helpers(brain, tools):
        def _mk(sysprompt, model=None, provider=""):
            return _EngineGia(hang.pop(0) if hang else [{"type": "final", "content": ""}])

        def _agent_sysprompt(aslug):
            ten = {"nguoi-viet": "Người viết", "nguoi-sua": "Người sửa"}.get(aslug, aslug)
            return ten, "bạn là agent", "claude-sonnet-4", prov

        return _mk, _agent_sysprompt, (lambda *a, **k: None), (lambda slug, out: out)

    main._workflow_agent_helpers = _helpers


def _chay_raw(slug, vao=""):
    async def _go():
        return [ev async for ev in _raw_that(str(wf_loi), slug, vao)]
    return asyncio.run(_go())


def _tin_chat(evs):
    """Đưa luồng sự kiện qua đúng đường dựng tin của khung chat, trả về câu người dùng đọc."""
    async def _gen():
        for e in evs:
            yield e

    kq = asyncio.run(workflow_chat.chay(_gen(), _im))
    loi = kq["loi"] or {}
    return kq["trang_thai"], workflow_chat.tin_loi(loi.get("i"), loi.get("agent", ""),
                                                  loi.get("content", ""))


# --- 1. Câu báo hết lượt về theo đường câu TRẢ LỜI (không phải lỗi) ---
_gan_engine([[{"type": "final", "content": "You've hit your session limit · resets 12pm (UTC)"}]])
evs = _chay_raw("hai-buoc")
loai = [e["type"] for e in evs]
check("het luot: KHONG co step_done va KHONG co done", "step_done" not in loai and "done" not in loai)
check("het luot: dung ngay, buoc 2 khong chay", loai.count("step_start") == 1)
_er = [e for e in evs if e["type"] == "error"]
check("het luot: mot su kien error mang so buoc + ten agent",
      len(_er) == 1 and _er[0].get("i") == 0 and _er[0].get("agent") == "Người viết")
_cau = _er[0].get("content", "")
check("het luot: cau tieng Viet chu khong phai nguyen van tieng Anh",
      "Hết lượt" in _cau and "session limit" not in _cau)
check("het luot: noi lai duoc moc reset nha cung cap da bao", "12pm" in _cau)
check("het luot: chi duong ra o trang Models, ke ten tro ly cua buoc",
      "Models" in _cau and "Người viết" in _cau)
_tt, _text = _tin_chat(evs)
check("het luot: lan chay ket thuc la LOI, khong phai xong", _tt == "error")
check("het luot: tin trong chat noi ro buoc nao, ai chay",
      _text.startswith("Quy trình dừng ở bước 1 (Người viết): ") and "Hết lượt" in _text)

# --- 2. Động cơ phát hẳn sự kiện error ---
_gan_engine([[{"type": "error", "content": "Anthropic trả về rỗng. Thử model khác."}]])
evs2 = _chay_raw("hai-buoc")
loai2 = [e["type"] for e in evs2]
check("engine loi: co step_error nhung KHONG co step_done",
      "step_error" in loai2 and "step_done" not in loai2)
check("engine loi: ket thuc bang error, khong phai done",
      loai2[-1] == "error" and "done" not in loai2)
check("engine loi: giu nguyen cau loi cua dong co",
      [e for e in evs2 if e["type"] == "error"][0]["content"].startswith("Anthropic trả về rỗng"))

# --- 3. Lần chạy SẠCH không đổi gì ---
_gan_engine([[{"type": "final", "content": "BẢN THẢO"}],
             [{"type": "final", "content": "BẢN SỬA"}]])
evs3 = _chay_raw("hai-buoc", "viết về A")
loai3 = [e["type"] for e in evs3]
check("chay sach: du 2 step_done va ket bang done",
      loai3.count("step_done") == 2 and loai3[-1] == "done" and "error" not in loai3)
check("chay sach: ket qua la output buoc cuoi", evs3[-1].get("result") == "BẢN SỬA")
check("chay sach: {{prev}} van la output buoc truoc",
      len(da_hoi) == 2 and "BẢN THẢO" in da_hoi[1])

# --- 4. Agent TRÍCH câu báo hết lượt trong bài viết của nó ---
# Đây là chính cái loại hỏng mà bản vá trên sinh ra để dập, chỉ đổi chiều: nhận nhầm một câu
# trích là vứt luôn bài viết thật (không có step_done nên không sang {{prev}}) rồi báo người
# dùng hết gói trong khi gói vẫn còn.
_trich = ('Bài viết: khi gặp thông báo "You have reached your session limit" '
          'thì bạn nên chờ tới giờ reset.')
_gan_engine([[{"type": "final", "content": _trich}],
             [{"type": "final", "content": "BẢN SỬA"}]])
evs4 = _chay_raw("hai-buoc")
loai4 = [e["type"] for e in evs4]
check("cau TRICH trong bai KHONG bi coi la het luot",
      loai4.count("step_done") == 2 and loai4[-1] == "done" and "error" not in loai4)
check("cau TRICH: bai viet that van sang duoc {{prev}}",
      len(da_hoi) == 2 and _trich in da_hoi[1])
check("cau TRICH: van la ket qua cua buoc 1",
      [e for e in evs4 if e["type"] == "step_done"][0].get("output") == _trich)
# Bài DÀI có câu báo thật ở cuối cũng không tính: bước đã làm ra việc thật.
_gan_engine([[{"type": "final", "content": "x" * 600 + "\nYou've hit your session limit"}],
             [{"type": "final", "content": "BẢN SỬA"}]])
check("bai DAI co cau bao o cuoi cung khong bi coi la het luot",
      "error" not in [e["type"] for e in _chay_raw("hai-buoc")])

# --- 5. Bước hỏng phải để lại LÝ DO trên đúng dòng bước trong kho lần chạy ---
# Nhánh hết lượt về theo đường câu trả lời nên không hề có step_error nào; thiếu nó thì dòng
# bước lưu với error rỗng, và bảng chạy của Studio quay mãi vì nó chỉ tắt vòng quay ở
# step_done / step_error.
main._execute_workflow_raw = _raw_that
_gan_engine([[{"type": "final", "content": "You've hit your session limit · resets 12pm (UTC)"}]])


async def _gom_lich_su():
    ra = []
    async for ev in _execute_that(str(wf_loi), "hai-buoc", "viết về A", source="web"):
        ra.append(ev)
    return ra

evs5 = asyncio.run(_gom_lich_su())
loai5 = [e["type"] for e in evs5]
check("het luot: co phat step_error truoc su kien error",
      "step_error" in loai5 and loai5.index("step_error") < loai5.index("error"))
_dong5 = workflow_runs.get_store().gan_nhat(main._brain_key(str(wf_loi)), slug="hai-buoc", limit=1)
_day5 = workflow_runs.get_store().lay(_dong5[0]["id"]) if _dong5 else {}
_buoc5 = (_day5.get("steps") or [{}])[0]
check("het luot: dong buoc trong kho lan chay mang cau loi tieng Viet",
      "Hết lượt" in str(_buoc5.get("error") or ""))
check("het luot: ban ghi lan chay ket thuc la error", _day5.get("status") == "error")
main._execute_workflow_raw = gia_raw

print("\nFAIL:" if fails else "\nOK - workflow_turn_ws", fails or "")
sys.exit(1 if fails else 0)
