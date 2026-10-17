"""Event loop watchdog: catch the code that freezes the server (0.194.0).

Why it exists. The dashboard talks to the server over one WebSocket. When something runs heavy synchronous work on the
event loop (reading a big file, a slow sqlite query, a subprocess wait without a thread), the loop cannot answer the
page's ping, cannot accept a new socket, and every page on every device shows "Mất kết nối tới máy chủ" until the work
ends. Nothing in the logs said WHICH code did it, so each report was a guess.

How. A tiny asyncio task stamps the time every TICK_S. A daemon thread checks the stamp; when the loop has not ticked
for BLOCK_S it captures the loop thread's Python stack (sys._current_frames) once per incident, prints it to stderr and
keeps the last INCIDENTS incidents (with the final duration once the loop is back) for GET /health/loop.

It only reads frames; it never interrupts the loop.

Unclean restarts. The other cause of a long "Mất kết nối" is the server process dying (out of memory, a crash) and
coming back. `start(state_dir)` keeps a heartbeat file; a boot that finds the previous run's heartbeat without the
clean-stop mark records an unexpected restart (when it was last alive), shown in GET /health/loop.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import traceback
import json
from collections import deque
from pathlib import Path
from typing import Optional

TICK_S = 0.25
try:
    BLOCK_S = max(0.2, float(os.environ.get("JAVIS_LOOP_BLOCK_S", "2")))
except ValueError:
    BLOCK_S = 2.0
INCIDENTS = 20
STACK_LINES = 14
BEAT_S = 10.0
RESTARTS = 10

_files = {"beat": None, "restarts": None}

_state = {"tick": 0.0, "loop_thread": None, "started": False, "current": None}
_incidents: deque = deque(maxlen=INCIDENTS)
_lock = threading.Lock()


async def _ticker() -> None:
    while True:
        _state["tick"] = time.monotonic()
        await asyncio.sleep(TICK_S)


def _stack_of(thread_id: Optional[int]) -> list:
    frame = sys._current_frames().get(thread_id) if thread_id else None
    if frame is None:
        return []
    lines = traceback.format_stack(frame)
    # Keep the innermost frames: that is where the loop is stuck.
    return [ln.rstrip() for ln in lines[-STACK_LINES:]]


def _watch() -> None:
    while True:
        time.sleep(min(TICK_S * 2, BLOCK_S / 4))
        last = _state["tick"]
        if not last:
            continue
        lag = time.monotonic() - last
        with _lock:
            cur = _state["current"]
            if lag >= BLOCK_S and cur is None:
                inc = {"at": time.time() - lag, "seconds": round(lag, 2), "ended": False,
                       "stack": _stack_of(_state["loop_thread"])}
                _state["current"] = inc
                _incidents.append(inc)
                print(f"[loop] the event loop has been blocked {lag:.1f}s, here:\n" + "\n".join(inc["stack"]),
                      file=sys.stderr, flush=True)
            elif cur is not None:
                if lag >= BLOCK_S:
                    cur["seconds"] = round(lag, 2)
                else:
                    cur["ended"] = True
                    _state["current"] = None
                    print(f"[loop] the event loop is free again after ~{cur['seconds']:.1f}s", file=sys.stderr,
                          flush=True)


def _read_json(path: Optional[Path], default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else default
    except Exception:  # noqa: BLE001 - a torn file only loses the diagnostics
        return default


def _write_json(path: Optional[Path], data) -> None:
    if not path:
        return
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def _beat(clean: bool = False) -> None:
    _write_json(_files["beat"], {"pid": os.getpid(), "alive": time.time(), "clean": clean})


async def _beater() -> None:
    while True:
        await asyncio.to_thread(_beat)
        await asyncio.sleep(BEAT_S)


def _note_restart(state_dir: Optional[str]) -> None:
    if not state_dir:
        return
    d = Path(state_dir)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    _files["beat"], _files["restarts"] = d / "loop_beat.json", d / "loop_restarts.json"
    prev = _read_json(_files["beat"], None)
    if isinstance(prev, dict) and not prev.get("clean") and prev.get("pid") != os.getpid():
        items = _read_json(_files["restarts"], [])
        items = (items if isinstance(items, list) else [])[-(RESTARTS - 1):]
        items.append({"last_alive": prev.get("alive"), "booted": time.time(), "pid": prev.get("pid")})
        _write_json(_files["restarts"], items)
        print(f"[loop] the previous server process ({prev.get('pid')}) stopped without a clean shutdown",
              file=sys.stderr, flush=True)
    _beat()


def stop() -> None:
    """Mark a clean shutdown (call from a shutdown hook)."""
    _beat(clean=True)


def start(loop: Optional[asyncio.AbstractEventLoop] = None, state_dir: Optional[str] = None) -> bool:
    """Start the watchdog on the running loop (call from a startup hook). Idempotent."""
    if _state["started"]:
        return False
    loop = loop or asyncio.get_running_loop()
    _note_restart(state_dir)
    if _files["beat"] is not None:
        loop.create_task(_beater())
    _state["loop_thread"] = threading.get_ident()
    _state["tick"] = time.monotonic()
    loop.create_task(_ticker())
    threading.Thread(target=_watch, name="javis-loop-watch", daemon=True).start()
    _state["started"] = True
    return True


def report() -> dict:
    """The recent incidents, newest first, for GET /health/loop."""
    with _lock:
        items = [dict(i) for i in reversed(_incidents)]
        lag = (time.monotonic() - _state["tick"]) if _state["tick"] else None
    restarts = _read_json(_files["restarts"], [])
    return {"running": bool(_state["started"]), "block_s": BLOCK_S,
            "lag_s": round(lag, 3) if lag is not None else None, "incidents": items,
            "unclean_restarts": list(reversed(restarts if isinstance(restarts, list) else []))}
