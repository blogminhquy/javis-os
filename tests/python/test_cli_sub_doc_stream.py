"""The CLI fast path streams Antigravity and Grok text as it comes (owner's measurement, 2026-11-24).

    python tests/python/test_cli_sub_doc_stream.py

`_cli_sub_doc` turns an Antigravity or Grok turn into `_api_stream` events for every chat path
without tools (Telegram, dedicated bots, the shortcut). It dropped the engines' `delta` pieces and
sent the answer only from `final`, so even a one-line reply appeared once the CLI had exited.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio

import main as srv
import pytest


class FakeCli:
    def __init__(self, events):
        self.events = events

    async def query(self, prompt):
        for ev in self.events:
            yield ev


def run(events):
    async def go():
        return [ev async for ev in srv._cli_sub_doc(FakeCli(events), "hi", "m")]
    return asyncio.run(go())


def texts(out):
    return [ev["content"] for ev in out if ev.get("type") == "text"]


def test_deltas_go_out_as_they_come_and_final_is_not_repeated():
    out = run([{"type": "delta", "content": "Xin "}, {"type": "delta", "content": "chào!"},
               {"type": "final", "content": "Xin chào!"}])
    assert texts(out) == ["Xin ", "chào!"]


def test_final_alone_still_answers():
    out = run([{"type": "final", "content": "Một câu."}])
    assert texts(out) == ["Một câu."]


def test_final_adds_only_what_the_pieces_did_not_carry():
    out = run([{"type": "delta", "content": "Trả lời."},
               {"type": "final", "content": "Trả lời.\n\n(cảnh báo)"}])
    assert "".join(texts(out)) == "Trả lời.\n\n(cảnh báo)"


def test_tool_calls_and_errors_still_pass_through():
    out = run([{"type": "tool_call", "name": "run_command", "input": {"CommandLine": "ls"}},
               {"type": "error", "content": "boom"}])
    calls = [ev for ev in out if ev.get("type") == "tool_call"]
    assert calls and calls[0]["detail"] == "ls"
    assert any(ev.get("type") == "error" and ev["content"] == "boom" for ev in out)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
