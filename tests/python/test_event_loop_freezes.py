"""Freezes found by GET /health/loop on the owner's VPS (2026-11-09).

    python tests/run.py event_loop_freezes      (no network)

The report named, by total time lost in 15 minutes: `packs.signature` under `mcp_catalog.load` (53 s), the Resonance
store waiting on a lock under /resonance/agents (26 s), a bot's document search walking the whole brain (6 to 7 s per
customer question), and system prompts built on the event loop by auto learning and reminders (2 to 5 s). These pin
the fixes."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import os
import time
from pathlib import Path

import chatbot_grounding as G
import mcp_catalog
import packs


# ---------- a bot's document search: walk only what can be a document ----------

def _old_candidates(root: Path):
    """The pre-2026-11-09 walk (`root.rglob("*")`, then the filters), kept here to compare against."""
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in G.DUOI or not p.is_file():
            continue
        folders = p.relative_to(root).parts[:-1]
        if folders and folders[0].lower() == G.SCOPED_DIR:
            if any(x.startswith(".") for x in folders):
                continue
            scope = G.file_scope(p)
            if scope is None:
                scope = (folders[1],) if len(folders) > 1 else ()
            yield p, scope
            continue
        if any(x.lower() in G.BO_QUA or x.startswith(".") for x in folders):
            continue
        if folders and folders[0].lower() in G.BO_QUA_GOC:
            continue
        if p.name.lower() in G.BO_QUA_FILE:
            continue
        yield p, G.file_scope(p)


def test_pruned_walk_finds_exactly_the_documents_the_full_walk_found(tmp_path):
    files = ["a.md", "B.txt", "x.pdf", "CLAUDE.md", "agents/a.md", "sub/agents/ok.md", "workflows/w.md",
             "Memory/m.md", ".git/x.md", "sub/.hidden/y.md", "rieng-theo-nhom/123/k.md",
             "rieng-theo-nhom/123/attachments/k2.md", "rieng-theo-nhom/.d/z.md", "rieng-theo-nhom/top.md",
             "sub/rieng-theo-nhom/q.md", "Attachments/p.md", "deep/a/b/c.markdown", "05 - Data Cache/d.md",
             "Inbox/i.md", "n/node_modules/z.md", "sub/readme.md", "sub/b.md", "sub/b/c.md",
             "shared.md", "private-note.md"]
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\ntype: x\n---\nhello\n", encoding="utf-8")
    (tmp_path / "private-note.md").write_text("---\nchat_scope: 42\n---\nsecret\n", encoding="utf-8")
    assert list(G._ung_vien(tmp_path)) == list(_old_candidates(tmp_path))


def test_pruned_walk_never_enters_a_dropped_folder(tmp_path, monkeypatch):
    for d in (".git/objects", "attachments/2026", "memory/facts", "agents"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "n.md").write_text("x", encoding="utf-8")
    (tmp_path / "doc.md").write_text("x", encoding="utf-8")
    seen = []
    real = os.walk

    def spy(top, *a, **k):
        for dirpath, dirnames, filenames in real(top, *a, **k):
            seen.append(Path(dirpath).relative_to(tmp_path).as_posix())
            yield dirpath, dirnames, filenames
    monkeypatch.setattr(G.os, "walk", spy)
    assert [p.name for p, _s in G._ung_vien(tmp_path)] == ["doc.md"]
    assert seen == ["."]


def test_document_tools_run_off_the_event_loop():
    src = (SERVER / "chatbot_doc_tools.py").read_text(encoding="utf-8")
    for name in ("_list_sync", "_search_sync", "_read_sync"):
        assert f"await asyncio.to_thread({name}" in src, name


# ---------- the MCP catalog and the pack signature: trust a recent check ----------

def test_catalog_is_not_rechecked_on_every_call_and_invalidate_forces_a_check(monkeypatch):
    calls = {"n": 0}
    real = packs.signature

    def counted():
        calls["n"] += 1
        return real()
    monkeypatch.setattr(mcp_catalog, "_sig_goi", counted)
    mcp_catalog.invalidate()
    first = mcp_catalog.load()
    for _ in range(50):
        assert mcp_catalog.load() is first
    assert calls["n"] == 1
    mcp_catalog.invalidate()
    mcp_catalog.load()
    assert calls["n"] == 2
    monkeypatch.setattr(mcp_catalog, "CHECK_S", 0.0)
    mcp_catalog.load()
    assert calls["n"] == 3


def test_pack_signature_is_reused_briefly_and_dropped_by_invalidate(monkeypatch):
    n = {"v": 0}

    def fresh():
        n["v"] += 1
        return ("sig", n["v"])
    monkeypatch.setattr(packs, "_signature_now", fresh)
    packs.invalidate()
    a = packs.signature()
    assert packs.signature() == a and n["v"] == 1
    packs.invalidate()          # what pack_install calls after any install, removal or consent
    assert packs.signature() != a
    monkeypatch.setenv("JAVIS_DISABLE_PACKS", "1")
    assert packs.signature() == "off"            # the kill switch is read live, never from the memo


def test_packs_and_removed_connectors_invalidate_the_catalog():
    src = (SERVER / "packs.py").read_text(encoding="utf-8")
    inv = src.split("def invalidate():", 1)[1].split("\ndef ", 1)[0]
    assert "mcp_catalog.invalidate()" in inv
    core = (SERVER / "core_off.py").read_text(encoding="utf-8")
    assert "mcp_catalog.invalidate()" in core.split("def dat(", 1)[1]


# ---------- the Resonance store: open once, set WAL once ----------

def test_shared_store_is_opened_once_per_file_and_reopened_when_removed(tmp_path, monkeypatch):
    import resonance_store as RS
    opened = []
    real = RS.GoalStore.__init__

    def counting(self, path=None):
        opened.append(path)
        real(self, path)
    monkeypatch.setattr(RS.GoalStore, "__init__", counting)
    p = tmp_path / "resonance.sqlite3"
    a = RS.shared(p)
    assert RS.shared(p) is a and RS.shared(p) is a and len(opened) == 1
    for f in tmp_path.iterdir():
        f.unlink()
    b = RS.shared(p)
    assert b is not a and len(opened) == 2
    RS._SHARED.pop(str(p), None)


def test_connections_set_wal_only_when_the_file_is_not_in_wal(tmp_path):
    import resonance_store as RS
    store = RS.GoalStore(tmp_path / "r.sqlite3")
    with __import__("contextlib").closing(store._conn()) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    src = (SERVER / "resonance_store.py").read_text(encoding="utf-8")
    conn = src.split("def _conn(self)", 1)[1].split("\n    def ", 1)[0].split("\n    class ", 1)[0]
    assert 'if str(c.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "wal":' in conn


def test_goal_plugin_uses_the_shared_store():
    src = (ROOT / "system" / "plugins" / "javis-goal" / "plugin.py").read_text(encoding="utf-8")
    assert "RS.GoalStore()" not in src and src.count("RS.shared()") == 3


# ---------- system prompts for background work: built on a worker thread ----------

def test_background_prompts_are_built_on_a_worker_thread():
    learn = (SERVER / "learn.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(self.deps.build_system_prompt, brain)" in learn
    assert "system_prompt=self.deps.build_system_prompt(" not in learn
    rem = (SERVER / "reminders.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(self.deps.build_system_prompt, brain)" in rem
    assert "await asyncio.to_thread(self.deps.build_agent_prompt, brain, agent)" in rem
    loops = (SERVER / "self_improve.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(self.deps.build_system_prompt, brain)" in loops
    assert 'await asyncio.to_thread(self.deps.build_agent_prompt, brain, loop["agent"])' in loops


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
