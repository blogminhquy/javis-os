"""A long first message to agy keeps the user's question even when agy cuts its end (2026-11-27).

    python -m pytest tests/python/test_agy_first_message_guard.py

Owner report: an assistant whose memory file had grown to 52.8 KB, on Antigravity, was asked "can you make images?".
agy cut the end of the first message ("<truncated 21720 bytes>" in the middle of the memory), the question sat at
the very end, so the model answered "your request was cut off, please send it again". The first message now copies
the latest user message to the top once it is long, on every agy path (ACP, stream-json, one-shot).
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json
import sys
from pathlib import Path

import pytest

import agy_acp
import antigravity_cli as agy
import compaction
import warm_pool

FAKE_ACP = str(Path(__file__).with_name("_fake_agy_acp.py"))
FAKE_STREAM = str(Path(__file__).with_name("_fake_agy_stream.py"))
MEMORY = "- Khi khách hỏi giá nước mắm thì báo theo bảng giá mới nhất, không tự giảm giá.\n" * 600
QUESTION = "em có tạo được ảnh không"
BUNDLE = f"[LỊCH SỬ]\nold turns\n{compaction.CURRENT_REQUEST_MARKER}\n{QUESTION}"


def test_short_first_message_is_unchanged():
    assert agy.first_message("RULES", "hi") == "RULES\n\nhi"
    assert agy.first_message("", "hi") == "hi"
    assert agy.first_message(None, BUNDLE) == BUNDLE


def test_long_first_message_starts_with_the_latest_question():
    text = agy.first_message("RULES\n" + MEMORY, BUNDLE)
    head = text[:1500]
    assert QUESTION in head, "the question survives whatever agy cuts from the end"
    assert "old turns" not in head, "only the latest message is copied, not the older history"
    assert "never ask the user to send it again" in head
    assert text.endswith(BUNDLE), "the full context is still there, in the same order"
    assert "—" not in text[:len(text) - len(BUNDLE)] and "–" not in head


def test_a_very_long_question_keeps_its_head_and_tail_on_top():
    long_q = "Viết lại đoạn sau:\n" + ("chữ " * 5000) + "\nrồi tóm tắt trong 3 dòng"
    head = agy.first_message("RULES\n" + MEMORY, long_q).split("[END OF COPY]")[0]
    assert "Viết lại đoạn sau" in head and "rồi tóm tắt trong 3 dòng" in head
    assert len(head) < 7000


def test_the_line_can_be_moved(monkeypatch):
    monkeypatch.setenv("JAVIS_AGY_FIRST_MESSAGE_GUARD", "0")
    assert agy.first_message("RULES", "hi").startswith("[LATEST USER MESSAGE")
    monkeypatch.setenv("JAVIS_AGY_FIRST_MESSAGE_GUARD", "10000000")
    assert agy.first_message("RULES\n" + MEMORY, BUNDLE) == ("RULES\n" + MEMORY).strip() + "\n\n" + BUNDLE


# ---- the real transports, driven against the fake agy ----

@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_AGY_DIR", str(tmp_path / "agy"))
    monkeypatch.setenv("JAVIS_WARM_BUDGET_MB", "4000")
    monkeypatch.setenv("JAVIS_AGY_MCP_HOME", "0")
    monkeypatch.delenv("JAVIS_AGY_RESUME", raising=False)
    monkeypatch.delenv("JAVIS_AGY_ACP", raising=False)
    monkeypatch.delenv("JAVIS_AGY_FIRST_MESSAGE_GUARD", raising=False)
    monkeypatch.setattr(agy, "co_co", lambda *names: any(n in (agy_acp.HELP_MARK, "--input-format") for n in names))
    pool = warm_pool.Pool()
    monkeypatch.setattr(warm_pool, "POOL", pool)
    yield pool
    asyncio.run(pool.close_all())


def make_cli(tmp_path):
    cli = agy.AntigravityCLI(cwd=str(tmp_path), tag="chat:guard:1", instructions="RULES\n" + MEMORY,
                             model="gemini-3.8-flash-high")
    cli.cli_path = sys.executable
    cli.mode = "full"
    cli.effort = None
    cli.stream_turns = True
    cli.warm_key = "chat-guard"
    cli.session_id = None
    cli.resume_prompt = "HDR\nnext"
    cli.acp_args = lambda: [sys.executable, "-u", FAKE_ACP]
    cli.stream_args = lambda cid="": [sys.executable, "-u", FAKE_STREAM, *(["--conversation", cid] if cid else [])]
    return cli


def sent_texts(tmp_path):
    p = tmp_path / "agy" / "received.jsonl"
    return [json.loads(x)["text"] for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_acp_first_message_carries_the_question_on_top(tmp_path):
    async def go():
        return [ev async for ev in make_cli(tmp_path).query(BUNDLE)]
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(go())
    first = sent_texts(tmp_path)[0]
    assert first.startswith("[LATEST USER MESSAGE") and QUESTION in first[:1500]
    assert first.endswith(BUNDLE)


def test_stream_json_first_message_carries_the_question_on_top(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVIS_AGY_ACP", "0")

    async def go():
        return [ev async for ev in make_cli(tmp_path).query(BUNDLE)]
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(go())
    first = sent_texts(tmp_path)[0]
    assert first.startswith("[LATEST USER MESSAGE") and QUESTION in first[:1500]
