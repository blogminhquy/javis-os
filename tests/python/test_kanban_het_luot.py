"""Việc Kanban vấp "gói thuê bao hết lượt": hoãn tới đúng mốc reset, không đốt lượt thử.

    python tests/python/test_kanban_het_luot.py

Bối cảnh (2026-09-19, task t_305e712a90f4): khung chat đã có limit_resume hẹn đúng giờ, còn
hàng đợi chỉ có `_is_transient` khớp "429" rồi trả việc về ready ngay -> dispatcher nhặt lại
sau 5 giây, 3 lượt thử cháy trong vài phút, việc nằm blocked vĩnh viễn dù 47 phút sau gói mở.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import time
from pathlib import Path

from fastapi import FastAPI

import aux_engine
import tasks as tasks_mod
from task_store import TaskStore
from tasks import TasksDeps, TasksFeature


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


async def _workflow(*_a, **_k):
    if False:
        yield {}


async def _report(*_a, **_k):
    return True


def _feature(tmp_path, brain):
    deps = TasksDeps(
        brain_root=lambda v: str(brain),
        atomic_write_text=_atomic,
        execute_workflow=_workflow,
        workflows_dir=lambda b: Path(brain) / "workflows",
        build_system_prompt=lambda b: "system",
        aux_model=lambda: None,
        safe_tools=["Read", "Write"],
        state_dir=tmp_path / "state",
        scheduler_brains=lambda: [str(brain)],
        report=_report,
    )
    FastAPI()
    return TasksFeature(deps)


def test_store_not_before_hoan_viec_va_khong_dot_luot(tmp_path):
    store = TaskStore(tmp_path / "q.sqlite3")
    root = str(tmp_path / "brain"); Path(root).mkdir()
    tid = store.enqueue(root, "Viec", "lam", capability="files", status="ready")
    assert store.claim(tid, "w1")
    moc = time.time() + 3600
    t = store.block(tid, "w1", "limit", "het luot, cho", transient=True,
                    not_before=moc, keep_attempt=True)
    assert t["status"] == "ready"
    assert abs(float(t["not_before"]) - moc) < 1
    # CANARY: lượt vấp hạn mức KHÔNG tính vào attempts (claim cộng 1, block trả lại 1).
    assert int(t["attempts"]) == 0, t["attempts"]
    assert "het luot" in t["block_reason"]
    # Chưa tới giờ thì KHÔNG phải ứng viên, dù status là ready.
    assert store.next_candidate(root) is None
    # Người dùng tự kéo việc thì bỏ mốc hoãn.
    assert store.move(tid, "ready", "operator")
    assert float(store.get_task(tid)["not_before"]) == 0
    assert store.next_candidate(root)["id"] == tid
    # Claim xoá mốc hoãn (không dính sang lần chạy sau).
    assert store.claim(tid, "w2")
    assert float(store.get_task(tid)["not_before"]) == 0
    store.close()


def test_store_khong_keep_attempt_van_tinh_luot(tmp_path):
    store = TaskStore(tmp_path / "q.sqlite3")
    root = str(tmp_path / "brain"); Path(root).mkdir()
    tid = store.enqueue(root, "Viec", "lam", capability="files", status="ready",
                        max_attempts=1)
    assert store.claim(tid, "w1")
    t = store.block(tid, "w1", "limit", "khong biet moc", transient=True,
                    not_before=time.time() + 60, keep_attempt=False)
    # Hết lượt thử -> blocked hẳn, và mốc hoãn không được ghi cho việc đã chặn.
    assert t["status"] == "blocked"
    assert float(t["not_before"]) == 0
    store.close()


def test_cot_not_before_duoc_them_vao_kho_cu(tmp_path):
    import sqlite3
    path = tmp_path / "cu.sqlite3"
    db = sqlite3.connect(str(path))
    db.executescript("""
        CREATE TABLE tasks (id TEXT PRIMARY KEY, brain_root TEXT NOT NULL, title TEXT NOT NULL,
            normalized_title TEXT NOT NULL, intent TEXT NOT NULL DEFAULT '',
            route TEXT NOT NULL DEFAULT 'auto', capability TEXT NOT NULL DEFAULT 'auto',
            execution_mode TEXT NOT NULL DEFAULT 'auto', priority INTEGER NOT NULL DEFAULT 2,
            status TEXT NOT NULL DEFAULT 'triage', needs_approval INTEGER NOT NULL DEFAULT 0,
            block_kind TEXT NOT NULL DEFAULT '', block_reason TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT 'user', chat_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3, claimed_by TEXT NOT NULL DEFAULT '',
            claim_expires_at REAL NOT NULL DEFAULT 0, last_heartbeat_at REAL NOT NULL DEFAULT 0,
            current_run_id TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}', artifacts_json TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL, updated_at REAL NOT NULL);
        INSERT INTO tasks(id, brain_root, title, normalized_title, status, created_at, updated_at)
            VALUES ('t_cu', '/b', 'Cu', 'cu', 'ready', 1, 1);
    """)
    db.commit(); db.close()
    store = TaskStore(path)
    # Kho cũ mở được, cột mới có, việc cũ vẫn là ứng viên (not_before mặc định 0).
    assert float(store.get_task("t_cu")["not_before"]) == 0
    assert store.next_candidate("/b")["id"] == "t_cu"
    store.close()


def test_worker_nhan_dien_het_luot_va_hoan_dung_moc(tmp_path, monkeypatch):
    brain = tmp_path / "brain"; brain.mkdir()
    feature = _feature(tmp_path, brain)
    monkeypatch.setattr(aux_engine, "read_spec", lambda: {"provider": "antigravity-cli"})
    root = feature._ensure(str(brain))

    # 1. Lỗi rõ ràng kèm mốc reset -> ready, not_before = mốc + trừ hao, KHÔNG tính lượt.
    hit = feature._het_luot("Error: You've hit your session limit · resets in 47 minutes", "")
    assert hit and hit.engine == "antigravity-cli" and hit.reset_epoch > time.time()
    tid = feature.store.enqueue(root, "IFRS", "doc", capability="files", status="ready")
    assert feature.store.claim(tid, "w1")
    t = feature._hoan_vi_het_luot(tid, "w1", hit)
    assert t["status"] == "ready" and t["block_kind"] == "limit"
    cho = float(t["not_before"]) - time.time()
    assert 47 * 60 - 30 <= cho <= 47 * 60 + tasks_mod.LIMIT_GRACE_SECONDS + 30, cho
    assert int(t["attempts"]) == 0
    assert "Google Antigravity" in t["block_reason"] and "Tự chạy lại" in t["block_reason"]
    assert feature.store.next_candidate(root) is None   # dispatcher không nhặt lại sau 5 giây

    # 2. 429 RESOURCE_EXHAUSTED không nói giờ -> hoãn khoảng cố định, CÓ tính lượt.
    hit2 = feature._het_luot("429 RESOURCE_EXHAUSTED: quota exceeded for quota metric", "")
    assert hit2 and not hit2.reset_epoch
    tid2 = feature.store.enqueue(root, "Khac", "lam", capability="files", status="ready")
    assert feature.store.claim(tid2, "w2")
    t2 = feature._hoan_vi_het_luot(tid2, "w2", hit2)
    assert t2["status"] == "ready" and int(t2["attempts"]) == 1
    cho2 = float(t2["not_before"]) - time.time()
    assert tasks_mod.LIMIT_UNKNOWN_WAIT_SECONDS - 30 <= cho2 <= tasks_mod.LIMIT_UNKNOWN_WAIT_SECONDS + 5

    # 3. Câu hết lượt in ở chỗ KẾT QUẢ (không có error) vẫn nhận ra; bài viết thật có TRÍCH
    #    câu đó thì không.
    assert feature._het_luot("", "You've hit your session limit · resets 12pm (UTC)")
    bai = ("Khi gặp thông báo \"You've hit your session limit\" thì nên chờ. " * 12)
    assert feature._het_luot("", bai) is None
    # 4. Lỗi thường không phải hết lượt.
    assert feature._het_luot("TimeoutError: engine", "") is None
    feature.store.close()


def test_block_giu_metadata_va_artifacts(tmp_path):
    """Audit 20/09: `_finish` ghi đè metadata_json bằng thứ được truyền, block() không truyền
    gì -> điều kiện hoàn thành do specifier viết mất sạch sau một lần thử lại."""
    store = TaskStore(tmp_path / "q.sqlite3")
    root = str(tmp_path / "brain"); Path(root).mkdir()
    tid = store.enqueue(root, "Viec", "lam", capability="auto", status="ready")
    assert store.claim(tid, "w0")
    store.prepared(tid, "w0", "lam that", "files", "auto", metadata={"acceptance": ["co file"]})
    assert store.claim(tid, "w1")
    t = store.block(tid, "w1", "limit", "het luot", transient=True, not_before=time.time() + 60,
                    keep_attempt=True)
    assert t["status"] == "ready"
    assert t["metadata"].get("acceptance") == ["co file"], t["metadata"]
    store.close()


def test_muc_chay_giu_full_va_van_kep_muc_khac(tmp_path):
    assert TasksFeature._muc_chay("full", "auto") == "full"
    assert TasksFeature._muc_chay("full", "suggest") == "full"
    # specifier không tự nâng quyền được
    assert TasksFeature._muc_chay("suggest", "auto") == "suggest"
    assert TasksFeature._muc_chay("auto", "full") == "auto"
    assert TasksFeature._muc_chay("auto", "auto") == "auto"


def test_tran_giay_viec_khong_nho_hon_tran_engine(monkeypatch):
    monkeypatch.setattr(aux_engine, "bg_max_wall_s", lambda: 3600)
    assert TasksFeature._tran_giay_viec() >= 3600 + 60
    monkeypatch.setattr(aux_engine, "bg_max_wall_s", lambda: 100)
    assert TasksFeature._tran_giay_viec() == tasks_mod.WORKER_TIMEOUT_SECONDS


def test_worker_moc_qua_xa_thi_chan_han_kem_ly_do(tmp_path, monkeypatch):
    brain = tmp_path / "brain"; brain.mkdir()
    feature = _feature(tmp_path, brain)
    monkeypatch.setattr(aux_engine, "read_spec", lambda: {"provider": "anthropic-cli"})
    root = feature._ensure(str(brain))
    xa = int(time.time()) + 3 * 24 * 3600
    hit = feature._het_luot(f"Claude AI usage limit reached|{xa}", "")
    assert hit and hit.engine == "claude-code"
    tid = feature.store.enqueue(root, "Xa", "lam", capability="files", status="ready")
    assert feature.store.claim(tid, "w1")
    t = feature._hoan_vi_het_luot(tid, "w1", hit)
    assert t["status"] == "blocked" and "quá xa" in t["block_reason"]
    feature.store.close()


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
