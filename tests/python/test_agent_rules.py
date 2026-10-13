"""Owner rules survive self-learning (incident 2026-10-13).

    python tests/run.py agent_rules     (no network)

The owner told an agent "messages sent on Zalo must not use markdown". A few learning rounds
later the rule was gone. These tests pin the three fixes:
1. A rule the owner gives in chat (`JAVIS_RULE:`) lands in "## Luật chủ dặn", never evicted.
2. `JAVIS_LESSON` keeps rotating through its 15-line window without touching owner rules.
3. The guard refuses any write that drops a line the owner wrote.
(The learn-engine side, op=update only adding rules, is in test_learn_agent_workflow.py.)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import tempfile
from pathlib import Path

import agent_rules
import main

ZALO_RULE = "Nhắn Zalo thì không dùng markdown."


# ---- agent_rules: pure helpers ----

def test_merge_bullets_keeps_text_outside_the_section():
    text = "# Ghi chú tay\n- Khách quen tên Ba.\n\n## Khác\n- giữ nguyên"
    out = agent_rules.merge_bullets(text, agent_rules.OWNER_RULES_HEADER, [ZALO_RULE])
    assert "# Ghi chú tay" in out and "- Khách quen tên Ba." in out and "- giữ nguyên" in out
    assert f"{agent_rules.OWNER_RULES_HEADER}\n- {ZALO_RULE}" in out


def test_merge_bullets_dedupes_and_caps_only_when_asked():
    text = ""
    for i in range(40):
        text = agent_rules.merge_bullets(text, "## X", [f"luật {i}"])
    text = agent_rules.merge_bullets(text, "## X", ["LUẬT 39!"])
    assert sum(1 for l in text.splitlines() if l.startswith("- ")) == 40, "no cap = keep all"
    capped = agent_rules.merge_bullets(text, "## X", ["luật mới"], cap=5)
    assert sum(1 for l in capped.splitlines() if l.startswith("- ")) == 5


def test_extract_rules_strips_marker_from_output():
    rules, clean = agent_rules.extract_rules(f"Dạ em nhớ rồi.\nJAVIS_RULE: {ZALO_RULE}\n")
    assert rules == [ZALO_RULE]
    assert "JAVIS_RULE" not in clean and "Dạ em nhớ rồi." in clean
    assert agent_rules.extract_rules("không có gì") == ([], "không có gì")


def test_guard_catches_a_dropped_owner_line():
    old = f"Bạn là nhân viên.\n\n## Điều cấm\n- {ZALO_RULE}\n\n## Bổ sung (tự học)\n- cũ"
    managed = [agent_rules.LEARNED_ADDITIONS_HEADER]
    rewritten = "Bạn là nhân viên.\n\n## Bổ sung (tự học)\n- mới"
    assert agent_rules.missing_owner_lines(old, rewritten, managed) == [
        "## Điều cấm", f"- {ZALO_RULE}"]
    # Javis-managed lines may change freely; owner lines may move.
    moved = f"## Điều cấm\n- {ZALO_RULE}\n\nBạn là nhân viên.\n\n## Bổ sung (tự học)\n- mới"
    assert agent_rules.missing_owner_lines(old, moved, managed) == []


# ---- main.py: the real agent chat path ----

def _brain(td):
    brain = str(Path(td) / "brain-test")
    Path(brain, "agents").mkdir(parents=True)
    Path(brain, "agents", "cham-khach.md").write_text(
        "---\ntype: agent\nname: Chăm khách\nrole: Trả lời khách Zalo\n---\nThân agent.\n",
        encoding="utf-8")
    return brain


def _mem(brain):
    return Path(brain, "memory", "agents", "cham-khach", "MEMORY.md")


def test_prompt_teaches_the_rule_marker():
    with tempfile.TemporaryDirectory() as td:
        brain = _brain(td)
        _mk, sysprompt, _log, _learn = main._workflow_agent_helpers(brain, tools=None)
        _name, sp, _model, _prov = sysprompt("cham-khach")
        assert "JAVIS_RULE" in sp and agent_rules.OWNER_RULES_HEADER in sp


def test_owner_rule_survives_many_lessons():
    """The incident, end to end: rule given in chat, then 30 lessons, rule still there."""
    with tempfile.TemporaryDirectory() as td:
        brain = _brain(td)
        out = main._ket_luot_agent(brain, "cham-khach",
                                   "Từ giờ nhắn Zalo đừng dùng markdown nhé",
                                   f"Dạ em nhớ rồi.\nJAVIS_RULE: {ZALO_RULE}\n")
        assert "JAVIS_RULE" not in out and "Dạ em nhớ rồi." in out
        for i in range(30):
            main._ket_luot_agent(brain, "cham-khach", f"việc {i}",
                                 f"xong {i}\nJAVIS_LESSON: Bài học số {i}\n")
        text = _mem(brain).read_text(encoding="utf-8")
        assert f"- {ZALO_RULE}" in text, text
        assert "Bài học số 29" in text and "Bài học số 0\n" not in text, "lessons still rotate"
        # And it reaches the agent's prompt on the next run.
        _mk, sysprompt, _log, _learn = main._workflow_agent_helpers(brain, tools=None)
        assert ZALO_RULE in sysprompt("cham-khach")[1]


def test_rule_without_owner_message_becomes_a_lesson():
    """A workflow step has no owner talking to it, so its JAVIS_RULE is not trusted as one."""
    with tempfile.TemporaryDirectory() as td:
        brain = _brain(td)
        _mk, _sp, _log, learn = main._workflow_agent_helpers(brain, tools=None)
        out = learn("cham-khach", f"kết quả bước\nJAVIS_RULE: {ZALO_RULE}\n")
        assert "JAVIS_RULE" not in out
        text = _mem(brain).read_text(encoding="utf-8")
        assert agent_rules.OWNER_RULES_HEADER not in text
        assert main._BAI_HOC_HEADER in text and ZALO_RULE in text


def test_memory_write_refuses_to_drop_owner_lines():
    with tempfile.TemporaryDirectory() as td:
        brain = _brain(td)
        mem = _mem(brain)
        mem.parent.mkdir(parents=True)
        mem.write_text(f"{agent_rules.OWNER_RULES_HEADER}\n- {ZALO_RULE}\n", encoding="utf-8")
        before = mem.read_text(encoding="utf-8")
        # Simulate a future bug in the merge step that loses the owner's section.
        orig = agent_rules.merge_bullets
        try:
            agent_rules.merge_bullets = lambda text, header, items, cap=None: \
                f"{header}\n- " + "\n- ".join(items)
            main._ghi_bai_hoc(brain, "cham-khach", ["bài học mới"])
        finally:
            agent_rules.merge_bullets = orig
        assert mem.read_text(encoding="utf-8") == before, "guard must refuse the write"
        main._ghi_bai_hoc(brain, "cham-khach", ["bài học mới"])
        text = mem.read_text(encoding="utf-8")
        assert f"- {ZALO_RULE}" in text and "- bài học mới" in text


if __name__ == "__main__":
    # CI runs each file as a script (`python tests/python/test_x.py`), not through pytest.
    import sys
    try:
        import pytest
    except ImportError:
        print("skipped: pytest not installed")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
