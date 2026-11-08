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

Slow spots (2026-11-08). An incident starts at BLOCK_S (2 s): long enough to drop sockets, far too long to see lag. The
owner felt "a few seconds" on page loads and chat switches while the loop froze 0.3 to 1.5 s at a time (the Kanban
dispatcher writing SQLite on the loop), and none of it reached this report. So every freeze of SLOW_S or more is
sampled too: the watch thread takes the loop thread's stack each tick while it is frozen, and the freeze is counted
against the Javis code it was stuck in most often. GET /health/loop then lists the slow spots by total time lost
(`slow_top`) and the latest ones (`slow_recent`), on the owner's real machine instead of a guess.
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

# 2026-11-08: 0.05 (was 0.25) so a freeze of a few hundred ms is measured to within 50 ms. One timer callback per tick.
TICK_S = 0.05
try:
    BLOCK_S = max(0.2, float(os.environ.get("JAVIS_LOOP_BLOCK_S", "2")))
except ValueError:
    BLOCK_S = 2.0
try:
    SLOW_S = max(0.1, float(os.environ.get("JAVIS_LOOP_SLOW_S", "0.3")))
except ValueError:
    SLOW_S = 0.3
SLOW_LOG_S = 1.0          # a slow spot this long also gets one line in the server log
SLOW_PLACES = 40          # distinct code places kept, the ones that lost the least time drop out first
SLOW_RECENT = 30
_HERE = os.path.dirname(os.path.abspath(__file__))
INCIDENTS = 20
STACK_LINES = 14
BEAT_S = 10.0
RESTARTS = 10

_files = {"beat": None, "restarts": None}

CLIENT_DROPS = 30
_client_drops: deque = deque(maxlen=CLIENT_DROPS)

_state = {"tick": 0.0, "loop_thread": None, "started": False, "current": None, "slow": None, "since": 0.0}
_incidents: deque = deque(maxlen=INCIDENTS)
_slow_places: dict = {}
_slow_recent: deque = deque(maxlen=SLOW_RECENT)
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


def _where(thread_id: Optional[int]) -> tuple:
    """(place, stack) of the loop thread now: place = the three innermost Javis frames, innermost first."""
    frame = sys._current_frames().get(thread_id) if thread_id else None
    if frame is None:
        return "", []
    st = traceback.extract_stack(frame)
    ours = [f for f in st if f.filename.startswith(_HERE) and not f.filename.endswith("loop_watch.py")]
    pick = ours[-3:] if ours else st[-1:]
    place = " < ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in reversed(pick))
    return place, [ln.rstrip() for ln in traceback.format_list(st[-STACK_LINES:])]


def _slow_end(cur: dict) -> None:
    """Count one finished slow spot against the place it spent most of its samples in. Call under _lock."""
    samples = cur["samples"]
    place = max(samples, key=samples.get) if samples else "(no Python frame: C code or the interpreter)"
    sec = round(cur["seconds"], 2)
    agg = _slow_places.get(place)
    if agg is None:
        agg = _slow_places[place] = {"where": place, "count": 0, "total_s": 0.0, "max_s": 0.0, "stack": []}
    agg["count"] += 1
    agg["total_s"] = round(agg["total_s"] + sec, 2)
    if sec >= agg["max_s"]:
        agg["max_s"] = sec
        agg["stack"] = cur["stacks"].get(place) or agg["stack"]
    agg["last_at"] = cur["at"]
    if len(_slow_places) > SLOW_PLACES:
        _slow_places.pop(min(_slow_places, key=lambda k: _slow_places[k]["total_s"]), None)
    _slow_recent.append({"at": cur["at"], "seconds": sec, "where": place})
    if SLOW_LOG_S <= sec < BLOCK_S:   # from BLOCK_S up the incident below already printed the stack
        print(f"[loop] slow {sec:.1f}s at {place}", file=sys.stderr, flush=True)


def _slow_track(lag: float) -> None:
    """Sample the loop thread on every tick of a freeze of SLOW_S or more; close the spot once it ticks again."""
    cur = _state["slow"]
    if lag >= SLOW_S:
        if cur is None:
            cur = _state["slow"] = {"at": time.time() - lag, "seconds": lag, "samples": {}, "stacks": {}}
        cur["seconds"] = max(cur["seconds"], lag)
        place, stack = _where(_state["loop_thread"])
        if place:
            cur["samples"][place] = cur["samples"].get(place, 0) + 1
            cur["stacks"].setdefault(place, stack)
    elif cur is not None:
        _state["slow"] = None
        _slow_end(cur)


def _watch() -> None:
    while True:
        time.sleep(TICK_S)
        last = _state["tick"]
        if not last:
            continue
        lag = time.monotonic() - last
        with _lock:
            _slow_track(lag)
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
    _state["since"] = time.time()
    _state["tick"] = time.monotonic()
    loop.create_task(_ticker())
    threading.Thread(target=_watch, name="javis-loop-watch", daemon=True).start()
    _state["started"] = True
    return True


def _clean_drop(d) -> dict:
    d = d if isinstance(d, dict) else {}

    def num(v):
        try:
            return round(float(v), 1)
        except (TypeError, ValueError):
            return None
    return {"code": str(d.get("code", ""))[:20], "clean": bool(d.get("clean")), "open_s": num(d.get("open_s")),
            "at": num(d.get("at"))}


def note_client_drops(body) -> None:
    """Keep one page's report of how it lost its socket (0.197.1). Bounded: the last CLIENT_DROPS reports, each with
    at most 10 drops and short strings, so a page cannot grow the server's memory."""
    body = body if isinstance(body, dict) else {}
    drops = body.get("drops") if isinstance(body.get("drops"), list) else []
    try:
        down = round(float(body.get("down_s") or 0), 1)
    except (TypeError, ValueError):
        down = 0.0
    with _lock:
        _client_drops.append({"received": time.time(), "ua": str(body.get("ua") or "")[:200], "down_s": down,
                              "drops": [_clean_drop(d) for d in drops[-10:]]})


def report() -> dict:
    """The recent incidents, newest first, for GET /health/loop."""
    with _lock:
        items = [dict(i) for i in reversed(_incidents)]
        clients = [dict(c) for c in reversed(_client_drops)]
        lag = (time.monotonic() - _state["tick"]) if _state["tick"] else None
        slow_top = sorted((dict(v) for v in _slow_places.values()), key=lambda v: -v["total_s"])[:15]
        slow_recent = [dict(x) for x in reversed(_slow_recent)]
    restarts = _read_json(_files["restarts"], [])
    return {"running": bool(_state["started"]), "block_s": BLOCK_S,
            "lag_s": round(lag, 3) if lag is not None else None, "incidents": items,
            "slow_s": SLOW_S, "slow_since": _state["since"] or None,
            "slow_top": slow_top, "slow_recent": slow_recent,
            "unclean_restarts": list(reversed(restarts if isinstance(restarts, list) else [])),
            "client_drops": clients}
