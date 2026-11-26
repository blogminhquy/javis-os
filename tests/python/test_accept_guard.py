"""The server keeps answering after a dropped connection on Windows.

    python tests/run.py accept_guard        (no network, no grok binary needed)

Two halves of one incident (2026-11-25): the event loop froze for a few seconds, a browser gave up on a pending
connection, the accept failed with WinError 64 and asyncio closed the listening port. The process stayed alive but
refused every new connection until it was restarted.

1. `accept_guard`: one failed accept must not close the listener (Windows only, skipped elsewhere).
2. `GrokCLI.query`: `grok --help` must run in a worker thread, not on the event loop.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import threading

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-accepttest-")

import accept_guard      # noqa: E402
import grok_cli          # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. A failed accept leaves the port listening ----
async def _serve_through_failed_accept():
    from asyncio import windows_events
    real_accept = windows_events.IocpProactor.accept
    calls = {"n": 0}

    def flaky_accept(self, listener):
        calls["n"] += 1
        if calls["n"] == 2:     # what a connection dropped mid-accept looks like
            fut = asyncio.get_running_loop().create_future()
            fut.set_exception(OSError(22, "The specified network name is no longer available", None, 64, None))
            return fut
        return real_accept(self, listener)

    async def handle(reader, writer):
        writer.write(b"ok")
        await writer.drain()
        writer.close()

    async def connect(port):
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 2)
            data = await asyncio.wait_for(reader.read(2), 2)
            writer.close()
            return data == b"ok"
        except Exception:  # noqa: BLE001
            return False

    windows_events.IocpProactor.accept = flaky_accept
    try:
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        results = []
        for _ in range(4):
            results.append(await connect(port))
            await asyncio.sleep(0.2)
        still_open = bool(server.sockets) and server.sockets[0].fileno() != -1
        server.close()
        return results, still_open
    finally:
        windows_events.IocpProactor.accept = real_accept


if sys.platform == "win32":
    check("accept_guard installs on Windows", accept_guard.install() is True)
    _results, _still_open = asyncio.run(_serve_through_failed_accept())
    check("every connection is served across one failed accept", _results == [True] * 4, _results)
    check("the listening socket is still open", _still_open)
else:
    check("accept_guard is a no-op off Windows", accept_guard.install() is False)


# ---- 2. Grok's `--help` probe runs off the event loop ----
class _StopBeforeSpawn(Exception):
    pass


async def _help_probe_thread():
    seen = {}
    real_help = grok_cli._help_text

    def record_help():
        seen["thread"] = threading.current_thread()
        return ""

    def stop(*_a, **_k):
        raise _StopBeforeSpawn()

    cli = grok_cli.GrokCLI(cwd=tempfile.gettempdir())
    cli.cli_path = "grok-not-installed"
    cli._build_args = stop
    grok_cli._help_text = record_help
    try:
        async for _ in cli.query("hi"):
            pass
    except _StopBeforeSpawn:
        pass
    finally:
        grok_cli._help_text = real_help
    return seen.get("thread")


_thread = asyncio.run(_help_probe_thread())
check("GrokCLI.query probes `--help` before building the command line", _thread is not None)
check("the `--help` probe runs in a worker thread", _thread is not None and _thread is not threading.main_thread(),
      getattr(_thread, "name", None))


print()
print(f"RED {len(_fails)}: " + "; ".join(_fails) if _fails else "GREEN: all passed")
sys.exit(1 if _fails else 0)
