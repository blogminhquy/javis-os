"""Antigravity chat turns over `agy acp`, which streams the model's thinking (agy_acp.py, 2026-11-24).

    python tests/python/test_agy_acp.py

Measured on agy 1.5.15: the stream-json mode sends nothing while the model thinks (12 to 18 s on Gemini Flash High
before the first word), while `agy acp` sends a summary of the thinking about every 3 s. These tests drive the real
AntigravityCLI and agy_acp against _fake_agy_acp.py, which follows the measured protocol, and against
_fake_agy_stream.py for the fallback.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

import agy_acp
import antigravity_cli as agy
import claude_cli
import warm_pool

FAKE_ACP = str(Path(__file__).with_name("_fake_agy_acp.py"))
FAKE_STREAM = str(Path(__file__).with_name("_fake_agy_stream.py"))


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_AGY_DIR", str(tmp_path / "agy"))
    monkeypatch.setenv("JAVIS_WARM_BUDGET_MB", "4000")
    monkeypatch.setenv("JAVIS_AGY_MCP_HOME", "0")
    monkeypatch.delenv("JAVIS_AGY_RESUME", raising=False)
    monkeypatch.delenv("JAVIS_AGY_ACP", raising=False)
    monkeypatch.setattr(agy, "co_co", lambda *names: any(n in (agy_acp.HELP_MARK, "--input-format") for n in names))
    pool = warm_pool.Pool()
    monkeypatch.setattr(warm_pool, "POOL", pool)
    yield pool
    asyncio.run(pool.close_all())


def received(tmp_path):
    p = tmp_path / "agy" / "received.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def make_cli(tmp_path, *, key="chat-1", session=None, resume="HDR\nnext question", extra=(), mode="full",
             model="gemini-3.8-flash-high", effort=None, tag="chat:acp-test:1"):
    cli = agy.AntigravityCLI(cwd=str(tmp_path), tag=tag, instructions="RULES OF JAVIS", model=model)
    cli.cli_path = sys.executable
    cli.mode = mode
    cli.effort = effort
    cli.stream_turns = True
    cli.warm_key = key
    cli.session_id = session
    cli.resume_prompt = resume
    cli.acp_args = lambda: [sys.executable, "-u", FAKE_ACP, *extra]
    cli.stream_args = lambda cid="": [sys.executable, "-u", FAKE_STREAM, *(["--conversation", cid] if cid else [])]
    return cli


async def turn(cli, prompt="BOOTSTRAP transcript + question"):
    return [ev async for ev in cli.query(prompt)]


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def kinds(ev):
    return [e["type"] for e in ev]


def test_thinking_streams_before_the_answer_and_the_thread_continues_warm(tmp_path, env):
    pool = env

    async def go():
        first = make_cli(tmp_path)
        ev1 = await turn(first)
        session = ev1[0]
        assert session["type"] == "session" and session["warm"] is False and session["cold"] == "new_thread"
        k = kinds(ev1)
        assert k.index("thinking") < k.index("delta"), "the thinking shows while the answer is not written yet"
        thought = [e for e in ev1 if e["type"] == "thinking"][0]["content"]
        assert thought.startswith("**Weighing the question**")
        assert "".join(e["content"] for e in ev1 if e["type"] == "delta") == "answer 1"
        assert [e["content"] for e in ev1 if e["type"] == "final"] == ["answer 1"]
        assert first.resumable and first.session_id == session["session_id"]
        assert pool.peek("chat-1") is not None and not pool.peek("chat-1").busy

        second = make_cli(tmp_path, session=first.session_id)
        ev2 = await turn(second)
        assert ev2[0]["warm"] is True, "the next turn runs on the warm process"
        assert [e["content"] for e in ev2 if e["type"] == "final"] == ["answer 2"]
        sent = received(tmp_path)
        assert sent[0]["text"] == "RULES OF JAVIS\n\nBOOTSTRAP transcript + question"
        assert sent[1]["text"] == "HDR\nnext question", "a continued thread gets only the facts and the message"
        assert sent[0]["pid"] == sent[1]["pid"], "one process served both turns"
        assert sent[0]["model"] == "gemini-3.8-flash-high", "the model is set on the session"
    run(go())


def test_resume_on_a_new_process_after_the_warm_one_is_gone(tmp_path, env):
    pool = env

    async def go():
        first = make_cli(tmp_path)
        await turn(first)
        pool.forget("chat-1")
        await asyncio.sleep(0.5)
        again = make_cli(tmp_path, session=first.session_id)
        ev = await turn(again)
        assert ev[0]["warm"] is False and ev[0]["session_id"] == first.session_id
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 2"], "the conversation came back"
        sent = received(tmp_path)
        assert sent[-1]["text"] == "HDR\nnext question"
        assert sent[0]["pid"] != sent[-1]["pid"]
    run(go())


def test_a_thread_agy_does_not_know_gets_the_whole_context(tmp_path, env):
    async def go():
        cli = make_cli(tmp_path, session="11111111-2222-3333-4444-555555555555")
        ev = await turn(cli)
        assert ev[0]["cold"] == "thread_lost"
        assert cli.session_id == ev[0]["session_id"] != "11111111-2222-3333-4444-555555555555"
        assert received(tmp_path)[-1]["text"].startswith("RULES OF JAVIS\n\nBOOTSTRAP"), \
            "agy opened a new conversation, so it must get the instructions and the transcript"
        assert cli.resumable
    run(go())


def test_a_thread_opened_on_stream_json_resumes_on_acp(tmp_path, env, monkeypatch):
    async def go():
        monkeypatch.setenv("JAVIS_AGY_ACP", "0")
        old = make_cli(tmp_path)
        ev = await turn(old)
        assert not any(e["type"] == "thinking" for e in ev), "the stream-json path served this one"
        monkeypatch.setenv("JAVIS_AGY_ACP", "1")
        new = make_cli(tmp_path, session=old.session_id)
        ev = await turn(new)
        assert ev[0]["session_id"] == old.session_id and ev[0].get("cold") != "thread_lost"
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 2"]
        assert received(tmp_path)[-1]["text"] == "HDR\nnext question"
        assert any(e["type"] == "thinking" for e in ev)
    run(go())


def test_a_model_acp_does_not_take_falls_back_to_stream_json(tmp_path, env):
    async def go():
        cli = make_cli(tmp_path, model="no-such-model")
        ev = await turn(cli)
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 1"]
        assert not any(e["type"] == "thinking" for e in ev)
        assert "model" not in received(tmp_path)[-1], "the stream-json fake served the turn"
        assert cli.resumable
    run(go())


def test_an_agy_without_acp_falls_back_to_stream_json(tmp_path, env):
    async def go():
        cli = make_cli(tmp_path, extra=("NOACP",))
        ev = await turn(cli)
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 1"]
        assert ev[0]["type"] == "session"
    run(go())


def test_tool_steps_carry_their_output_and_hub_calls_their_real_name(tmp_path, env):
    pool = env

    async def go():
        cli = make_cli(tmp_path)
        ev = await turn(cli, "BOOTSTRAP RUNCMD MCPCALL")
        calls = [e for e in ev if e["type"] == "tool_call"]
        assert [c["name"] for c in calls] == ["run_command", "javis_connections"]
        assert calls[0]["input"]["CommandLine"] == "git status"
        assert calls[1]["input"] == {"op": "list", "toolSummary": "List connections"}
        results = [e for e in ev if e["type"] == "tool_result"]
        assert [r["id"] for r in results] == ["call_1", "call_2"]
        assert results[0]["content"].startswith("Command exited with code 0")
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 1"]
        assert pool.peek("chat-1") is not None, "a command that finished leaves nothing behind"
    run(go())


def test_a_command_left_running_hands_the_process_back(tmp_path, env):
    pool = env

    async def go():
        cli = make_cli(tmp_path)
        await turn(cli, "BOOTSTRAP BGCMD")
        assert pool.peek("chat-1") is None, "tien_trinh_nen must be able to adopt what it left running"
        assert cli.resumable and "chat-1" in pool._recipes
        assert not [p for p in list(claude_cli._ACTIVE_PROCS) if claude_cli._ACTIVE_PROCS.get(p) == cli.tag]
    run(go())


def test_permission_requests_follow_the_mode(tmp_path, env):
    async def go():
        await turn(make_cli(tmp_path, key="c-full"), "BOOTSTRAP ASKPERM")
        assert (tmp_path / "agy" / "permission.txt").read_text() == "a1"
        await turn(make_cli(tmp_path, key="c-sug", mode="suggest"), "BOOTSTRAP ASKPERM")
        assert (tmp_path / "agy" / "permission.txt").read_text() == "r1", "suggest never approves a tool"
        await turn(make_cli(tmp_path, key="c-other"), "BOOTSTRAP UNKNOWNREQ")
        r = json.loads((tmp_path / "agy" / "unknown_req.txt").read_text())
        assert r["error"]["code"] == -32601, "agy never waits on a request Javis does not serve"
    run(go())


def test_effort_goes_on_the_session_only_for_a_model_without_one(tmp_path, env):
    async def go():
        await turn(make_cli(tmp_path, key="e1", model="claude-sonnet-4-6", effort="low"))
        assert received(tmp_path)[-1]["effort"] == "low"
        await turn(make_cli(tmp_path, key="e2", model="gemini-3.8-flash-high", effort="low"))
        assert received(tmp_path)[-1]["effort"] == "", "the model's name already carries its effort"
        ev = await turn(make_cli(tmp_path, key="e3", model="claude-sonnet-4-6", effort="max"))
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 1"], "a level it lacks is skipped"
        assert received(tmp_path)[-1]["effort"] == ""
    run(go())


def test_a_busy_provider_before_any_work_retries_one_shot(tmp_path, env):
    async def go():
        cli = make_cli(tmp_path)
        cli._build_args = lambda *a, **kw: [sys.executable, "-u", "-c",
                                            'print(\'{"event":"result","result":{"status":"SUCCESS",'
                                            '"response":"after retry"}}\', flush=True)']
        cli._chon_duong = lambda full: "argv"
        ev = await turn(cli, "BOOTSTRAP FAIL503")
        assert [e["content"] for e in ev if e["type"] == "final"] == ["after retry"]
        assert not any(e["type"] == "error" for e in ev), "the 503 was handled, not shown"
        assert not cli.resumable
    run(go())


def test_a_refusal_is_an_error_and_the_thread_is_not_kept(tmp_path, env):
    pool = env

    async def go():
        cli = make_cli(tmp_path)
        ev = await turn(cli, "BOOTSTRAP REFUSE")
        assert any(e["type"] == "error" for e in ev)
        assert not cli.resumable and pool.peek("chat-1") is None
    run(go())


def test_stop_mid_turn_ends_the_process_and_keeps_nothing(tmp_path, env):
    pool = env

    async def go():
        cli = make_cli(tmp_path)
        task = asyncio.create_task(turn(cli, "BOOTSTRAP SLOW"))
        end = time.monotonic() + 10
        while not received(tmp_path) and time.monotonic() < end:
            await asyncio.sleep(0.05)
        procs = [p for p in list(claude_cli._ACTIVE_PROCS) if claude_cli._ACTIVE_PROCS.get(p) == cli.tag]
        assert procs
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        end = time.monotonic() + 8
        while procs[0].poll() is None and time.monotonic() < end:
            await asyncio.sleep(0.05)
        assert procs[0].poll() is not None
        assert pool.peek("chat-1") is None and not cli.resumable
    run(go())


def test_typing_reopens_an_expired_process_on_the_same_thread(tmp_path, env):
    pool = env

    async def go():
        first = make_cli(tmp_path)
        await turn(first)
        assert pool.reap(now=time.monotonic() + 10 ** 6) == 1
        assert pool.prewarm("chat-1"), "the owner started typing: reopen it ahead of the message"
        end = time.monotonic() + 10
        while pool.peek("chat-1") is None and time.monotonic() < end:
            await asyncio.sleep(0.05)
        assert pool.peek("chat-1") is not None
        nxt = make_cli(tmp_path, session=first.session_id)
        ev = await turn(nxt)
        assert ev[0]["warm"] is True
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 2"]
    run(go())


def test_a_stream_json_slot_is_not_taken_for_an_acp_turn(tmp_path, env, monkeypatch):
    pool = env

    async def go():
        monkeypatch.setenv("JAVIS_AGY_ACP", "0")
        old = make_cli(tmp_path)
        await turn(old)
        assert pool.peek("chat-1") is not None
        monkeypatch.setenv("JAVIS_AGY_ACP", "1")
        new = make_cli(tmp_path, session=old.session_id)
        ev = await turn(new)
        assert ev[0]["warm"] is False and ev[0]["cold"] == "config_changed"
    run(go())


def servers_sent(tmp_path):
    p = tmp_path / "agy" / "servers.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


HUB = {"serverUrl": "http://127.0.0.1:7777/hub/mcp", "url": "http://127.0.0.1:7777/hub/mcp",
       "headers": {"Authorization": "Bearer t0k", "X-Javis-Vault": "/brains/a"}, "disabled": False}


def test_the_session_gets_this_turn_s_hub_and_the_workspace_servers(tmp_path, env):
    """agy acp reads the HOME mcp_config but not <cwd>/.agents/mcp_config.json (measured on 1.5.15), so Javis passes
    the workspace entries and this turn's hub entry on the session, on a new thread and on a resume alike."""
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "mcp_config.json").write_text(json.dumps({"mcpServers": {
        "javis": {"serverUrl": "http://stale/hub", "headers": {"X-Javis-Vault": "/brains/other"}},
        "notes": {"command": "node", "args": ["notes.js"], "env": {"TOKEN": "x"}},
        "off": {"serverUrl": "http://off", "disabled": True}}}), encoding="utf-8")

    async def go():
        first = make_cli(tmp_path)
        first.hub_entry = HUB
        await turn(first)
        sent = servers_sent(tmp_path)[-1]
        assert sent["method"] == "session/new"
        by_name = {s["name"]: s for s in sent["mcpServers"]}
        assert set(by_name) == {"javis", "notes"}, "a disabled entry stays out"
        assert by_name["javis"] == {"type": "http", "name": "javis", "url": "http://127.0.0.1:7777/hub/mcp",
                                    "headers": [{"name": "Authorization", "value": "Bearer t0k"},
                                                {"name": "X-Javis-Vault", "value": "/brains/a"}]}, \
            "this turn's hub wins over the workspace file"
        assert by_name["notes"] == {"name": "notes", "command": "node", "args": ["notes.js"],
                                    "env": [{"name": "TOKEN", "value": "x"}]}
        env.forget("chat-1")
        await asyncio.sleep(0.5)
        again = make_cli(tmp_path, session=first.session_id)
        again.hub_entry = HUB
        await turn(again)
        sent = servers_sent(tmp_path)[-1]
        assert sent["method"] == "session/resume" and {s["name"] for s in sent["mcpServers"]} == {"javis", "notes"}
    run(go())


