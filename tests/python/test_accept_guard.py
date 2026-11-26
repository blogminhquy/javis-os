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


# ---- 3. A failed accept FUTURE backs off like a failed synchronous accept (any platform, with fakes) ----
# Before: the guard accepted again at once after an accept future failed. A listener that is itself broken fails every
# future straight away, so that was a busy loop on the CPU.
class _FakeFuture:
    def __init__(self):
        self.exc, self.value, self.callbacks = None, None, []

    def result(self):
        if self.exc is not None:
            raise self.exc
        return self.value

    def exception(self):
        return self.exc

    def cancelled(self):
        return False

    def add_done_callback(self, cb):
        self.callbacks.append(cb)

    def finish(self, exc=None, value=None):
        self.exc, self.value = exc, value
        for cb in self.callbacks:
            cb(self)


class _FakeSock:
    def fileno(self):
        return 7


class _FakeConn:
    def close(self):
        pass


class _FakeLoop:
    """Just what `_start_serving` touches: the proactor's accept, call_soon/call_later, transports."""

    def __init__(self):
        self._proactor = self
        self._accept_futures = {}
        self.pending, self.soon, self.later, self.served = [], [], [], []

    def accept(self, sock):
        fut = _FakeFuture()
        self.pending.append(fut)
        return fut

    def call_soon(self, cb):
        self.soon.append(cb)

    def call_later(self, delay, cb):
        self.later.append((delay, cb))

    def is_closed(self):
        return False

    def _make_socket_transport(self, conn, protocol, extra=None, server=None):
        self.served.append(conn)


def _drive_backoff():
    import contextlib
    import io
    fl = _FakeLoop()
    accept_guard._last_log, accept_guard._dropped = 0.0, 0
    err = io.StringIO()
    delays, sync_reaccepts = [], 0
    with contextlib.redirect_stderr(err):
        accept_guard._start_serving(fl, lambda: object(), _FakeSock())
        fl.soon.pop()()                                   # the first accept
        for _ in range(8):                                # every accept future fails at once: a broken listener
            n = len(fl.pending)
            fl.pending[-1].finish(OSError(22, "The specified network name is no longer available"))
            sync_reaccepts += len(fl.pending) - n        # accepted again inside the failure callback = a spin
            if not fl.later:
                break
            delay, cb = fl.later.pop()
            delays.append(delay)
            cb()                                          # the timer fires: accept again
        n = len(fl.pending)
        fl.pending[-1].finish(value=(_FakeConn(), ("127.0.0.1", 5000)))   # a connection is served
        served_then_accepted = bool(fl.served) and len(fl.pending) == n + 1 and not fl.later
        fl.pending[-1].finish(OSError(64, "dropped"))
        reset = fl.later[-1][0] if fl.later else None
    lines = [x for x in err.getvalue().splitlines() if "[accept guard]" in x]
    return delays, sync_reaccepts, served_then_accepted, reset, lines


_delays, _spins, _served, _reset, _lines = _drive_backoff()
check("a failed accept future is not followed by an immediate accept", _spins == 0, _spins)
check("it waits, doubling up to the cap", _delays == [0.05, 0.1, 0.2, 0.4, 0.8, 1.0, 1.0, 1.0], _delays)
check("a served connection accepts the next one at once", _served)
check("the backoff starts again from the minimum after a served connection", _reset == accept_guard.RETRY_MIN_S,
      _reset)
check("the log line is rate limited across those failures", len(_lines) == 1, len(_lines))


print()
print(f"RED {len(_fails)}: " + "; ".join(_fails) if _fails else "GREEN: all passed")
sys.exit(1 if _fails else 0)
