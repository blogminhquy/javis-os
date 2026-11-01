"""Memory recall stops echoing, stops flagging false conflicts, and knows secondary indexes (#934).

    python tests/run.py memory_recall_noise

Reported on 0.420.2 from a real brain:
  1. _log_agent_run wrote the task with the recall block and the UI context block still in front, and the memory index
     took agents/<slug>/runs/*.md as memories, so old chat excerpts came back as fresh recalls.
  2. The conflict check grouped records by the label before the first ":"; the facts template's "**Vì sao:**" and
     "**Áp dụng:**" lines made any two recalled facts look like a conflict.
  3. always_on matched any substring of the path: "...-google-business-profile.md" took core slots on every turn.
  5. learn and the curator only knew MEMORY.md and appended duplicates of memories listed in a secondary index.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-memory-noise-"))

from capability_registry import brain_scope  # noqa: E402
import memory_index  # noqa: E402
from memory_index import MemoryIndex  # noqa: E402
import memory_index_files  # noqa: E402
import memory_control  # noqa: E402


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _refs(db, brain):
    return {r[0] for r in db.execute("SELECT content_ref FROM memory_records WHERE scope=?", (brain_scope(brain),))}


# ---- 1. agent run logs: not indexed, and logged without the injected blocks
def test_agent_run_logs_are_not_memory(tmp_path):
    brain = tmp_path / "b"
    _write(brain / "memory" / "facts" / "gia-ban.md", "---\ntype: business\n---\n- Giá bán: 120 nghìn một hộp.\n")
    _write(brain / "memory" / "agents" / "sales" / "runs" / "2026-10-23.md",
           "\n## 09:00\n**Task:** giá bán bao nhiêu\n\n**Kết quả:** Giá bán: 99 nghìn một hộp.\n")
    _write(brain / "memory" / "agents" / "sales" / "MEMORY.md", "## Bài học (tự học)\n- Báo giá kèm phí ship.\n")
    idx = MemoryIndex(tmp_path / "state")
    idx.rebuild(brain)
    refs = _refs(sqlite3.connect(tmp_path / "state" / "memory_index.db"), brain)
    assert "memory/facts/gia-ban.md" in refs
    assert not any("/runs/" in r for r in refs), refs
    assert "memory/agents/sales/MEMORY.md" in refs, "the agent's own memory (lessons, rules) stays indexed"


def test_run_log_path_rule():
    assert memory_index._is_agent_run_log("agents/sales/runs/2026-10-23.md")
    assert not memory_index._is_agent_run_log("agents/sales/MEMORY.md")
    assert not memory_index._is_agent_run_log("facts/runs.md")


def test_run_log_task_drops_injected_blocks():
    import main
    import chat_recall
    user = "Soạn báo giá cho khách sỉ"
    recall = chat_recall.block([{"title": "chat cũ", "snippet": "giá sỉ là 90 nghìn"}])
    ui = "[NGỮ CẢNH GIAO DIỆN: trang=chat]\n\n"
    assert main._agent_run_task_text(recall + ui + user) == user
    assert main._agent_run_task_text(ui + user) == user
    assert main._agent_run_task_text(user) == user
    # A workflow step prompt with no blocks is kept as it is.
    assert main._agent_run_task_text("Bước 2: tổng hợp") == "Bước 2: tổng hợp"


# ---- 2. generic labels are not a subject
def test_generic_labels_do_not_make_conflicts(tmp_path):
    brain = tmp_path / "b"
    _write(brain / "memory" / "facts" / "kiem-chung.md",
           "---\ntype: decision\n---\n# Kiểm chứng trước khi nói\n\n**Vì sao:** chủ bị báo sai số một lần nên mọi số phải "
           "kiểm chứng với MCP trước khi nói ra.\n")
    _write(brain / "memory" / "facts" / "danh-gia-google.md",
           "---\ntype: decision\n---\n# Trả lời đánh giá Google\n\n**Vì sao:** khách đọc câu trả lời đánh giá trước khi "
           "ghé tiệm nên phải trả lời đánh giá trong ngày.\n")
    idx = MemoryIndex(tmp_path / "state")
    got = idx.retrieve(brain, "vì sao phải kiểm chứng và trả lời đánh giá")
    assert len(got.records) >= 2, got.records
    assert not got.conflicts, got.conflicts


def test_real_subjects_still_conflict(tmp_path):
    brain = tmp_path / "b"
    _write(brain / "memory" / "facts" / "gia-a.md", "---\ntype: business\n---\n- Giá hộp quà: 120 nghìn.\n")
    _write(brain / "memory" / "facts" / "gia-b.md", "---\ntype: business\n---\n- Giá hộp quà: 150 nghìn.\n")
    got = MemoryIndex(tmp_path / "state").retrieve(brain, "giá hộp quà bao nhiêu")
    assert got.conflicts, "CANARY: two files giving the same subject different values is still a conflict"


# ---- 3. always_on by path segment, not substring
def test_always_on_path_rule():
    on = memory_index._always_on_path
    assert on("memory/identity.md")
    assert on("memory/facts/profile-chu-shop.md")
    assert on("memory/profile/ten.md")
    assert on("memory/core-facts.md")
    assert not on("memory/facts/reference-javis-google-business-profile.md")
    assert not on("memory/facts/identityless.md")


def test_frontmatter_always_on_still_works(tmp_path):
    brain = tmp_path / "b"
    _write(brain / "memory" / "facts" / "x.md", "---\nalways_on: true\n---\n- Tên chủ: Bình, bán đồ gốm.\n")
    _write(brain / "memory" / "facts" / "google-business-profile.md", "---\ntype: business\n---\n- GBP: chưa có quyền.\n")
    idx = MemoryIndex(tmp_path / "state")
    idx.rebuild(brain)
    db = sqlite3.connect(tmp_path / "state" / "memory_index.db")
    core = {r[0] for r in db.execute("SELECT content_ref FROM memory_records WHERE scope=? AND always_on=1",
                                     (brain_scope(brain),))}
    assert core == {"memory/facts/x.md"}, core


# ---- 5. secondary indexes
def _brain_with_secondary(tmp_path):
    mem = tmp_path / "b" / "memory"
    _write(mem / "MEMORY.md", "# Bộ nhớ\n- [Lõi](facts/loi.md) - điều cốt lõi\n")
    _write(mem / "muc-luc-thuong-hieu.md", "# Mục lục thương hiệu\n- [Màu thương hiệu](facts/mau.md) - cam đất\n")
    _write(mem / "tang-phu.md", "---\ntype: index\n---\n- [Giờ mở cửa](facts/gio.md) - 8h-22h\n")
    _write(mem / "ghi-chu.md", "---\ntype: user\n---\n- [Không phải mục lục](facts/khac.md)\n")
    for slug in ("loi", "mau", "gio", "khac", "moi"):
        _write(mem / "facts" / f"{slug}.md", "---\ntype: business\n---\n- " + slug + "\n")
    return mem


def test_secondary_index_detection(tmp_path):
    mem = _brain_with_secondary(tmp_path)
    names = [p.name for p in memory_index_files.secondary_indexes(mem)]
    assert names == ["muc-luc-thuong-hieu.md", "tang-phu.md"], names
    assert memory_index_files.listed(mem, "mau") and memory_index_files.listed(mem, "gio")
    assert not memory_index_files.listed(mem, "khac")


def test_titles_come_from_every_index(tmp_path):
    mem = _brain_with_secondary(tmp_path)
    titles = memory_control._index_titles(mem)
    assert titles.get("mau") == "Màu thương hiệu" and titles.get("gio") == "Giờ mở cửa" and titles.get("loi") == "Lõi"


def test_learn_does_not_duplicate_into_memory_md(tmp_path):
    import learn
    mem = _brain_with_secondary(tmp_path)
    root = tmp_path / "b"
    writes = {}

    def atomic(path, text):
        Path(path).write_text(text, encoding="utf-8")
        writes[str(path)] = text

    fake = SimpleNamespace(deps=SimpleNamespace(brain_memory_dir=lambda b: mem, atomic_write_text=atomic))
    merge = learn.LearnFeature._merge_memory_index
    before = (mem / "MEMORY.md").read_text(encoding="utf-8")
    merge(fake, "b", "mau", "Màu thương hiệu", "cam đất", [], root)
    assert (mem / "MEMORY.md").read_text(encoding="utf-8") == before, "a memory in a secondary index is not re-added"
    merge(fake, "b", "moi", "Mới", "chưa có ở đâu", [], root)
    assert "facts/moi.md" in (mem / "MEMORY.md").read_text(encoding="utf-8"), "CANARY: an unlisted memory is still added"


def test_learn_prompt_index_reads_every_index(tmp_path):
    import learn
    mem = _brain_with_secondary(tmp_path)
    cls = learn.LearnFeature
    fake = SimpleNamespace(deps=SimpleNamespace(brain_memory_dir=lambda b: mem), MEMORY_INDEX_PROMPT_MAX=16000)
    text = cls._read_memory_index(fake, "b")
    assert "facts/loi.md" in text and "facts/mau.md" in text and "facts/gio.md" in text


def test_schema_version_bumped():
    assert memory_index.INDEX_SCHEMA_VERSION != "memory-index-v3", "old indexes must rebuild with the new rules"