def test_another_brain_s_hub_opens_another_process(tmp_path, env):
    async def go():
        first = make_cli(tmp_path)
        first.hub_entry = HUB
        await turn(first)
        other = make_cli(tmp_path, session=first.session_id)
        other.hub_entry = dict(HUB, headers={"Authorization": "Bearer t0k", "X-Javis-Vault": "/brains/b"})
        ev = await turn(other)
        assert ev[0]["warm"] is False and ev[0]["cold"] == "config_changed", \
            "a process opened with another brain's hub must not serve this turn"
    run(go())


def test_a_hub_tool_named_the_acp_way_shows_its_real_name(tmp_path, env):
    async def go():
        cli = make_cli(tmp_path)
        cli.hub_entry = HUB
        ev = await turn(cli, "BOOTSTRAP MCPACP")
        call = [e for e in ev if e["type"] == "tool_call"][0]
        assert call["name"] == "javis_connections"
        assert call["input"] == {"op": "list", "toolSummary": "List connections"}
        assert [e for e in ev if e["type"] == "tool_result"][0]["id"] == "call_4"
    run(go())


# ---- pure parts ----

def test_unwrap_mcp_name():
    servers = agy_acp.server_names(type("C", (), {})(), [{"name": "javis"}, {"name": "probe_ws"}])
    assert agy_acp.unwrap_mcp_name("mcp_javis_javis_run_tool", {"name": "pos_order", "args": {"id": 1},
                                                                "toolSummary": "Read order"}, servers) == \
        ("pos_order", {"id": 1, "toolSummary": "Read order"})
    assert agy_acp.unwrap_mcp_name("mcp_javis_javis_task", {"op": "list"}, servers) == ("javis_task", {"op": "list"})
    assert agy_acp.unwrap_mcp_name("mcp_probe_ws_probe_secret_word", {}, servers) == ("probe_secret_word", {}), \
        "a server name with an underscore is matched whole"
    assert agy_acp.unwrap_mcp_name("run_command", {"CommandLine": "ls"}, servers) == \
        ("run_command", {"CommandLine": "ls"})
    assert agy_acp.unwrap_mcp_name("mcp_unknown_tool", {}, servers) == ("mcp_unknown_tool", {})


