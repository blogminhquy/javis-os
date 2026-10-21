"""Real-process regressions for interrupted Antigravity turns, without a real model."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import os
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import antigravity_cli as agy
import claude_cli
import pytest


@pytest.fixture
def processes(tmp_path):
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
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and any(
        t.name.startswith("javis-agy-") and "stop-test" in t.name
        for t in threading.enumerate()
    ):
        time.sleep(0.02)


def driver(tmp_path, *, tag="chat:stop-test", code="import time; time.sleep(30)", timeout=10):
    cli = agy.AntigravityCLI(cwd=str(tmp_path), tag=tag)
    cli.cli_path = sys.executable
    cli.timeout = timeout
    cli._build_args = lambda *a, **kw: [sys.executable, "-u", "-c", code]
    cli._chon_duong = lambda full: "argv"
    return cli


async def until(predicate, timeout=3):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "Process did not reach the expected state"
        await asyncio.sleep(0.01)


async def consume(cli):
    return [event async for event in cli.query("test prompt")]


def test_cancel_stops_process_and_next_turn_answers(tmp_path, processes):
    async def run():
        cli = driver(tmp_path)
        task = asyncio.create_task(consume(cli))
        await until(lambda: bool(processes))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await until(lambda: processes[0].poll() is not None)
        assert processes[0] not in claude_cli._ACTIVE_PROCS
        reply = driver(tmp_path, code='print("next turn ok", flush=True)')
        events = await asyncio.wait_for(consume(reply), 3)
        assert any(e.get("type") == "final" and e.get("content") == "next turn ok" for e in events)

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


def test_silent_process_has_a_real_deadline_without_retry(tmp_path, processes):
    async def run():
        cli = driver(tmp_path, timeout=0.2)
        task = asyncio.create_task(consume(cli))
        done, _ = await asyncio.wait([task], timeout=2)
        if not done:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            pytest.fail("Silent stdout bypassed the turn deadline")
        events = task.result()
        assert any(e.get("type") == "error" for e in events)
        assert len(processes) == 1, "An expired turn must not be retried"
        assert processes[0].poll() is not None

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


def test_stop_registry_only_kills_the_selected_chat(tmp_path, processes):
    async def run():
        first = asyncio.create_task(consume(driver(tmp_path, tag="chat:stop-test:first")))
        await until(lambda: len(processes) == 1)
        second = asyncio.create_task(consume(driver(tmp_path, tag="chat:stop-test:second")))
        await until(lambda: len(processes) == 2 and len([
            p for p, tag in claude_cli._ACTIVE_PROCS.items() if "stop-test" in tag
        ]) == 2)
        assert await asyncio.to_thread(claude_cli.cancel_all, "chat:stop-test:first") == 1
        await asyncio.wait_for(first, 3)
        assert processes[0].poll() is not None
        assert processes[1].poll() is None
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


def test_cancel_before_spawn_returns_does_not_leave_a_process(tmp_path, processes):
    async def run():
        entered, release = threading.Event(), threading.Event()
        tracked_spawn = agy.subprocess.Popen

        def delayed_spawn(*args, **kwargs):
            proc = tracked_spawn(*args, **kwargs)
            entered.set()
            assert release.wait(3)
            return proc

        with patch.object(agy.subprocess, "Popen", side_effect=delayed_spawn):
            task = asyncio.create_task(consume(driver(tmp_path)))
            await until(entered.is_set)
            task.cancel()
            await asyncio.sleep(0.02)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        await until(lambda: processes[0].poll() is not None)
        assert processes[0] not in claude_cli._ACTIVE_PROCS

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


def test_double_cancel_still_cleans_the_worker(tmp_path, processes):
    async def run():
        task = asyncio.create_task(consume(driver(tmp_path)))
        await until(lambda: bool(processes))
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await until(lambda: processes[0].poll() is not None)
        await until(lambda: processes[0] not in claude_cli._ACTIVE_PROCS)

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


def test_closing_the_event_stream_stops_its_process(tmp_path, processes):
    async def run():
        cli = driver(tmp_path, code='print(\'{"type":"tool_call","name":"probe"}\', flush=True); import time; time.sleep(30)')
        events = cli._mot_luot("test", "test", "argv", {})
        assert (await asyncio.wait_for(anext(events), 3))["type"] == "tool_call"
        await events.aclose()
        assert processes[0].poll() is not None
        assert processes[0] not in claude_cli._ACTIVE_PROCS

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


@pytest.mark.skipif(os.name != "nt", reason="Checks real Windows process-tree termination")
def test_cancel_kills_a_real_windows_child(tmp_path, processes):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    marker = tmp_path / "child.pid"
    code = (
        "import subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
        "creationflags=subprocess.CREATE_NO_WINDOW); "
        f"Path({str(marker)!r}).write_text(str(child.pid)); time.sleep(30)"
    )

    async def run():
        task = asyncio.create_task(consume(driver(tmp_path, code=code)))
        await until(marker.exists)
        child_pid = int(marker.read_text())
        handle = kernel.OpenProcess(0x00100000, False, child_pid)
        assert handle, "Could not observe the child process"
        try:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert kernel.WaitForSingleObject(handle, 3000) == 0, "The child survived cancellation"
        finally:
            if kernel.WaitForSingleObject(handle, 0) != 0:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(child_pid)],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            kernel.CloseHandle(handle)

    with patch.object(agy, "co_co", return_value=False):
        asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
