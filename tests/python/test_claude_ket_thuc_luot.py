"""A completed Claude response must not wait forever for the CLI result envelope."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-completion-"))
import claude_agent_sdk as sdk
from claude_sdk_engine import ClaudeSDK


def answer(text="Xong", stop="end_turn", parent=None):
    return sdk.AssistantMessage(content=[sdk.TextBlock(text=text)], model="sonnet",
                                stop_reason=stop, parent_tool_use_id=parent)


def result():
    return sdk.ResultMessage(subtype="success", duration_ms=100, duration_api_ms=90,
                             is_error=False, num_turns=1, session_id="s1", result="Xong",
                             total_cost_usd=0.01, usage={"input_tokens": 7, "output_tokens": 3})


async def run_case(messages, monitored=True):
    class Client:
        def __init__(self, options=None): self.closed = False
        async def connect(self): pass
        async def query(self, prompt): pass
        async def interrupt(self): raise AssertionError("completed answer needs no interrupt request")
        async def disconnect(self): self.closed = True
        def receive_response(self): return messages()

    client = Client()
    with patch.object(sdk, "ClaudeSDKClient", return_value=client), \
         patch.object(ClaudeSDK, "is_available", return_value=True), \
         patch.object(ClaudeSDK, "_options", return_value=SimpleNamespace(include_hook_events=monitored)), \
         patch("claude_token_gate.xep_hang", return_value=""), \
         patch.dict(os.environ, {"JAVIS_CLAUDE_RESULT_TIMEOUT": "0.05",
                                 "JAVIS_CLAUDE_IDLE_TIMEOUT": "0",
                                 "JAVIS_CLAUDE_FIRST_TIMEOUT": "0"}):
        engine = ClaudeSDK(tag="completion-test")
        engine.session_id = "s1"
        events = []
        async def consume():
            async for event in engine.query("test"):
                events.append(event)
        try:
            await asyncio.wait_for(consume(), 0.5)
        except asyncio.TimeoutError:
            raise AssertionError("Claude reported end_turn but Javis kept waiting for result") from None
    assert client.closed, "SDK connection must be closed"
    return events


async def main():
    async def missing_result():
        yield answer()
        await asyncio.Event().wait()
    evs = await run_case(missing_result)
    finals = [e for e in evs if e["type"] == "final"]
    assert len(finals) == 1 and finals[0]["content"] == "Xong"
    assert finals[0]["session_id"] == "s1"
    assert finals[0].get("completion_recovered") is True
    assert not any(e["type"] == "error" for e in evs)
    assert "cost_usd" not in finals[0], "do not fabricate missing billing data"

    async def normal():
        yield answer()
        yield result()
    evs = await run_case(normal)
    final = [e for e in evs if e["type"] == "final"]
    assert len(final) == 1 and final[0]["cost_usd"] == 0.01
    assert final[0]["tokens_in"] == 7 and not final[0].get("completion_recovered")

    # Text alone, a subagent answer, and a tool result cannot finish the parent turn.
    for msg in [answer(stop=None), answer(parent="child-tool"),
                answer(stop="tool_use"), answer(stop="max_tokens")]:
        async def still_working():
            yield msg
            await asyncio.sleep(0.12)
            yield result()
        evs = await run_case(still_working)
        assert [e for e in evs if e["type"] == "final"][0].get("cost_usd") == 0.01

    async def pending_tool():
        yield sdk.AssistantMessage(content=[sdk.ToolUseBlock(id="t1", name="mail", input={})], model="m")
        yield answer()
        await asyncio.sleep(0.12)
        yield sdk.UserMessage(content=[sdk.ToolResultBlock(tool_use_id="t1", content="sent")])
        yield result()
    evs = await run_case(pending_tool)
    assert [e for e in evs if e["type"] == "final"][0].get("cost_usd") == 0.01

    async def continues_after_answer():
        yield answer()
        yield answer("Continuing", stop=None)
        await asyncio.sleep(0.12)
        yield result()
    evs = await run_case(continues_after_answer)
    assert [e for e in evs if e["type"] == "final"][0].get("cost_usd") == 0.01

    async def heartbeat_after_answer():
        yield answer()
        while True:
            await asyncio.sleep(0.01)
            yield sdk.SystemMessage(subtype="status", data={})
    evs = await run_case(heartbeat_after_answer)
    assert [e for e in evs if e["type"] == "final"][0].get("completion_recovered")

    # Hooks and background tasks can outlive an end_turn. Both orderings matter.
    for busy in [sdk.SystemMessage(subtype="hook_started", data={"hook_id": "h1"}),
                 sdk.SystemMessage(subtype="task_started", data={"task_id": "t1"})]:
        for before in [True, False]:
            async def active_work():
                if before: yield busy
                yield answer()
                if not before: yield busy
                await asyncio.sleep(0.12)
                yield result()
            evs = await run_case(active_work)
            assert [e for e in evs if e["type"] == "final"][0].get("cost_usd") == 0.01

    def stream(event, parent=None):
        return sdk.StreamEvent(uuid="u1", session_id="s1", event=event, parent_tool_use_id=parent)

    async def partial_end():
        yield stream({"type": "message_start", "message": {"id": "m1"}})
        yield stream({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Xong"}})
        yield answer(stop=None)
        yield stream({"type": "message_delta", "delta": {"stop_reason": "end_turn"}})
        yield stream({"type": "message_stop"})
        await asyncio.Event().wait()
    evs = await run_case(partial_end)
    assert [e for e in evs if e["type"] == "final"][0].get("completion_recovered")

    async def complete_message_after_stop():
        yield stream({"type": "message_start", "message": {"id": "m1"}})
        yield stream({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Xong"}})
        yield stream({"type": "message_delta", "delta": {"stop_reason": "end_turn"}})
        yield stream({"type": "message_stop"})
        msg = answer(stop=None)
        msg.message_id = "m1"
        yield msg
        await asyncio.Event().wait()
    evs = await run_case(complete_message_after_stop)
    assert [e for e in evs if e["type"] == "final"][0].get("completion_recovered")

    async def killed_task():
        yield sdk.SystemMessage(subtype="task_started", data={"task_id": "t1"})
        yield sdk.SystemMessage(subtype="task_updated", data={"task_id": "t1", "patch": {"status": "killed"}})
        yield answer()
        await asyncio.Event().wait()
    evs = await run_case(killed_task)
    assert [e for e in evs if e["type"] == "final"][0].get("completion_recovered")

    async def stream_continues():
        yield answer()
        yield stream({"type": "message_start", "message": {"id": "m2"}})
        await asyncio.sleep(0.12)
        yield result()
    evs = await run_case(stream_continues)
    assert [e for e in evs if e["type"] == "final"][0].get("cost_usd") == 0.01

    async def old_cli():
        yield answer()
        await asyncio.sleep(0.12)
        yield result()
    evs = await run_case(old_cli, monitored=False)
    assert [e for e in evs if e["type"] == "final"][0].get("cost_usd") == 0.01
    print("OK - Claude completion: missing result, normal billing, tool/subagent safety, continuation, heartbeat")


asyncio.run(main())

# Never pass new flags to an older or differently selected CLI binary.
with patch("claude_cli.tim_binary", return_value="/test/claude"), \
     patch("claude_cli.find_claude_cli", return_value="/test/claude"), \
     patch.object(ClaudeSDK, "_mcp_servers", return_value=(None, False)), \
     patch.dict(os.environ, {"JAVIS_CLAUDE_CLI": "/test/claude"}):
    with patch("claude_cli.co_co", return_value=True):
        opts = ClaudeSDK()._options()
        assert opts.include_hook_events and opts.include_partial_messages
    with patch("claude_cli.co_co", return_value=False):
        opts = ClaudeSDK()._options()
        assert not opts.include_hook_events and not opts.include_partial_messages
    with patch("claude_cli.co_co", return_value=True), \
         patch("claude_cli.find_claude_cli", return_value="/other/claude"):
        assert not ClaudeSDK()._options().include_hook_events
print("OK - completion monitoring respects actual CLI capability")
