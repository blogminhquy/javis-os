"""Javis Core's memory index rebuilds only what changed (v6, 2026-11-27).

    python -m pytest tests/python/test_memory_index_incremental.py

Before v6 one new memory file re-read and re-chunked every file of the brain and rebuilt the whole link graph, and the
keyword stage scanned the whole table with LIKE '%term%'. Now only changed files are read and re-chunked, and the
keyword stage asks the full-text index, which holds the normalized text ("đ" as "d").
"""
from _paths import ROOT, SERVER  # noqa: F401

import os
import time

import memory_index
from memory_index import MemoryIndex


def write_fact(brain, slug, body):
    d = brain / "memory" / "facts"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(f"---\ntype: business\n---\n{body}\n", encoding="utf-8")


def make_brain(tmp_path, n=200):
    brain = tmp_path / "brain"
    for i in range(n):
        write_fact(brain, f"khach-{i}", f"Khách {i}: chị Lan {i} ở quận {i % 12}, mua combo {i % 7}.")
    write_fact(brain, "dai-ly", "Giá đại lý nước mắm 40 độ đạm: 85.000đ một chai.")
    return brain


def test_only_changed_files_are_rebuilt(tmp_path):
    brain = make_brain(tmp_path)
    idx = MemoryIndex(tmp_path / "state")
    first = idx.rebuild(brain)
    assert first["rebuilt"] and first["full"] and first["source_count"] == 201
    assert idx.rebuild(brain)["rebuilt"] is False, "nothing changed, nothing read"

    time.sleep(0.01)
    write_fact(brain, "khach-5", "Khách 5: chị Lan 5 đã chuyển sang quận 9, mua thùng 12 chai.")
    second = idx.rebuild(brain)
    assert second["rebuilt"] and not second["full"]
    assert second["changed_sources"] == 1 and second["removed_sources"] == 0
    assert second["source_count"] == 201

    found = idx.retrieve(brain, "chị Lan 5 quận nào thùng 12 chai")
    texts = " ".join(r["excerpt"] for r in found.records)
    assert "chuyển sang quận 9" in texts and "Khách 5: chị Lan 5 ở quận 5" not in texts

    os.remove(brain / "memory" / "facts" / "khach-7.md")
    third = idx.rebuild(brain)
    assert third["removed_sources"] == 1 and third["source_count"] == 200
    gone = idx.retrieve(brain, "chị Lan 7 combo")
    assert not any(r["content_ref"].endswith("khach-7.md") for r in gone.records)
    assert idx.integrity_check(brain)["ok"]


def test_touch_without_change_keeps_records(tmp_path):
    brain = make_brain(tmp_path, 20)
    idx = MemoryIndex(tmp_path / "state")
    idx.rebuild(brain)
    before = idx.integrity_check(brain)["revision"]
    f = brain / "memory" / "facts" / "khach-3.md"
    os.utime(f, (time.time() + 5, time.time() + 5))
    res = idx.rebuild(brain)
    assert res["changed_sources"] == 0, "a file touched but not changed is not re-chunked"
    assert idx.integrity_check(brain)["revision"] == before


def test_unaccented_query_matches_d_with_stroke(tmp_path):
    brain = make_brain(tmp_path, 5)
    idx = MemoryIndex(tmp_path / "state")
    found = idx.retrieve(brain, "gia dai ly nuoc mam")
    assert any("85.000" in r["excerpt"] for r in found.records), "'dai ly' finds 'đại lý'"


def test_schema_upgrade_rebuilds_everything(tmp_path):
    brain = make_brain(tmp_path, 5)
    idx = MemoryIndex(tmp_path / "state")
    idx.rebuild(brain)
    db = idx._conn()
    db.execute("UPDATE index_meta SET schema_version='memory-index-v5'")
    db.commit()
    res = idx.rebuild(brain)
    assert res["full"] and res["source_count"] == 6
    assert memory_index.INDEX_SCHEMA_VERSION == "memory-index-v6"


def test_large_memory_stays_fast(tmp_path):
    brain = make_brain(tmp_path, 3000)
    idx = MemoryIndex(tmp_path / "state")
    t = time.time()
    idx.rebuild(brain)
    full = time.time() - t
    time.sleep(0.01)
    write_fact(brain, "moi", "Ghi nhớ mới: khách sỉ ở Đà Nẵng muốn giao hàng thứ bảy.")
    t = time.time()
    res = idx.rebuild(brain)
    one = time.time() - t
    assert res["changed_sources"] == 1
    assert one < full / 3, f"adding one memory took {one:.2f}s against {full:.2f}s for the whole brain"
    t = time.time()
    found = idx.retrieve(brain, "khách sỉ Đà Nẵng giao thứ bảy")
    assert time.time() - t < 1.0
    assert any("Đà Nẵng" in r["excerpt"] for r in found.records)