def test_acp_server_shapes():
    assert agy_acp.acp_server("a", {"url": "http://x", "headers": {"K": "V"}}) == \
        {"type": "http", "name": "a", "url": "http://x", "headers": [{"name": "K", "value": "V"}]}
    assert agy_acp.acp_server("b", {"command": "npx", "args": ["-y", 3]}) == \
        {"name": "b", "command": "npx", "args": ["-y", "3"], "env": []}
    assert agy_acp.acp_server("c", {"serverUrl": "http://x", "disabled": True}) is None
    assert agy_acp.acp_server("d", {"nothing": 1}) is None
    assert agy_acp.acp_server("e", "junk") is None

def test_translate_maps_every_update():
    st = agy_acp.new_state()
    assert agy_acp.translate({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Hi"}},
                             st) == [{"type": "_text", "content": "Hi"}]
    assert agy_acp.translate({"sessionUpdate": "agent_thought_chunk",
                              "content": {"type": "text", "text": "  Planning.\n\n"}}, st) == \
        [{"type": "thinking", "content": "Planning."}]
    assert agy_acp.translate({"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": " "}},
                             st) == []
    first = agy_acp.translate({"sessionUpdate": "tool_call", "toolCallId": "t1", "name": "read_file",
                               "rawInput": {"Path": "a.md"}, "status": "in_progress"}, st)
    assert first == [{"type": "tool_call", "name": "read_file", "id": "t1", "input": {"Path": "a.md"}}]
    done = agy_acp.translate({"sessionUpdate": "tool_call_update", "toolCallId": "t1", "status": "failed",
                              "content": [{"type": "content", "content": {"type": "text", "text": "no file"}}]}, st)
    assert done == [{"type": "tool_result", "id": "t1", "status": "error", "content": "no file"}]
    assert agy_acp.translate({"sessionUpdate": "tool_call_update", "toolCallId": "t1", "status": "failed"}, st) == []
    # an update for a step never announced still shows the step first
    late = agy_acp.translate({"sessionUpdate": "tool_call_update", "toolCallId": "t2", "name": "write_file",
                              "status": "completed", "rawOutput": {}}, st)
    assert [e["type"] for e in late] == ["tool_call", "tool_result"]
    agy_acp.translate({"sessionUpdate": "usage_update", "used": 4321, "size": 1}, st)
    assert st["context"] == 4321
    assert agy_acp.translate({"sessionUpdate": "session_info_update", "title": "x"}, st) == []


