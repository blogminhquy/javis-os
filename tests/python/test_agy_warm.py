"""Antigravity chat turns on a warm agy that resumes its conversation (agy_warm.py, 2026-11-24).

    python tests/python/test_agy_warm.py

The owner measured on agy 1.5.15 with Javis's 58 KB context: one process per turn took 11.6 s to the first word,
a warm process resuming its conversation 1.6 to 2.7 s. These tests drive the real AntigravityCLI and agy_warm
against _fake_agy_stream.py, which follows the measured protocol (init before any message, one `result` per stdin
line, an unknown `--conversation` silently opens a new one, running-total usage).
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import agy_warm
import antigravity_cli as agy
import claude_cli
import warm_pool

FAKE = str(Path(__file__).with_name("_fake_agy_stream.py"))


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_AGY_DIR", str(tmp_path / "agy"))
    monkeypatch.setenv("JAVIS_WARM_BUDGET_MB", "4000")
    monkeypatch.setenv("JAVIS_AGY_MCP_HOME", "0")
    monkeypatch.delenv("JAVIS_AGY_RESUME", raising=False)
    monkeypatch.setattr(agy, "co_co", lambda *names: "--input-format" in names)
    pool = warm_pool.Pool()
    monkeypatch.setattr(warm_pool, "POOL", pool)
    yield pool
    asyncio.run(pool.close_all())


def received(tmp_path):
    p = tmp_path / "agy" / "received.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def make_cli(tmp_path, *, key="chat-1", session=None, resume="HDR\nnext question", extra=(), tag="chat:warm-test:1"):
    cli = agy.AntigravityCLI(cwd=str(tmp_path), tag=tag, instructions="RULES OF JAVIS")
    cli.cli_path = sys.executable
    cli.mode = "full"
    cli.stream_turns = True
    cli.warm_key = key
    cli.session_id = session
    cli.resume_prompt = resume
    cli.stream_args = lambda cid="": [sys.executable, "-u", FAKE, *extra, *(["--conversation", cid] if cid else [])]
    return cli


async def turn(cli, prompt="BOOTSTRAP transcript + question"):
    return [ev async for ev in cli.query(prompt)]


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_new_thread_sends_the_whole_context_once_then_only_the_new_message(tmp_path, env):
    pool = env

    async def go():
        first = make_cli(tmp_path)
        ev1 = await turn(first)
        session = [e for e in ev1 if e["type"] == "session"][0]
        assert session["warm"] is False and session["cold"] == "new_thread"
        assert [e["content"] for e in ev1 if e["type"] == "final"] == ["answer 1"]
        assert first.resumable and first.session_id == session["session_id"]
        slot = pool.peek("chat-1")
        assert slot is not None and not slot.busy, "the process stays for the next turn"

        second = make_cli(tmp_path, session=first.session_id)
        ev2 = await turn(second)
        session2 = [e for e in ev2 if e["type"] == "session"][0]
        assert session2["warm"] is True, "the next turn runs on the warm process"
        assert [e["content"] for e in ev2 if e["type"] == "final"] == ["answer 2"], "same conversation"
        assert second.session_id == first.session_id and second.resumable

        sent = received(tmp_path)
        assert sent[0]["text"] == "RULES OF JAVIS\n\nBOOTSTRAP transcript + question"
        assert sent[1]["text"] == "HDR\nnext question", "a continued thread gets only the facts and the message"
        assert sent[0]["pid"] == sent[1]["pid"], "one process served both turns"
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
        session = [e for e in ev if e["type"] == "session"][0]
        assert session["warm"] is False and session["session_id"] == first.session_id
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 2"], "the conversation came back"
        sent = received(tmp_path)
        assert sent[-1]["text"] == "HDR\nnext question"
        assert sent[0]["pid"] != sent[-1]["pid"]
    run(go())


def test_a_thread_agy_does_not_know_gets_the_whole_context(tmp_path, env):
    async def go():
        cli = make_cli(tmp_path, session="11111111-2222-3333-4444-555555555555")
        ev = await turn(cli)
        session = [e for e in ev if e["type"] == "session"][0]
        assert session["cold"] == "thread_lost"
        assert cli.session_id == session["session_id"] != "11111111-2222-3333-4444-555555555555"
        assert received(tmp_path)[-1]["text"].startswith("RULES OF JAVIS\n\nBOOTSTRAP"), \
            "agy opened a new conversation, so it must get the instructions and the transcript"
        assert cli.resumable
    run(go())


def test_a_command_left_running_hands_the_process_back(tmp_path, env):
    pool = env

    async def go():
        cli = make_cli(tmp_path)
        ev = await turn(cli, "BOOTSTRAP BGCMD")
        assert any(e["type"] == "tool_call" and e["name"] == "run_command" for e in ev)
        assert pool.peek("chat-1") is None, "tien_trinh_nen must be able to adopt what it left running"
        assert cli.resumable, "the thread is still good to resume"
        assert "chat-1" in pool._recipes, "typing the next message still reopens a process ahead of it"
        procs = [p for p in list(claude_cli._ACTIVE_PROCS) if claude_cli._ACTIVE_PROCS.get(p) == cli.tag]
        assert not procs

        fin = make_cli(tmp_path, key="chat-2")
        await turn(fin, "BOOTSTRAP RUNCMD")
        assert pool.peek("chat-2") is not None, "a command that finished leaves nothing behind"
    run(go())


def test_typing_reopens_an_expired_process_on_the_same_thread(tmp_path, env):
    pool = env

    async def go():
        first = make_cli(tmp_path)
        await turn(first)
        assert pool.reap(now=time.monotonic() + 10 ** 6) == 1, "the idle process expires"
        assert pool.peek("chat-1") is None
        assert pool.prewarm("chat-1"), "the owner started typing: reopen it ahead of the message"
        end = time.monotonic() + 10
        while pool.peek("chat-1") is None and time.monotonic() < end:
            await asyncio.sleep(0.05)
        assert pool.peek("chat-1") is not None
        nxt = make_cli(tmp_path, session=first.session_id)
        ev = await turn(nxt)
        assert [e for e in ev if e["type"] == "session"][0]["warm"] is True
        assert [e["content"] for e in ev if e["type"] == "final"] == ["answer 2"]
        assert received(tmp_path)[-1]["text"] == "HDR\nnext question"
    run(go())


def test_left_running_rules():
    done = "Command exited with code 0.\nOutput: ok"
    assert not agy_warm.left_running("run_command", {"CommandLine": "git status"}, done)
    assert not agy_warm.left_running("run_command", {"CommandLine": "echo hi && dir"}, done)
    assert agy_warm.left_running("run_command", {"CommandLine": "nohup ffmpeg -i a.mp4 b.mp4 &"}, done)
    assert agy_warm.left_running("run_command", {"CommandLine": "Start-Process ffmpeg"}, done)
    assert agy_warm.left_running("run_command", {"CommandLine": "npm run dev"}, "Command is running in background")
    assert not agy_warm.left_running("view_file", {"AbsolutePath": "a.md"}, "")


def test_usage_is_the_turn_s_own_not_the_process_total(tmp_path, env):
    async def go():
        first = make_cli(tmp_path)
        await turn(first)
        second = make_cli(tmp_path, session=first.session_id)
        ev = await turn(second)
        usage = [e for e in ev if e["type"] == "usage"][0]
        assert usage["input_tokens"] == 200 and usage["cached"] == 10000, usage
        assert usage["context_tokens"] == 10200
    run(go())


def test_no_init_falls_back_to_the_one_shot_turn(tmp_path, env):
    async def go():
        cli = make_cli(tmp_path, extra=("NOINIT",))
        cli._build_args = lambda *a, **kw: [sys.executable, "-u", "-c",
                                            'print(\'{"event":"result","result":{"status":"SUCCESS",'
                                            '"response":"one-shot answer"}}\', flush=True)']
        cli._chon_duong = lambda full: "argv"
        ev = await turn(cli)
        assert [e["content"] for e in ev if e["type"] == "final"] == ["one-shot answer"]
        assert not any(e["type"] == "session" for e in ev)
        assert not cli.resumable, "a one-shot thread is never stored for a resume"
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
        assert pool.peek("chat-1") is None
        assert not cli.resumable
    run(go())


def test_switch_off_restores_one_process_per_turn(tmp_path, env, monkeypatch):
    monkeypatch.setenv("JAVIS_AGY_RESUME", "0")

    async def go():
        cli = make_cli(tmp_path)
        cli._build_args = lambda *a, **kw: [sys.executable, "-u", "-c",
                                            'print(\'{"event":"result","result":{"status":"SUCCESS",'
                                            '"response":"classic"}}\', flush=True)']
        cli._chon_duong = lambda full: "argv"
        ev = await turn(cli)
        assert [e["content"] for e in ev if e["type"] == "final"] == ["classic"]
        assert received(tmp_path) == []
    run(go())


def test_the_wire_carries_ascii_only():
    line = agy_warm.message_line("Xin chào, đây là tiếng Việt")
    assert line.endswith("\n") and line.isascii()
    assert json.loads(line)["message"]["content"] == "Xin chào, đây là tiếng Việt"


def test_stream_args_have_no_prompt_flag_and_no_print_timeout(monkeypatch):
    monkeypatch.setattr(agy, "co_co", lambda *names: True)
    cli = agy.AntigravityCLI(cwd=".")
    cli.cli_path, cli.mode, cli.model = "agy", "full", "gemini-x-low"
    args = cli.stream_args("abc")
    assert args[args.index("--input-format") + 1] == "stream-json"
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert args[args.index("--conversation") + 1] == "abc"
    assert "-p" not in args and "--print-timeout" not in args
    assert "--conversation" not in cli.stream_args("")


def test_sessions_keep_and_clear_the_conversation(tmp_path):
    import sessions
    ss = sessions.SessionStore(db_path=tmp_path / "chat.db")
    sid = ss.get_or_create(None, brain="b", engine="antigravity-cli", model="m")
    ss.set_agy_conversation_id(sid, "conv-1")
    assert ss.get_session(sid)["agy_conversation_id"] == "conv-1"
    assert ss.clear_native_threads(sid, keep="antigravity-cli") == []
    assert ss.get_session(sid)["agy_conversation_id"] == "conv-1"
    assert "antigravity-cli" in ss.clear_native_threads(sid, keep="codex"), "another engine ran a turn"
    assert not ss.get_session(sid)["agy_conversation_id"]


def test_main_wires_the_chat_branch():
    src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
    start = src.index('elif prov == "antigravity-cli":')
    branch = src[start:src.index('elif prov == "openai-oauth":', start)]
    assert "acli.stream_turns = True" in branch and "acli.warm_key = conv_sid" in branch
    assert "acli.resume_prompt" in branch and "stable=_a_stable" in branch
    assert "if acli.resumable and acli.session_id:" in branch, "only a thread that answered is stored"
    assert "compaction.nen_mach_thue_bao(" in branch, "a long thread rotates like Grok's"
    assert src.count("warm_pool.POOL.drop_kind(agy_warm.KIND)") >= 2, "sign-out and reconnect drop warm agy"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
