"""An Antigravity turn closes on agy's result line, not on its exit (owner's measurement, 2026-11-24).

    python tests/python/test_antigravity_early_finish.py

agy 1.5.15 prints its `result` line and then spends 2-3 s shutting its language server down. The
chat used to wait for that exit with the answer already in hand, so every Antigravity turn ended
2-3 s late and text-to-speech waited with it. These tests run a fake agy (a Python child) with the
real reader and check that the turn ends at the result line, that agy is still allowed to exit on
its own, that one which never exits is stopped after the grace, and that an error result still
waits for the process as before.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import antigravity_cli as agy
import claude_cli
import pytest
import tien_trinh_nen


def _line(ev):
    return json.dumps(ev)


TOOL_ACTIVE = {"event": "step_update", "step_update": {
    "step_index": 2, "state": "ACTIVE", "step_type": "tool", "tool_name": "run_command",
    "tool_info": {"name": "run_command", "parameters": {"CommandLine": "dir"}}}}
TOOL_DONE = {"event": "step_update", "step_update": {
    "step_index": 2, "state": "DONE", "step_type": "tool", "tool_name": "run_command",
    "tool_info": {"name": "run_command", "parameters": {"CommandLine": "dir"}, "output": "a.txt"}}}
TEXT = {"event": "step_update", "step_update": {
    "step_index": 3, "state": "DONE", "step_type": "agent_response", "text_delta": "Done."}}
RESULT_OK = {"event": "result", "result": {"status": "SUCCESS", "response": "Done.",
                                           "usage": {"input_tokens": 10, "output_tokens": 2,
                                                     "cache_read_tokens": 30}}}
RESULT_ERR = {"event": "result", "result": {"status": "ERROR", "error": {"message": "boom"}}}


def _fake(lines, linger):
    """A fake agy: prints the lines, then keeps running for `linger` seconds (its shutdown)."""
    body = "".join(f"print({_line(x)!r}, flush=True)\n" for x in lines)
    return body + f"import time\ntime.sleep({linger})\n"


@pytest.fixture
def processes():
    spawned = []
    original = subprocess.Popen

    def spawn(*args, **kwargs):
        proc = original(*args, **kwargs)
        if args[0][0] == sys.executable:
            spawned.append(proc)
        return proc

    with patch.object(agy.subprocess, "Popen", side_effect=spawn):
        yield spawned
    for proc in spawned:
        if proc.poll() is None:
            claude_cli._kill_tree(proc, grace_s=0.1)
        proc.wait(timeout=5)


def driver(tmp_path, code, tag="chat:early-test:1"):
    cli = agy.AntigravityCLI(cwd=str(tmp_path), tag=tag)
    cli.cli_path = sys.executable
    cli.timeout = 30
    cli._build_args = lambda *a, **kw: [sys.executable, "-u", "-c", code]
    cli._chon_duong = lambda full: "argv"
    return cli


async def until(predicate, timeout=5):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "Process did not reach the expected state"
        await asyncio.sleep(0.02)


async def consume(cli):
    return [event async for event in cli.query("prompt")]


def test_success_result_closes_the_turn_before_agy_exits(tmp_path, processes):
    async def run():
        cli = driver(tmp_path, _fake([TOOL_ACTIVE, TOOL_DONE, TEXT, RESULT_OK], linger=2.5))
        t0 = time.monotonic()
        events = await asyncio.wait_for(consume(cli), 10)
        took = time.monotonic() - t0
        assert any(e.get("type") == "final" and e.get("content") == "Done." for e in events), events
        assert took < 2.0, f"the turn waited for agy's shutdown ({took:.2f}s)"
        assert processes[0].poll() is None, "agy must be left to exit on its own, not killed"
        # The step is marked done with agy's own output, and the cached tokens are counted.
        assert any(e.get("type") == "tool_result" and e.get("content") == "a.txt" for e in events)
        usage = [e for e in events if e.get("type") == "usage"]
        assert usage and usage[0]["cached"] == 30
        await until(lambda: processes[0].poll() is not None, timeout=6)
        assert processes[0].returncode == 0, "agy exited on its own after its shutdown"
        await until(lambda: processes[0] not in claude_cli._ACTIVE_PROCS)

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


def test_agy_that_never_exits_is_stopped_after_the_grace(tmp_path, processes):
    async def run():
        cli = driver(tmp_path, _fake([TEXT, RESULT_OK], linger=60))
        events = await asyncio.wait_for(consume(cli), 10)
        assert any(e.get("type") == "final" for e in events)
        await until(lambda: processes[0].poll() is not None, timeout=8)
        await until(lambda: processes[0] not in claude_cli._ACTIVE_PROCS)

    with patch.object(agy, "co_co", return_value=False), patch.object(agy, "EXIT_GRACE_S", 0.5):
        asyncio.run(run())


def test_the_grace_stops_agy_but_not_the_work_it_started(tmp_path, processes):
    """A render agy started in the background belongs to the owner: only agy is stopped."""
    pid_file, marker = tmp_path / "child.pid", tmp_path / "child.alive"
    child = (f"import time; time.sleep(1.5); open({str(marker)!r}, 'w').write('alive'); time.sleep(30)")
    code = ("import subprocess, sys\n"
            f"c = subprocess.Popen([sys.executable, '-c', {child!r}], stdin=subprocess.DEVNULL, "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            f"open({str(pid_file)!r}, 'w').write(str(c.pid))\n") + _fake([TEXT, RESULT_OK], linger=60)

    async def run():
        cli = driver(tmp_path, code)
        events = await asyncio.wait_for(consume(cli), 10)
        assert any(e.get("type") == "final" for e in events)
        await until(lambda: processes[0].poll() is not None, timeout=8)
        await until(marker.exists, timeout=8)

    try:
        with patch.object(agy, "co_co", return_value=False), patch.object(agy, "EXIT_GRACE_S", 0.3):
            asyncio.run(run())
    finally:
        if pid_file.exists():
            pid = int(pid_file.read_text())
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                import os
                import signal
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


def test_error_result_still_waits_for_the_process(tmp_path, processes):
    async def run():
        cli = driver(tmp_path, _fake([RESULT_ERR], linger=0.8))
        events = await asyncio.wait_for(consume(cli), 10)
        assert processes[0].poll() is not None, "an error turn reads stderr and the exit code first"
        assert any(e.get("type") == "error" and "boom" in str(e.get("content")) for e in events), events

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


def test_is_success_result_shapes():
    assert agy.is_success_result(RESULT_OK)
    assert agy.is_success_result({"type": "result", "status": "success"})
    assert agy.is_success_result({"event": "result", "result": {}})
    assert not agy.is_success_result(RESULT_ERR)
    assert not agy.is_success_result(TEXT)
    assert not agy.is_success_result({"_exit": 0})
    assert not agy.is_success_result(None)


def test_adoption_waits_for_an_engine_still_exiting(monkeypatch):
    monkeypatch.setattr(tien_trinh_nen, "POSIX", True)
    gone = threading.Event()
    tien_trinh_nen.note_engine_exiting("chat:wait-test:1", gone)
    threading.Timer(0.3, gone.set).start()
    t0 = time.monotonic()
    tien_trinh_nen.wait_engine_exit("chat:wait-test:1", timeout=5)
    assert gone.is_set() and 0.2 < time.monotonic() - t0 < 3
    # Nothing noted: no wait at all; and the wait is capped.
    t0 = time.monotonic()
    tien_trinh_nen.wait_engine_exit("chat:wait-test:none", timeout=5)
    assert time.monotonic() - t0 < 0.1
    tien_trinh_nen.note_engine_exiting("chat:wait-test:2", threading.Event())
    t0 = time.monotonic()
    tien_trinh_nen.wait_engine_exit("chat:wait-test:2", timeout=0.3)
    assert time.monotonic() - t0 < 1.5
    # A turn that ends in error drops the note with the rest of its bookkeeping.
    tien_trinh_nen.note_engine_exiting("chat:wait-test:3", threading.Event())
    tien_trinh_nen.bo_tag("chat:wait-test:3")
    t0 = time.monotonic()
    tien_trinh_nen.wait_engine_exit("chat:wait-test:3", timeout=5)
    assert time.monotonic() - t0 < 0.1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
