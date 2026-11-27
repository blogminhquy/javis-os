"""Keep the port listening after a failed accept on Windows (2026-11-25).

When a browser drops a connection while it is being accepted, asyncio's proactor loop gets an OSError (WinError 64) and
CLOSES the listening socket: the process lives on but refuses every new connection until it is restarted. Here a failed
accept is logged and the loop accepts again after a short backoff (doubling up to RETRY_MAX_S, reset by the next
connection served); only a socket closed on purpose stops it. No effect off Windows.

The patch replaces a private asyncio method, so its signature must match the running Python's. Python 3.15 added
`context=` and every server died at startup with a TypeError (2026-11-27). Now `install()` compares the two signatures
first: a parameter this file does not know means a newer asyncio, and the guard stands aside (stock asyncio keeps
serving, only without the retry) rather than drop an argument whose meaning it cannot know.
"""
from __future__ import annotations

import inspect
import sys
import time

RETRY_MIN_S = 0.05
RETRY_MAX_S = 1.0
LOG_EVERY_S = 10.0
_last_log = 0.0
_dropped = 0


def _log(exc) -> None:
    global _last_log, _dropped
    _dropped += 1
    now = time.monotonic()
    if _last_log and now - _last_log < LOG_EVERY_S:
        return
    _last_log = now
    try:
        print(f"[accept guard] {time.strftime('%Y-%m-%d %H:%M:%S')} accept failed, still listening "
              f"({type(exc).__name__}: {exc!a}; total {_dropped})", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 - a log line must never stop the accept loop
        pass


def _start_serving(self, protocol_factory, sock, sslcontext=None, server=None, backlog=100,
                   ssl_handshake_timeout=None, ssl_shutdown_timeout=None, context=None):
    # `context` (3.15+) is accepted and unused, exactly as the stock proactor loop does: it only feeds the selector
    # loop's per-connection tasks, and the proactor builds transports straight from the accept callback.
    from asyncio import exceptions
    delay = RETRY_MIN_S

    def retry(exc):
        nonlocal delay
        _log(exc)
        if sock.fileno() == -1 or self.is_closed():
            return
        self.call_later(delay, loop)
        delay = min(delay * 2, RETRY_MAX_S)

    def loop(f=None):
        nonlocal delay
        if sock.fileno() == -1 or self.is_closed():
            if f is not None and not f.cancelled():
                f.exception()
            return
        conn = None
        try:
            if f is not None:
                conn, addr = f.result()
        except exceptions.CancelledError:
            sock.close()
            return
        except OSError as exc:
            # This one connection is gone; accept the next one, after the same backoff as a failed synchronous accept.
            # One dropped connection waits RETRY_MIN_S; a listener that is itself broken fails every future at once,
            # and accepting again right away would spin the CPU (the log line is rate limited in `_log`).
            retry(exc)
            return
        if conn is not None:
            delay = RETRY_MIN_S
            try:
                protocol = protocol_factory()
                if sslcontext is not None:
                    self._make_ssl_transport(conn, protocol, sslcontext, server_side=True,
                                             extra={"peername": addr}, server=server,
                                             ssl_handshake_timeout=ssl_handshake_timeout,
                                             ssl_shutdown_timeout=ssl_shutdown_timeout)
                else:
                    self._make_socket_transport(conn, protocol, extra={"peername": addr}, server=server)
            except Exception as exc:  # noqa: BLE001 - one bad connection must not stop the listener
                conn.close()
                _log(exc)
        try:
            nxt = self._proactor.accept(sock)
        except OSError as exc:
            retry(exc)
            return
        self._accept_futures[sock.fileno()] = nxt
        nxt.add_done_callback(loop)

    self.call_soon(loop)


def unknown_params(stock) -> list:
    """Parameters of the stock `_start_serving` that ours does not take (empty = safe to swap). Unreadable = unsafe."""
    try:
        ours = inspect.signature(_start_serving).parameters
        theirs = inspect.signature(stock).parameters
    except (TypeError, ValueError):
        return ["<signature unreadable>"]
    return [n for n, p in theirs.items()
            if n not in ours and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]


def install() -> bool:
    """Patch the proactor loop. True when applied. Must run before the loop serves; main.py calls it at import.

    Never raises: a guard that cannot be applied must not keep the server from starting."""
    if sys.platform != "win32" or sys.version_info < (3, 11):
        return False
    try:
        from asyncio import proactor_events
        stock = proactor_events.BaseProactorEventLoop._start_serving
        if stock is _start_serving:
            return True
        extra = unknown_params(stock)
        if extra:
            print(f"[accept guard] not applied: this Python ({sys.version.split()[0]}) passes {', '.join(extra)} "
                  "to asyncio's accept loop, which the guard does not know yet; stock asyncio serves instead",
                  file=sys.stderr, flush=True)
            return False
        proactor_events.BaseProactorEventLoop._start_serving = _start_serving
        return True
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"[accept guard] not applied: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return False
