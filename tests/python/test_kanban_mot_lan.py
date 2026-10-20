"""Việc Kanban chạy lại không gửi tin, đăng bài, tạo đơn lần hai (0.238.0, once_ledger.py).

Ý tưởng từ OpenMuse: mỗi thao tác ra ngoài của một việc ghi sổ theo dấu vân tay (mã việc + tool +
tham số) trước khi gọi. Đã xong thì lần sau trả kết quả cũ; kẹt giữa chừng thì không tự làm lại mà
hỏi chủ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
from pathlib import Path

import once_ledger
import turn_context
from tasks import TasksDeps, TasksFeature

JOB = "kanban:t_demo"


def _ledger(tmp_path):
    once_ledger.configure(tmp_path / "once.sqlite3")


def _counter(result="Đã gửi"):
    calls = []

    async def call(args):
        calls.append(dict(args))
        return result

    return calls, call


def test_mot_viec_mot_lan_ngoai_viec_nen_goi_thang(tmp_path):
    _ledger(tmp_path)
    calls, call = _counter()
    args = {"threadId": "123", "message": "Chào chị Lan"}
    assert asyncio.run(once_ledger.run("zalo_send_message", args, call, job=JOB)) == "Đã gửi"
    lan2 = asyncio.run(once_ledger.run("zalo_send_message", dict(args), call, job=JOB))
    assert len(calls) == 1 and lan2.startswith(once_ledger.DONE_NOTE) and "Đã gửi" in lan2
    # Tham số khác là thao tác khác.
    asyncio.run(once_ledger.run("zalo_send_message", {"threadId": "456", "message": "Chào"}, call, job=JOB))
    assert len(calls) == 2
    # Việc khác, cùng tham số: không dính nhau.
    asyncio.run(once_ledger.run("zalo_send_message", args, call, job="kanban:t_khac"))
    assert len(calls) == 3
    # Chat thường (không có job trong lượt): gọi thẳng, gọi bao nhiêu lần chạy bấy nhiêu.
    asyncio.run(once_ledger.run("zalo_send_message", args, call))
    asyncio.run(once_ledger.run("zalo_send_message", args, call))
    assert len(calls) == 5


def test_loi_ro_rang_duoc_goi_lai_loi_mo_ho_thi_khong(tmp_path):
    _ledger(tmp_path)
    calls, call = _counter("ERROR: 400 thread không tồn tại")
    asyncio.run(once_ledger.run("zalo_send_message", {"threadId": "1"}, call, job=JOB))
    asyncio.run(once_ledger.run("zalo_send_message", {"threadId": "1"}, call, job=JOB))
    assert len(calls) == 2          # dịch vụ trả lỗi rõ: chưa gửi, được thử lại

    calls, call = _counter("ERROR: gọi tool lỗi: TimeoutError: ")
    asyncio.run(once_ledger.run("dang_bai", {"page_id": "p1"}, call, job=JOB))
    lan2 = asyncio.run(once_ledger.run("dang_bai", {"page_id": "p1"}, call, job=JOB))
    assert len(calls) == 1 and lan2 == once_ledger.UNKNOWN_NOTE   # hết giờ: có thể đã đăng, không đăng lại
    assert [x["tool"] for x in once_ledger.unknowns(JOB)] == ["dang_bai"]


def test_bi_huy_giua_luc_goi_la_chua_ro(tmp_path):
    _ledger(tmp_path)

    async def call(args):
        raise asyncio.CancelledError()

    try:
        asyncio.run(once_ledger.run("tao_don", {"order_id": "9"}, call, job=JOB))
    except BaseException:
        pass
    assert len(once_ledger.unknowns(JOB)) == 1


def test_may_chu_chet_giua_chung_thanh_chua_ro(tmp_path):
    _ledger(tmp_path)
    fp = once_ledger.fingerprint(JOB, "zalo_send_message", {"threadId": "1"})
    once_ledger._conn().execute(
        "INSERT INTO writes(fp, job, tool, target, status, boot, started_at) VALUES (?,?,?,?,?,?,?)",
        (fp, JOB, "zalo_send_message", "zalo_send_message tới 1", "started", "tien-trinh-cu", 1.0))
    once_ledger._conn().commit()
    treo = once_ledger.unknowns(JOB)
    assert len(treo) == 1 and treo[0]["target"] == "zalo_send_message tới 1"
    calls, call = _counter()
    assert asyncio.run(once_ledger.run("zalo_send_message", {"threadId": "1"}, call, job=JOB)) == once_ledger.UNKNOWN_NOTE
    assert not calls


def test_doc_cau_tra_loi_cua_chu():
    assert once_ledger.answer_means_redo("Chưa gửi")
    assert once_ledger.answer_means_redo("chưa, gửi lại giúp")
    assert once_ledger.answer_means_redo("not sent")
    assert once_ledger.answer_means_redo("Gửi lại đi")
    assert not once_ledger.answer_means_redo("Đã gửi rồi")
    assert not once_ledger.answer_means_redo("đã gửi rồi, không cần gửi lại")
    assert not once_ledger.answer_means_redo("sent")
    assert not once_ledger.answer_means_redo("ok")


# ---------------------------------------------------------------- hai cửa ra ngoài


def test_plugin_muc_full_ghi_so_muc_thap_hon_thi_khong(tmp_path):
    import plugins_host
    _ledger(tmp_path)
    goi = []

    def handler(args, ctx):
        goi.append(args)
        return "ok"

    full = plugins_host._make_call({"handler": handler, "min_mode": "full", "name": "zalo_send_message"}, None, "full")
    safe = plugins_host._make_call({"handler": handler, "min_mode": "safe", "name": "javis_task"}, None, "full")

    async def trong_viec():
        tok = turn_context.bind(turn_context.make("kanban", job=JOB))
        try:
            await full({"threadId": "1", "message": "hi"})
            await full({"threadId": "1", "message": "hi"})
            await safe({"op": "list"})
            await safe({"op": "list"})
        finally:
            turn_context.reset(tok)

    asyncio.run(trong_viec())
    assert len(goi) == 3                       # gửi một lần, tool mức safe vẫn chạy mỗi lần gọi
    asyncio.run(full({"threadId": "1", "message": "hi"}))
    assert len(goi) == 4                       # ngoài việc nền: như cũ


def test_ket_noi_mcp_ghi_so_khi_khong_phai_doc(tmp_path, monkeypatch):
    import mcp_catalog
    import mcp_client
    import mcp_hub
    _ledger(tmp_path)
    goi = []

    async def call_route(route, fn, args):
        goi.append((fn, dict(args)))
        return "sent"

    loai = {"cls": "danger"}
    monkeypatch.setattr(mcp_client, "call_route", call_route)
    monkeypatch.setattr(mcp_catalog, "get", lambda cid: {})
    monkeypatch.setattr(mcp_catalog, "classify", lambda c, t, a: loai["cls"])
    monkeypatch.setattr(mcp_catalog, "allowed", lambda *a, **k: (True, ""))
    monkeypatch.setattr(mcp_hub, "_audit_append", lambda rec: None)
    ent = {"conn": {"id": "c1", "connector_id": "x", "label": "Shop"}, "tool": "create_order", "spec": {}}
    g = mcp_hub._guard(ent, "shop__create_order", "full")

    async def trong_viec():
        tok = turn_context.bind(turn_context.make("kanban", job=JOB))
        try:
            await g({"sku": "A"})
            await g({"sku": "A"})
            loai["cls"] = "read"
            await g({"sku": "A"})
            await g({"sku": "A"})
        finally:
            turn_context.reset(tok)

    asyncio.run(trong_viec())
    assert len(goi) == 3                       # tạo đơn một lần, đọc thì đọc mỗi lần


# ---------------------------------------------------------------- vòng Kanban thật


def _atomic(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


async def _workflow(*_a, **_k):
    if False:
        yield {}


def _feature(tmp_path):
    brain = tmp_path / "Brain"
    brain.mkdir(exist_ok=True)
    sent = []

    async def report(chat_id, text, **kw):
        sent.append({"chat_id": chat_id, "text": text, **kw})
        return True

    deps = TasksDeps(
        brain_root=lambda v: str(brain), atomic_write_text=_atomic, execute_workflow=_workflow,
        workflows_dir=lambda b: brain / "workflows", build_system_prompt=lambda b: "system",
        aux_model=lambda: None, safe_tools=["Read"], state_dir=tmp_path / "state",
        scheduler_brains=lambda: [str(brain)], report=report)
    f = TasksFeature(deps)
    tid = f.store.enqueue(f._ensure(str(brain)), "Gửi báo giá", "gửi báo giá cho chị Lan",
                          capability="files", status="ready", chat_id="web:s1")
    return f, tid, sent


def _chay(f, tid, execute):
    f._execute = execute
    claimed = f.store.claim(tid, "w")
    assert claimed
    asyncio.run(f._run_worker(claimed, "w"))
    return f.store.get_task(tid)


def test_chay_lai_sau_loi_khong_gui_lan_hai(tmp_path):
    _ledger(tmp_path)
    f, tid, _ = _feature(tmp_path)
    gui = []

    async def zalo(args):
        gui.append(args)
        return "Đã gửi tin"

    async def execute(task):
        # Mã việc phải có sẵn trong lượt mà không cần ai truyền tay.
        assert once_ledger.current_job() == f"kanban:{task['id']}"
        kq = await once_ledger.run("zalo_send_message", {"threadId": "lan", "message": "Báo giá"}, zalo)
        if len(gui) == 1 and kq == "Đã gửi tin":
            return "", "429 rate limit", False, {}      # lỗi tạm thời SAU khi đã gửi: việc được thử lại
        return f"Xong. {kq}", "", False, {}

    task = _chay(f, tid, execute)
    assert task["status"] == "ready"                     # đã lên lịch thử lại
    task = _chay(f, tid, execute)
    assert len(gui) == 1                                 # lần chạy lại KHÔNG gửi lần hai
    assert task["status"] == "done" and once_ledger.DONE_NOTE.strip()[:20] in task["result"]
    f.store.close()


def _treo_mot_tin(tid):
    job = f"kanban:{tid}"
    fp = once_ledger.fingerprint(job, "zalo_send_message", {"threadId": "lan", "message": "Báo giá"})
    once_ledger._conn().execute(
        "INSERT INTO writes(fp, job, tool, target, status, boot, started_at) VALUES (?,?,?,?,?,?,?)",
        (fp, job, "zalo_send_message", 'zalo_send_message tới lan "Báo giá"', "started", "tien-trinh-cu", 1.0))
    once_ledger._conn().commit()


def test_may_chu_chet_giua_luc_gui_thi_hoi_chu_roi_bo_qua(tmp_path):
    _ledger(tmp_path)
    f, tid, sent = _feature(tmp_path)
    _treo_mot_tin(tid)
    gui = []

    async def zalo(args):
        gui.append(args)
        return "Đã gửi tin"

    async def execute(task):
        kq = await once_ledger.run("zalo_send_message", {"threadId": "lan", "message": "Báo giá"}, zalo)
        return f"Xong. {kq}", "", False, {}

    task = _chay(f, tid, execute)
    # Không chạy engine, dừng lại hỏi chủ, câu hỏi nói rõ thao tác nào.
    assert task["status"] == "blocked" and task["block_kind"] == "needs_input"
    assert task["metadata"].get("once_pending") is True
    assert "zalo_send_message tới lan" in task["metadata"]["qa"][-1]["q"]
    assert not gui
    assert any(c.get("viec", {}).get("status") == "hoi" for c in sent)

    assert asyncio.run(f.answer(tid, "Đã gửi rồi"))["ok"]
    assert "once_pending" not in f.store.get_task(tid)["metadata"]
    task = _chay(f, tid, execute)
    assert not gui and task["status"] == "done"          # chủ nói đã gửi: không gửi lại
    f.store.close()


def test_chu_noi_chua_gui_thi_gui_lai_dung_mot_lan(tmp_path):
    _ledger(tmp_path)
    f, tid, _ = _feature(tmp_path)
    _treo_mot_tin(tid)
    gui = []

    async def zalo(args):
        gui.append(args)
        return "Đã gửi tin"

    async def execute(task):
        kq = await once_ledger.run("zalo_send_message", {"threadId": "lan", "message": "Báo giá"}, zalo)
        return f"Xong. {kq}", "", False, {}

    _chay(f, tid, execute)
    assert asyncio.run(f.answer(tid, "Chưa gửi"))["ok"]
    task = _chay(f, tid, execute)
    assert len(gui) == 1 and task["status"] == "done"
    f.store.close()


def test_het_gio_giua_luc_goi_thi_hoi_chu_thay_vi_bao_xong(tmp_path):
    _ledger(tmp_path)
    f, tid, _ = _feature(tmp_path)

    async def zalo(args):
        return "ERROR: gọi tool lỗi: TimeoutError: "

    async def execute(task):
        await once_ledger.run("zalo_send_message", {"threadId": "lan"}, zalo)
        return "Đã cố gửi", "", False, {}

    task = _chay(f, tid, execute)
    assert task["status"] == "blocked" and task["metadata"].get("once_pending") is True
    f.store.close()


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