def test_usage_is_the_turn_s_own_with_the_thread_size():
    u = agy_acp.usage_event({"inputTokens": 200, "outputTokens": 2, "cachedReadTokens": 10000,
                             "totalTokens": 10202}, 10201)
    assert u == {"type": "usage", "context_tokens": 10201, "input_tokens": 200, "output_tokens": 2,
                 "total_tokens": 10202, "cached": 10000}
    assert agy_acp.usage_event({"inputTokens": 5, "cachedReadTokens": 7}, 0)["context_tokens"] == 12
    assert agy_acp.usage_event({}, 9) is None


def test_permission_answers_fail_closed():
    req = {"jsonrpc": "2.0", "id": 9, "method": "session/request_permission",
           "params": {"options": [{"optionId": "y", "kind": "allow_always"}, {"optionId": "n", "kind": "reject_once"}]}}
    pick = lambda mode: json.loads(agy_acp.answer_request(req, mode))["result"]["outcome"]
    assert pick("full") == {"outcome": "selected", "optionId": "y"}
    assert pick("auto") == {"outcome": "selected", "optionId": "y"}
    assert pick("suggest") == {"outcome": "selected", "optionId": "n"}
    assert pick("weird") == {"outcome": "selected", "optionId": "n"}
    only_allow = dict(req, params={"options": [{"optionId": "y", "kind": "allow_once"}]})
    assert json.loads(agy_acp.answer_request(only_allow, "suggest"))["result"]["outcome"] == {"outcome": "cancelled"}
    other = json.loads(agy_acp.answer_request({"id": 3, "method": "terminal/create"}, "full"))
    assert other["error"]["code"] == -32601


