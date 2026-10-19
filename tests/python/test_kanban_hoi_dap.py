"""Việc Kanban dừng lại hỏi, chủ trả lời, việc chạy tiếp với câu trả lời (0.235.0).

Trước bản này `[[NEEDS_INPUT]]` chặn được việc nhưng không có chỗ trả lời: bấm Thử lại là chạy
lại từ đầu mà không ai nói cho worker câu trả lời, nên nó hỏi lại y hệt. Ý tưởng `ask_user` của
OpenMuse: câu hỏi là một trạng thái của việc, câu trả lời được nạp vào lần chạy sau.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import importlib.util
from pathlib import Path

from fastapi import FastAPI  # noqa: F401  - giữ cùng môi trường nạp với các test Kanban khác

from task_store import TaskStore
from tasks import TasksDeps, TasksFeature


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


async def _workflow(*_args, **_kwargs):
    if False:
        yield {}


def _feature(tmp_path, report):
    brain = tmp_path / "Brain"
    brain.mkdir(exist_ok=True)
    deps = TasksDeps(
        brain_root=lambda value: str(brain),
        atomic_write_text=_atomic,
        execute_workflow=_workflow,
        workflows_dir=lambda b: brain / "workflows",
        build_system_prompt=lambda b: "system",
        aux_model=lambda: None,
        safe_tools=["Read", "Write"],
        state_dir=tmp_path / "state",
        scheduler_brains=lambda: [str(brain)],
        report=report,
    )
    return TasksFeature(deps), brain


def _sent():
    calls = []

    async def report(chat_id, text, **kw):
        calls.append({"chat_id": chat_id, "text": text, **kw})
        return True

    return calls, report


def _run_once(feature, tid, result):
    """Nhận việc rồi chạy một lượt worker với kết quả cho sẵn."""
    async def execute(task):
        return result, "", "[[NEEDS_INPUT]]" in result, {"provider": "test"}

    feature._execute = execute
    claimed = feature.store.claim(tid, "w-test")
    assert claimed, "phải nhận được việc"
    asyncio.run(feature._run_worker(claimed, "w-test"))
    return feature.store.get_task(tid)


def _new_task(feature, brain, chat_id="web:sess-1"):
    root = feature._ensure(str(brain))
    return feature.store.enqueue(root, "Gửi báo giá", "gửi báo giá cho khách mới",
                                 capability="files", status="ready", chat_id=chat_id)


def test_hoi_luu_cau_hoi_va_bao_rieng_mot_lan(tmp_path):
    calls, report = _sent()
    feature, brain = _feature(tmp_path, report)
    tid = _new_task(feature, brain)

    task = _run_once(feature, tid, "Đã soạn xong báo giá.\n[[NEEDS_INPUT]] Gửi cho khách nào, anh Minh hay chị Lan?")
    assert task["status"] == "blocked" and task["block_kind"] == "needs_input"
    qa = task["metadata"]["qa"]
    assert len(qa) == 1 and qa[0]["q"] == "Gửi cho khách nào, anh Minh hay chị Lan?"
    assert "Đã soạn xong báo giá" in qa[0]["progress"] and "a" not in qa[0]
    assert task["attempts"] == 1

    # Báo RIÊNG về đúng người giao việc, có câu hỏi, có khoá chống trùng theo câu hỏi.
    assert len(calls) == 1, calls
    c = calls[0]
    assert c["chat_id"] == "web:sess-1"
    assert "Gửi cho khách nào" in c["text"] and tid in c["text"]
    assert c["viec"]["status"] == "hoi" and c["viec"]["id"] == tid
    assert c["dedup"].startswith(f"ask:{tid}:")
    assert c["quiet"] is False
    feature.store.close()


def test_tra_loi_dua_viec_ve_hang_doi_khong_ton_luot_va_nap_vao_prompt(tmp_path):
    calls, report = _sent()
    feature, brain = _feature(tmp_path, report)
    tid = _new_task(feature, brain)
    _run_once(feature, tid, "Đã soạn xong báo giá.\n[[NEEDS_INPUT]] Gửi cho khách nào?")
    before = feature.store.get_task(tid)["attempts"]

    out = asyncio.run(feature.answer(tid, "Gửi chị Lan, qua Zalo", brain=str(brain)))
    assert out["ok"] and out["status"] == "ready", out
    task = feature.store.get_task(tid)
    assert task["status"] == "ready" and task["block_kind"] == "" and task["block_reason"] == ""
    assert task["metadata"]["qa"][-1]["a"] == "Gửi chị Lan, qua Zalo"
    assert any(e["event_type"] == "answered" for e in feature.store.list_events(tid))

    # Trả lời lần hai cho câu đã trả lời: từ chối, không chạy lại việc thêm lần nữa.
    again = asyncio.run(feature.answer(tid, "Gửi anh Minh", brain=str(brain)))
    assert not again["ok"]

    # Lần chạy kế: lượt thử KHÔNG tăng so với lần chạy đã hỏi, và prompt mang câu hỏi, câu trả
    # lời cùng phần lần trước đã làm.
    claimed = feature.store.claim(tid, "w-2")
    assert claimed["attempts"] == before
    seen = {}

    async def query(cli, prompt):
        seen["prompt"] = prompt
        return "Đã gửi báo giá cho chị Lan.", "", []

    del feature._execute          # bỏ bản giả của _run_once, chạy _execute thật để đọc prompt
    feature._base_cli = lambda *a, **k: type("Cli", (), {})()
    feature._query = query
    asyncio.run(feature._execute(claimed))
    p = seen["prompt"]
    assert "HỎI ĐÁP VỚI CHỦ" in p
    assert "Gửi cho khách nào?" in p and "Gửi chị Lan, qua Zalo" in p
    assert "Đã soạn xong báo giá" in p and "KHÔNG làm lại" in p
    feature.store.close()


def test_hoi_nhieu_lan_giu_lich_su_theo_thu_tu(tmp_path):
    calls, report = _sent()
    feature, brain = _feature(tmp_path, report)
    tid = _new_task(feature, brain)
    _run_once(feature, tid, "[[NEEDS_INPUT]] Gửi cho khách nào?")
    asyncio.run(feature.answer(tid, "Chị Lan", brain=str(brain)))
    _run_once(feature, tid, "[[NEEDS_INPUT]] Giá có gồm VAT không?")
    asyncio.run(feature.answer(tid, "Đã gồm VAT", brain=str(brain)))

    task = feature.store.get_task(tid)
    assert [x["q"] for x in task["metadata"]["qa"]] == ["Gửi cho khách nào?", "Giá có gồm VAT không?"]
    khoi = TasksFeature._hoi_dap(task)
    assert khoi.index("Chị Lan") < khoi.index("Đã gồm VAT")
    # Hai câu hỏi khác nhau là hai tin báo, mỗi tin một khoá riêng.
    keys = [c["dedup"] for c in calls if c.get("viec", {}).get("status") == "hoi"]
    assert len(keys) == 2 and keys[0] != keys[1]
    assert task["attempts"] == 0

    # Worker hỏi lại ĐÚNG câu cũ sau khi đã được trả lời: lượt mới, khoá mới, vẫn báo.
    _run_once(feature, tid, "[[NEEDS_INPUT]] Gửi cho khách nào?")
    keys = [c["dedup"] for c in calls if c.get("viec", {}).get("status") == "hoi"]
    assert len(keys) == 3 and len(set(keys)) == 3
    feature.store.close()


def test_tra_loi_bi_tu_choi_dung_luc(tmp_path):
    calls, report = _sent()
    feature, brain = _feature(tmp_path, report)
    tid = _new_task(feature, brain)
    # Việc chưa hỏi gì thì không nhận câu trả lời.
    assert not asyncio.run(feature.answer(tid, "gì đó", brain=str(brain)))["ok"]
    _run_once(feature, tid, "[[NEEDS_INPUT]] Gửi cho khách nào?")
    assert not asyncio.run(feature.answer(tid, "   ", brain=str(brain)))["ok"]
    assert not asyncio.run(feature.answer("t_khong_co", "Chị Lan"))["ok"]
    assert asyncio.run(feature.answer(tid, "Chị Lan"))["ok"]   # thẻ trong khung chat không gửi brain
    feature.store.close()


def test_viec_ket_tu_ban_cu_van_tra_loi_duoc(tmp_path):
    """Việc chặn ở needs_input từ trước 0.235.0 không có sổ hỏi đáp, câu hỏi nằm trong block_reason."""
    store = TaskStore(tmp_path / "q.sqlite3")
    root = str(tmp_path / "brain")
    Path(root).mkdir()
    tid = store.enqueue(root, "Cũ", "việc cũ", capability="files", status="ready")
    store.claim(tid, "w")
    store.block(tid, "w", "needs_input", "Thiếu số tài khoản nhận tiền")
    task, err = store.answer(tid, "VCB 0123")
    assert not err and task["status"] == "ready"
    assert task["metadata"]["qa"] == [dict(task["metadata"]["qa"][0])]
    assert task["metadata"]["qa"][0]["q"] == "Thiếu số tài khoản nhận tiền"
    assert task["metadata"]["qa"][0]["a"] == "VCB 0123"
    store.close()


def test_chua_dat_dieu_kien_cung_thanh_cau_hoi_tra_loi_duoc(tmp_path):
    calls, report = _sent()
    feature, brain = _feature(tmp_path, report)
    tid = _new_task(feature, brain)

    async def accept(task, result):
        return False, "thiếu ảnh sản phẩm", "ai"

    feature._check_acceptance = accept
    task = _run_once(feature, tid, "Đã viết bài.")
    assert task["status"] == "blocked" and task["block_kind"] == "needs_input"
    assert "thiếu ảnh sản phẩm" in task["metadata"]["qa"][-1]["q"]
    assert asyncio.run(feature.answer(tid, "Dùng ảnh trong attachments/sp1.jpg", brain=str(brain)))["ok"]
    feature.store.close()


def _plugin():
    spec = importlib.util.spec_from_file_location(
        "javis_task_plugin_hoi_dap", ROOT / "system" / "plugins" / "javis-task" / "plugin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tool_javis_task_op_answer(tmp_path, monkeypatch):
    import tasks as tasks_mod
    calls, report = _sent()
    feature, brain = _feature(tmp_path, report)
    monkeypatch.setattr(tasks_mod, "current", lambda: feature)
    m = _plugin()

    class Ctx:
        vault_root = str(brain)

    assert "Không có việc nào" in asyncio.run(m._chay({"op": "answer", "answer": "x"}, Ctx()))

    a = _new_task(feature, brain)
    _run_once(feature, a, "[[NEEDS_INPUT]] Gửi cho khách nào?")
    # list cho model thấy việc nào đang chờ trả lời và câu hỏi là gì.
    ds = asyncio.run(m._chay({"op": "list"}, Ctx()))
    assert "CHỜ TRẢ LỜI: Gửi cho khách nào?" in ds

    # Đúng một việc đang chờ: thiếu id vẫn chuyển đúng việc đó.
    out = asyncio.run(m._chay({"op": "answer", "answer": "Chị Lan"}, Ctx()))
    assert out.startswith("Đã chuyển câu trả lời cho việc " + a), out
    assert feature.store.get_task(a)["metadata"]["qa"][-1]["a"] == "Chị Lan"
    # Điều phối đang tắt: phải nói thẳng việc chỉ nằm xếp hàng.
    assert "AI tự vận hành" in out

    # Hai việc cùng chờ: không đoán, trả danh sách để model hỏi lại.
    b = feature.store.enqueue(feature._ensure(str(brain)), "Đăng bài", "đăng bài fanpage",
                              capability="files", status="ready")
    c = feature.store.enqueue(feature._ensure(str(brain)), "Chạy ads", "chạy ads",
                              capability="files", status="ready")
    _run_once(feature, b, "[[NEEDS_INPUT]] Đăng lúc mấy giờ?")
    _run_once(feature, c, "[[NEEDS_INPUT]] Ngân sách bao nhiêu?")
    out = asyncio.run(m._chay({"op": "answer", "answer": "8 giờ tối"}, Ctx()))
    assert out.startswith("ERROR") and b in out and c in out
    out = asyncio.run(m._chay({"op": "answer", "id": b, "answer": "8 giờ tối"}, Ctx()))
    assert out.startswith("Đã chuyển"), out
    assert "ERROR" in asyncio.run(m._chay({"op": "answer", "id": "t_khac", "answer": "x"}, Ctx()))
    feature.store.close()


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
