"""A bot reads its Agent's documents, never the whole brain (owner, 2026-11-09).

    python tests/run.py bot_agent_docs      (no network)

Before, a bot's documents were every .md/.txt file of its brain (minus the operating folders), so a bot running on the
owner's main brain could quote any private note to a customer, and every question walked the whole brain. Now: the
files listed in the Documents section of the bot's Agent, the chat-scoped folder `rieng-theo-nhom/`, and the Google
files linked from the Agent (unchanged). No bot on the turn, no Agent, or an Agent with no file: no shared document."""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
from pathlib import Path

import chatbot_doc_tools
import chatbot_grounding as G
import chatbot_runtime
import turn_context


def _brain(tmp_path: Path) -> Path:
    files = {
        "sources/bang-gia.md": "# Bảng giá\nNước mắm 40 độ giá 120 nghìn một chai.\n",
        "sources/doi-tra.md": "# Đổi trả\nĐổi trả trong 7 ngày.\n",
        "01 - Daily Log/2026-11-09.md": "# Nhật ký\nDoanh thu hôm nay 9 triệu, khách VIP tên Lan.\n",
        "wiki/chien-luoc.md": "---\nchat_scope: 999\n---\n# Chiến lược giá\nGiá vốn chai 40 độ 55 nghìn.\n",
        "memory/facts/x.md": "# Ký ức\nbí mật\n",
        "rieng-theo-nhom/42/hop-dong.md": "# Hợp đồng\nKhách 42 đặt cọc 2 triệu.\n",
        "outside.md": "# Ngoài\nkhông được thấy\n",
    }
    for rel, text in files.items():
        p = tmp_path / "brain" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path / "brain"


PINNED = ("sources/bang-gia.md", "sources/doi-tra.md", "memory/facts/x.md", "../escape.md", "wiki/chien-luoc.md")


def test_only_the_agent_files_and_the_scoped_folder_are_documents(tmp_path):
    r = _brain(tmp_path)
    (tmp_path / "escape.md").write_text("# Thoát\nngoài brain\n", encoding="utf-8")
    shared = G.ds_tai_lieu(r, None, PINNED)
    # memory/ stays an operating folder even when listed; `..` never leaves the brain; a pinned `chat_scope` file
    # stays private to its chat.
    assert shared == ["sources/bang-gia.md", "sources/doi-tra.md"]
    assert G.ds_tai_lieu(r, "42", PINNED) == shared + ["rieng-theo-nhom/42/hop-dong.md"]
    assert G.ds_tai_lieu(r, "999", PINNED) == shared + ["wiki/chien-luoc.md"]
    whole = G.ds_tai_lieu(r, None)          # None: the old whole-brain set, for callers outside a bot
    assert "01 - Daily Log/2026-11-09.md" in whole and "outside.md" in whole


def test_search_never_reaches_a_note_that_is_not_the_agents(tmp_path):
    r = _brain(tmp_path)
    G.xoa_cache()
    assert G.thu_thap(r, "doanh thu hôm nay khách VIP", files=PINNED)["co"] is False
    assert G.thu_thap(r, "doanh thu hôm nay khách VIP")["co"] is True          # whole brain would have answered
    hit = G.thu_thap(r, "giá nước mắm 40 độ một chai", files=PINNED)
    assert hit["co"] and hit["nguon"] == ["sources/bang-gia.md"]
    assert G.thu_thap(r, "đặt cọc hợp đồng", chat_id="42", files=PINNED)["co"] is True
    assert G.thu_thap(r, "đặt cọc hợp đồng", chat_id="7", files=PINNED)["co"] is False
    assert G.ds_tai_lieu(r, None, ()) == []                                   # no Agent document: nothing shared


def test_bot_doc_files_reads_the_agent_documents_section(tmp_path, monkeypatch):
    r = _brain(tmp_path)
    meta = {"assets": {"files": [{"id": "1", "path": "sources/bang-gia.md"},
                                 {"id": "2", "path": "../../etc/passwd"},
                                 {"id": "3", "path": "sources/doi-tra.md", "pinned": True}]}}
    monkeypatch.setitem(chatbot_runtime._deps, "read_agent", lambda brain, slug: (meta, ""))
    monkeypatch.setitem(chatbot_runtime._deps, "brain_root", lambda brain: str(r))
    cfg = {"id": "b1", "brain": "brain", "agent": {"brain": "brain", "slug": "ban-hang"}}
    assert sorted(chatbot_runtime.bot_doc_files(cfg)) == ["sources/bang-gia.md", "sources/doi-tra.md"]
    assert chatbot_runtime.bot_doc_files({"id": "b2", "brain": "brain"}) == ()      # no Agent: no document


def test_doc_tools_read_the_bot_of_the_turn_and_fail_closed_without_one(tmp_path, monkeypatch):
    r = _brain(tmp_path)
    G.xoa_cache()
    _tools, route = chatbot_doc_tools.build(r)
    monkeypatch.setattr(chatbot_runtime, "bot_doc_files_by_id",
                        lambda bot_id: ("sources/bang-gia.md",) if bot_id == "b1" else ())

    def call(name, args, bot_id):
        turn = turn_context.make("zalo_personal", chat_id="5")
        if bot_id:
            turn["bot_id"] = bot_id
        tok = turn_context.bind(turn)
        try:
            return asyncio.run(route[name]["call"](args))
        finally:
            turn_context.reset(tok)
    listed = call("javis_docs_list", {}, "b1")
    assert "sources/bang-gia.md" in listed and "doi-tra" not in listed and "Daily Log" not in listed
    assert "ERROR" in call("javis_docs_read", {"path": "01 - Daily Log/2026-11-09.md"}, "b1")
    assert "120 nghìn" in call("javis_docs_read", {"path": "sources/bang-gia.md"}, "b1")
    assert "chưa có tài liệu" in call("javis_docs_list", {}, "")
    assert "Không có đoạn" in call("javis_docs_search", {"query": "nước mắm giá"}, "")


def test_every_bot_call_site_passes_the_agent_files():
    rt = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
    assert "chatbot_grounding.thu_thap, root, text, 4, linked[\"docs\"], chat_id, files)" in rt
    assert "chatbot_doc_tools.table_of_contents, root, chatbot_doc_tools.INDEX_MAX, chat_id,\n" in rt
    assert "chatbot_grounding.chi_muc(root, None, files)" in rt and "has_scoped_docs(root, files)" in rt
    assert "list_doc_titles(root)" not in rt
    tools = (SERVER / "chatbot_doc_tools.py").read_text(encoding="utf-8")
    assert tools.count("turn_files()") >= 3


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