def test_effort_rule():
    cfg = [{"id": "thought_level", "options": [{"value": "low"}, {"value": "high"}]}]
    assert agy_acp.effort_for("claude-sonnet-4-6", "low", cfg) == "low"
    assert agy_acp.effort_for("claude-sonnet-4-6", "medium", cfg) == ""
    assert agy_acp.effort_for("gemini-3.8-flash-high", "low", cfg) == ""
    assert agy_acp.effort_for("claude-sonnet-4-6", None, cfg) == ""
    assert agy_acp.effort_for("claude-sonnet-4-6", "high") == "high", "no option list: try it, agy may refuse"


def test_the_wire_carries_ascii_only():
    line = agy_acp.request_line(4, "session/prompt", {"prompt": [{"type": "text", "text": "Xin chào"}]})
    assert line.endswith("\n") and line.isascii()
    assert json.loads(line)["params"]["prompt"][0]["text"] == "Xin chào"


def test_acp_args_carry_the_permission_flags_and_no_model(monkeypatch):
    monkeypatch.setattr(agy, "co_co", lambda *names: True)
    cli = agy.AntigravityCLI(cwd=".", model="gemini-3.8-flash-low")
    cli.cli_path, cli.mode = "agy", "full"
    cli.include_dirs = ["/data/x"]
    assert cli.acp_args() == ["agy", "acp", "--dangerously-skip-permissions", "--add-dir", "/data/x"]
    cli.mode = "suggest"
    assert cli.acp_args()[:3] == ["agy", "acp", "--sandbox"]
    assert "--model" not in cli.acp_args()


def test_main_relays_the_thinking():
    src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
    start = src.index('elif prov == "antigravity-cli":')
    branch = src[start:src.index('elif prov == "openai-oauth":', start)]
    assert 'elif et == "thinking":' in branch
    assert '{"type": "thinking", "content": ev["content"]}' in branch


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
