"""Hai brain có file bộ nhớ giống hệt nhau phải cùng dựng được chỉ mục bộ nhớ.

    python tests/run.py memory_index_hai_brain

Lỗi thật (06/09/2026): Brain Default và Japan VIP Content cùng có
`memory/facts/cach-lam-viec-chuan.md` và cùng một dòng ở `memory/MEMORY.md`. record_id chỉ
băm (đường dẫn tương đối | dòng | nội dung), KHÔNG có scope, mà bảng memory_records lại khai
record_id là khóa chính. rebuild() của brain thứ hai xóa bản ghi cũ theo scope của NÓ rồi
INSERT, đụng ngay bản ghi cùng id còn nằm đó của brain thứ nhất:
`sqlite3.IntegrityError: UNIQUE constraint failed: memory_records.record_id`.

Hệ quả: nguồn bộ nhớ của đường tiết kiệm ở brain đó không dựng được, lượt nào cũng lỗi, và
không có dòng nào báo cho người dùng. Cách né tạm là đổi tên file ở một brain, tức là bộ nhớ
chung giữa hai brain bị coi là lỗi. Ba bài kiểm dưới đây khóa lại: cả hai cùng dựng được,
truy vấn always_on của mỗi scope chỉ trả bản ghi của scope đó, và chỉ mục cũ (v2) tự dựng lại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sqlite3
from pathlib import Path

import pytest

from capability_registry import brain_scope
from memory_index import INDEX_SCHEMA_VERSION, MemoryIndex

FACT_MD = (
    "---\ntype: preference\nalways_on: true\n---\n"
    "- Cách làm việc chuẩn: báo cáo ngắn gọn, số thật từ MCP, luôn so với kỳ trước.\n"
)
MEMORY_MD = (
    "# Bộ nhớ\n"
    "- [Cách làm việc chuẩn](facts/cach-lam-viec-chuan.md) - báo cáo ngắn, số thật, so kỳ trước\n"
)
FACT_REL = "memory/facts/cach-lam-viec-chuan.md"


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _brain(root: Path, name: str) -> Path:
    """Hai brain chép chung một bộ file bộ nhớ - đúng tình huống gây lỗi."""
    brain = root / name
    _write(brain / "memory" / "MEMORY.md", MEMORY_MD)
    _write(brain / FACT_REL, FACT_MD)
    return brain


def _ids(db: sqlite3.Connection, scope: str) -> set[str]:
    return {row[0] for row in db.execute(
        "SELECT record_id FROM memory_records WHERE scope=?", (scope,))}


def test_hai_brain_giong_het_cung_dung_duoc_chi_muc(tmp_path):
    a = _brain(tmp_path, "brain-default")
    b = _brain(tmp_path, "japan-vip-content")
    index = MemoryIndex(tmp_path / "state")

    built_a = index.rebuild(a)
    built_b = index.rebuild(b)   # trước bản vá: IntegrityError ngay tại đây
    assert built_a["rebuilt"] is True and built_b["rebuilt"] is True
    assert built_a["record_count"] == built_b["record_count"] >= 2

    # Dựng brain sau không được xóa hay đè lên brain trước.
    assert index.rebuild(a)["rebuilt"] is False
    assert index.integrity_check(a)["ok"] is True
    assert index.integrity_check(b)["ok"] is True

    db = sqlite3.connect(tmp_path / "state" / "memory_index.db")
    ids_a, ids_b = _ids(db, brain_scope(a)), _ids(db, brain_scope(b))
    assert len(ids_a) == built_a["record_count"]
    assert len(ids_b) == built_b["record_count"]
    assert ids_a.isdisjoint(ids_b), "cùng nội dung ở hai brain phải là hai bản ghi khác id"
    if index._fts:
        fts_count = db.execute("SELECT COUNT(*) FROM memory_records_fts").fetchone()[0]
        assert fts_count == len(ids_a) + len(ids_b)
    db.close()


def test_always_on_cua_moi_scope_chi_tra_ban_ghi_cua_scope_do(tmp_path):
    a = _brain(tmp_path, "brain-default")
    b = _brain(tmp_path, "japan-vip-content")
    index = MemoryIndex(tmp_path / "state")
    index.rebuild(a)
    index.rebuild(b)

    db = sqlite3.connect(tmp_path / "state" / "memory_index.db")
    for brain in (a, b):
        scope = brain_scope(brain)
        rows = db.execute(
            "SELECT scope,content_ref FROM memory_records WHERE scope=? AND always_on=1",
            (scope,),
        ).fetchall()
        assert [row[0] for row in rows] == [scope]
        assert rows[0][1] == FACT_REL

        found = index.retrieve(brain, "Cách làm việc chuẩn của mình là gì?")
        assert "identity_core" in found.stages
        assert found.records
        assert {record["scope"] for record in found.records} == {scope}
        assert any(FACT_REL in ref for record in found.records for ref in record["source_refs"])
    db.close()


def test_chi_muc_cu_v2_tu_dung_lai_khi_len_ban_moi(tmp_path):
    # Bản vá đổi cách đánh record_id, nên chỉ mục đã dựng bằng bản cũ phải được dựng lại dù
    # không file nào đổi. Cơ chế là so schema_version; bài này khóa việc số hiệu đã nhích.
    a = _brain(tmp_path, "brain-default")
    index = MemoryIndex(tmp_path / "state")
    assert index.rebuild(a)["rebuilt"] is True
    assert index.rebuild(a)["rebuilt"] is False
    index.close()

    db = sqlite3.connect(tmp_path / "state" / "memory_index.db")
    db.execute("UPDATE index_meta SET schema_version='memory-index-v2'")
    db.commit()
    db.close()

    assert INDEX_SCHEMA_VERSION != "memory-index-v2"
    index = MemoryIndex(tmp_path / "state")
    assert index.rebuild(a)["rebuilt"] is True


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa
    # từng chạy một assertion nào.
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
