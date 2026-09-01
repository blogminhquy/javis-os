from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI

from task_store import TaskStore
from tasks import TasksDeps, TasksFeature


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


async def _workflow(*_args, **_kwargs):
    if False:
        yield {}


async def _report(*_args, **_kwargs):
    return True


def _feature(tmp_path, brains):
    state = tmp_path / "state"
    app = FastAPI()

    def resolve(value):
        candidate = Path(str(value))
        if candidate.is_dir():
            return str(candidate)
        return str(brains[0])

    deps = TasksDeps(
        brain_root=resolve,
        atomic_write_text=_atomic,
        execute_workflow=_workflow,
        workflows_dir=lambda brain: Path(resolve(brain)) / "workflows",
        build_system_prompt=lambda brain: "system",
        aux_model=lambda: None,
        safe_tools=["Read", "Write"],
        state_dir=state,
        scheduler_brains=lambda: [str(p) for p in brains],
        report=_report,
    )
    return TasksFeature(deps)


def test_legacy_json_migrates_once_and_keeps_snapshot(tmp_path):
    brain = tmp_path / "Brain A"
    legacy = brain / "Javis" / "kanban.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "orchestration": "auto",
                "tasks": [
                    {
                        "id": "t_old",
                        "title": "Legacy task",
                        "intent": "Keep this task",
                        "status": "ready",
                        "priority": 2,
                        "needs_approval": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    feature = _feature(tmp_path, [brain])
    root = feature._ensure(str(brain))
    assert feature.store.board_mode(root) == "auto"
    assert feature.store.get_task("t_old")["intent"] == "Keep this task"

    feature._snapshot(root)
    mirrored = json.loads(legacy.read_text(encoding="utf-8"))
    assert mirrored["schema"] == 2
    assert mirrored["source"] == "kanban.sqlite3"
    assert [t["id"] for t in mirrored["tasks"]] == ["t_old"]
    feature.store.close()


def test_claim_is_compare_and_set_and_targets_exact_task(tmp_path):
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    Path(root).mkdir()
    first = store.enqueue(root, "First", "one", capability="files", status="ready")
    second = store.enqueue(root, "Second", "two", capability="files", status="ready")

    claimed = store.claim(second, "worker-2")
    assert claimed and claimed["id"] == second
    assert store.get_task(first)["status"] == "ready"
    assert store.claim(second, "worker-race") is None

    done = store.complete(second, "worker-2", "finished")
    assert done["status"] == "done"
    assert store.get_task(first)["status"] == "ready"
    assert len(store.list_runs(second)) == 1
    store.close()


def test_dependency_waits_and_promotes_after_parent_done(tmp_path):
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    Path(root).mkdir()
    parent = store.enqueue(root, "Parent", "parent", capability="files", status="ready")
    child = store.enqueue(
        root, "Child", "child", deps=[parent], capability="files", status="todo"
    )
    assert store.promote_dependencies(root) == 0
    claimed = store.claim(parent, "worker-parent")
    assert claimed
    store.complete(parent, "worker-parent", "ok")
    assert store.promote_dependencies(root) == 1
    assert store.get_task(child)["status"] == "ready"
    store.close()


def test_recovers_only_codex_global_flag_blocks_once(tmp_path):
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    Path(root).mkdir()
    affected = store.enqueue(
        root, "Affected", "run", capability="code", status="ready"
    )
    other = store.enqueue(
        root, "Needs input", "wait", capability="external-write", status="ready"
    )
    assert store.claim(affected, "worker-a")
    store.block(
        affected,
        "worker-a",
        "engine",
        "Codex lỗi (exit 2): error: unexpected argument '--ask-for-approval' found",
    )
    assert store.claim(other, "worker-b")
    store.block(other, "worker-b", "needs_input", "Cần người dùng chọn tài khoản")

    assert store.recover_codex_global_flag_blocks(root) == 1
    recovered = store.get_task(affected)
    assert recovered["status"] == "ready"
    assert recovered["attempts"] == 0
    assert recovered["block_reason"] == ""
    assert store.get_task(other)["status"] == "blocked"
    assert store.recover_codex_global_flag_blocks(root) == 0
    assert any(
        event["event_type"] == "system_recovered"
        for event in store.list_events(affected)
    )
    store.close()


def test_dispatcher_scans_all_brains_and_workers_finish_independently(tmp_path):
    async def scenario():
        brain_a = tmp_path / "Brain A"
        brain_b = tmp_path / "Brain B"
        brain_a.mkdir()
        brain_b.mkdir()
        feature = _feature(tmp_path, [brain_a, brain_b])

        async def execute(task):
            await asyncio.sleep(0.02)
            return f"done {task['title']}", "", False, {"provider": "test"}

        feature._execute = execute
        roots = [feature._ensure(str(brain_a)), feature._ensure(str(brain_b))]
        ids = []
        for index, root in enumerate(roots):
            feature.store.set_orchestration(root, "auto")
            ids.append(
                feature.store.enqueue(
                    root,
                    f"Task {index}",
                    "execute",
                    capability="files",
                    status="ready",
                )
            )
        feature.start()
        for _ in range(100):
            if all(feature.store.get_task(tid)["status"] == "done" for tid in ids):
                break
            await asyncio.sleep(0.02)
        assert [feature.store.get_task(tid)["status"] for tid in ids] == ["done", "done"]
        assert all(feature.store.list_runs(tid)[0]["status"] == "completed" for tid in ids)
        await feature.shutdown()

    asyncio.run(scenario())


def test_run_selected_task_does_not_pick_older_ready_task(tmp_path):
    async def scenario():
        brain = tmp_path / "Brain"
        brain.mkdir()
        feature = _feature(tmp_path, [brain])
        root = feature._ensure(str(brain))
        older = feature.store.enqueue(
            root, "Older", "older", priority=1, capability="files", status="ready"
        )
        selected = feature.store.enqueue(
            root, "Selected", "selected", priority=3, capability="files", status="ready"
        )

        async def execute(task):
            return task["id"], "", False, {}

        feature._execute = execute
        assert await feature._claim_and_spawn(selected)
        await feature._workers[selected]
        assert feature.store.get_task(selected)["status"] == "done"
        assert feature.store.get_task(older)["status"] == "ready"
        await feature.shutdown()

    asyncio.run(scenario())


def test_auto_archive_old_terminal_tasks(tmp_path):
    """Việc một-lần đã kết thúc không nằm mãi trên bảng: done/cancelled quá hạn
    tự chuyển archived trong housekeep; task mới xong và task đang sống giữ nguyên."""
    import time as _time

    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    old_done = store.enqueue(root, "Xong lâu rồi", "old-done", status="done")
    old_cancel = store.enqueue(root, "Huỷ lâu rồi", "old-cancel", status="cancelled")
    fresh_done = store.enqueue(root, "Mới xong", "fresh-done", status="done")
    still_ready = store.enqueue(root, "Đang chờ", "ready-1", status="ready")
    past = _time.time() - 4 * 86400
    with store._lock:
        store._db.execute(
            "UPDATE tasks SET updated_at=? WHERE id IN (?,?)", (past, old_done, old_cancel)
        )
        store._db.commit()

    n = store.archive_old_terminal(root, age_days=3)
    assert n == 2
    assert store.get_task(old_done)["status"] == "archived"
    assert store.get_task(old_cancel)["status"] == "archived"
    assert store.get_task(fresh_done)["status"] == "done"
    assert store.get_task(still_ready)["status"] == "ready"
    # chạy lại không dọn thêm gì (idempotent)
    assert store.archive_old_terminal(root, age_days=3) == 0


def test_purge_terminal_xoa_han_viec_da_cat(tmp_path):
    """Dọn bảng thật sự: archived/cancelled bị XOÁ hẳn khỏi kho (kèm event + run),
    việc đang sống và việc done không bị đụng tới. Chỉ dọn đúng brain được chỉ định."""
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    other = str(tmp_path / "brain-khac")
    archived = store.enqueue(root, "Đã cất", "a", status="archived")
    cancelled = store.enqueue(root, "Đã huỷ", "c", status="cancelled")
    done = store.enqueue(root, "Đã xong", "d", status="done")
    ready = store.enqueue(root, "Đang chờ", "r", status="ready")
    other_archived = store.enqueue(other, "Brain khác", "x", status="archived")

    n = store.purge_terminal(root)
    assert n == 2
    assert store.get_task(archived) is None
    assert store.get_task(cancelled) is None
    assert store.get_task(done) is not None
    assert store.get_task(ready) is not None
    assert store.get_task(other_archived) is not None, "không được dọn lan sang brain khác"
    # event của task đã xoá cũng phải đi theo, không để lại rác mồ côi
    assert store.list_events(archived) == []
    # chạy lại không còn gì để dọn
    assert store.purge_terminal(root) == 0


def test_purge_terminal_nhan_them_done_khi_duoc_yeu_cau(tmp_path):
    """Mặc định giữ done (lịch sử việc đã làm được); chỉ dọn khi chủ nói rõ."""
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    done = store.enqueue(root, "Đã xong", "d", status="done")
    ready = store.enqueue(root, "Đang chờ", "r", status="ready")
    assert store.purge_terminal(root, statuses=("done",)) == 1
    assert store.get_task(done) is None
    assert store.get_task(ready) is not None


def test_purge_terminal_khong_dong_vao_viec_dang_chay(tmp_path):
    """Chốt an toàn: dù truyền bậy status đang sống thì cũng không được xoá."""
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    running = store.enqueue(root, "Đang chạy", "run", status="running")
    assert store.purge_terminal(root, statuses=("running", "ready", "triage")) == 0
    assert store.get_task(running) is not None


def test_clear_board_xoa_sach_tru_viec_dang_chay(tmp_path):
    """Xoá trắng bảng: mọi việc đi hết, RIÊNG việc đang có worker cầm thì giữ lại -
    xoá nó ra khỏi kho trong lúc worker còn chạy là để lại worker mồ côi."""
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    other = str(tmp_path / "brain-khac")
    ids = [
        store.enqueue(root, f"Việc {s}", s, status=s)
        for s in ("triage", "todo", "ready", "review", "blocked", "done", "cancelled", "archived")
    ]
    running = store.enqueue(root, "Đang chạy", "run", status="running")
    khac = store.enqueue(other, "Brain khác", "x", status="ready")

    n = store.clear_board(root)
    assert n == len(ids)
    assert all(store.get_task(i) is None for i in ids)
    assert store.get_task(running) is not None, "việc đang chạy phải được giữ"
    assert store.get_task(khac) is not None, "không được dọn lan sang brain khác"
    assert store.clear_board(root) == 0


# ---- Kết quả worker: lấy câu chốt, không lấy dòng suy nghĩ ----

# Ca thật (0.9.232): worker kể lể "Tôi sẽ lần theo...", "Lệnh shell vừa bị chặn..." rồi
# mới chốt. Cả chuỗi bị gom làm result → Telegram nhận một bức tường văn.
_NARRATION = [
    "Tôi sẽ lần theo chỗ ShortMason đang xử lý IPN, tìm luồng subscription hiện có.",
    "Lệnh shell vừa bị chặn bởi môi trường sandbox, nên tôi đổi sang truy vấn tối giản.",
    "Tôi đang kiểm tra xem workspace có nguồn truy cập thay thế ngoài shell không.",
]


class _FakeCli:
    """Engine giả phát đúng chuỗi event như engine thật (text… rồi final)."""

    def __init__(self, events):
        self.events = events

    def is_available(self):
        return True

    async def query(self, _prompt):
        for ev in self.events:
            yield ev


def test_query_lay_final_bo_dong_suy_nghi(tmp_path):
    """result phải là CÂU CHỐT của worker, không phải toàn bộ dòng tường thuật."""
    feature = _feature(tmp_path, [tmp_path / "Brain"])
    events = [{"type": "text", "content": t} for t in _NARRATION]
    events.append({"type": "final", "content": "Đã tạo file bonus.md, đã kiểm chứng bằng test."})
    out, error, _ = asyncio.run(feature._query(_FakeCli(events), "p"))
    assert error == ""
    assert out == "Đã tạo file bonus.md, đã kiểm chứng bằng test."
    assert "Tôi sẽ lần theo" not in out


def test_query_khong_co_final_thi_giu_text(tmp_path):
    """Engine không phát final (CLI cũ) → vẫn phải có kết quả, không được rỗng."""
    feature = _feature(tmp_path, [tmp_path / "Brain"])
    events = [{"type": "text", "content": "Chỉ có dòng này."}]
    out, _, _ = asyncio.run(feature._query(_FakeCli(events), "p"))
    assert out == "Chỉ có dòng này."


def test_needs_input_reason_lay_mot_y_ngan(tmp_path):
    """Lý do chặn là MỘT ý ngắn để đọc trên điện thoại, không phải 1000 ký tự tường thuật."""
    raw = "[[NEEDS_INPUT]]\n" + "\n".join(_NARRATION) + \
          "\nCần anh cho biết bonus cộng theo gói nào."
    reason = TasksFeature._needs_input_reason(raw)
    assert len(reason) <= 220
    assert "\n" not in reason
    # lấy Ý CUỐI (câu hỏi thật), không phải câu mở đầu kể lể
    assert "bonus cộng theo gói nào" in reason


def test_report_ngan_va_khong_lap_lai(tmp_path):
    """Thông báo Telegram: 1 dòng tiêu đề + lý do gọn. Không dán result rồi dán lại y hệt."""
    sent = []

    async def capture(chat_id, text, **kw):
        sent.append((text, kw))

    feature = _feature(tmp_path, [tmp_path / "Brain"])
    feature.deps.report = capture
    long_result = "\n".join(_NARRATION * 6)
    asyncio.run(
        feature._report(
            {
                "title": "Thiết kế credit bonus cho subscription WarriorPlus",
                "status": "blocked",
                "result": long_result,
                "block_reason": "Cần anh chốt bonus cộng theo gói nào.",
                "chat_id": "1",
            }
        )
    )
    msg, kw = sent[0]
    assert len(msg) <= 400, f"thông báo dài {len(msg)} ký tự"
    assert "Thiết kế credit bonus" in msg
    assert "Cần anh chốt bonus cộng theo gói nào." in msg
    # result tường thuật KHÔNG được dán vào tin nhắn việc bị chặn
    assert "Tôi sẽ lần theo" not in msg
    # lý do chỉ xuất hiện đúng một lần
    assert msg.count("Cần anh chốt bonus") == 1
    # Việc KẸT thì phải KÊU: đây là thứ cần người dùng ra tay, nên vẫn nổi chấm đỏ trên
    # chuông và vẫn rung thông báo đẩy.
    assert kw.get("quiet") is False, kw


def test_report_done_bao_ngan_gon(tmp_path):
    """Việc xong: báo tiêu đề + tóm tắt ngắn, không đổ nguyên bản kết quả."""
    sent = []

    async def capture(chat_id, text, **kw):
        sent.append((text, kw))

    feature = _feature(tmp_path, [tmp_path / "Brain"])
    feature.deps.report = capture
    asyncio.run(
        feature._report(
            {
                "title": "Lấy bảng giá Submagic",
                "status": "done",
                "result": "Đã lấy xong bảng giá.\n" + ("chi tiết dài " * 200),
                "chat_id": "1",
            }
        )
    )
    msg, kw = sent[0]
    assert len(msg) <= 400
    assert "Lấy bảng giá Submagic" in msg
    assert "Đã lấy xong bảng giá." in msg
    # Việc xong TRÓT LỌT thì báo LẶNG: kết quả vẫn đi qua kênh (rơi vào khung chat đã giao
    # việc) và vẫn vào hòm thư, nhưng không nổi chấm đỏ và không rung thông báo đẩy.
    assert kw.get("quiet") is True, kw


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa từng
    # chạy một assertion nào. Bảy file từng ở tình trạng đó, và bốn assertion trong số
    # chúng đang ĐỎ mà không ai biết (xem CHANGELOG 0.13.2).
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
