"""Values the event loop reads from memory instead of waiting for the disk.

GET /health/loop on the owner's VPS (2026-11-09 and 2026-11-13): one `stat` or one small read sometimes takes
seconds there, once 93 seconds, most often right after an update, when the disk is busy with everything that
starts again. Whatever asks the disk from the event loop freezes every page, every bot and the hub for that long,
and the container then fails its health check.

A `Value` wraps one such read (the signature of a few files, a small JSON store). The rules:

- A value younger than `fresh_s` is reused by every caller without touching the disk.
- ON THE EVENT LOOP a value younger than RECHECK_S is reused as well. An older one is read again on a helper
  thread, and the loop waits for that read for WAIT_S at most: a healthy disk answers long before, so the caller
  gets the new value; a stalled disk does not, so the caller gets the last value and the read finishes behind it.
  While that read is still running, later calls take the last value without waiting at all.
- The loop reads for itself only when there is nothing to fall back on: the first call, or the call after `drop()`.
- Every other thread reads for itself, exactly as before this module existed.
- `drop()` forgets the value. Code that just changed the files calls it, and the very next call reads them.

So a change made through Javis shows at once. A change made behind its back (a hand edit, another process) shows
on the event loop within RECHECK_S; on other threads it still shows at once.

JAVIS_KEPT_OFF=1 switches the event-loop rules off: every caller then reads for itself as it did before.
"""
from __future__ import annotations

import asyncio
import os
import queue
import sys
import threading
import time
import weakref
from pathlib import Path
from typing import Any, Callable, Optional, Union

# On the event loop, a value younger than this is reused without asking. Also the pause between two tries when a
# read on a helper thread failed, so a read that keeps failing is not asked for on every call.
RECHECK_S = 1.0
# How long the event loop waits for a helper thread's read before it goes on with the last value. A stat or a
# small read takes well under a millisecond on a healthy disk, thread hand-over included.
WAIT_S = 0.02
# Helper threads shared by every Value. Each Value has at most one read waiting or running, so the queue never
# holds more jobs than there are Values. More than one thread, so one stalled folder does not hold up the rest.
HELPERS = 4

# A read at least this slow is listed by `report()` even when no caller had to go on without it.
SLOW_READ_S = 0.3

_jobs: "queue.SimpleQueue[Callable[[], None]]" = queue.SimpleQueue()
_threads: list = []
_threads_lock = threading.Lock()
_all: "weakref.WeakSet[Value]" = weakref.WeakSet()    # every live Value, for `report()`
_all_lock = threading.Lock()


def _work() -> None:
    while True:
        job = _jobs.get()
        try:
            job()
        except BaseException as e:  # noqa: BLE001 - a helper must outlive whatever one read does
            print(f"[kept] helper: {type(e).__name__}: {e}", file=sys.stderr)


def _behind(job: Callable[[], None]) -> None:
    """Run `job` on a helper thread. Daemon threads, so a read stuck on the disk never holds up a shutdown."""
    with _threads_lock:
        if len(_threads) < HELPERS:
            t = threading.Thread(target=_work, name=f"javis-kept-{len(_threads)}", daemon=True)
            t.start()
            _threads.append(t)
    _jobs.put(job)


def on_loop() -> bool:
    """True when the caller is a thread that is running an asyncio event loop right now."""
    if os.environ.get("JAVIS_KEPT_OFF") == "1":
        return False
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class Value:
    """One value read from the disk by `read()`, kept for the event loop (see the module text).

    `fresh_s`: how long any caller reuses a value without looking; a number, or a function returning one so a
    module constant can still be changed after import. `key`: a function whose result must match for the kept
    value to count (the path being read, so pointing a module at another folder never returns the old folder's
    value)."""

    def __init__(self, read: Callable[[], Any], fresh_s: Union[float, Callable[[], float]] = 0.0,
                 key: Optional[Callable[[], Any]] = None, name: str = ""):
        self._read = read
        self._fresh = fresh_s
        self._key = key
        self.name = name or getattr(read, "__name__", "value")
        self._lock = threading.Lock()
        self._state: Optional[tuple] = None   # (key, value, time the read started); replaced whole, never edited
        self._gen = 0                         # drop() moves it: a read that started before must not be kept
        self._busy = False                    # a read is waiting or running on a helper thread
        self._asked = 0.0                     # when the last helper read was asked for
        self.late = 0                         # helper reads the event loop did not wait out (diagnostics)
        self.reads = 0                        # reads of the disk, on any thread
        self.slowest_s = 0.0                  # the longest of them
        with _all_lock:
            _all.add(self)

    def _fresh_s(self) -> float:
        f = self._fresh
        return float(f() if callable(f) else f)

    def get(self) -> Any:
        k = self._key() if self._key is not None else None
        st = self._state
        if st is None or st[0] != k:
            return self._read_now(k)
        age = time.monotonic() - st[2]
        fresh = self._fresh_s()
        if 0 <= age < fresh:
            return st[1]
        if not on_loop():
            return self._read_now(k)
        if 0 <= age < max(fresh, RECHECK_S):
            return st[1]
        done = self._read_behind(k)
        if done is None:
            return st[1]                      # a helper is already reading (or just failed): do not wait again
        if not done.wait(WAIT_S):
            self.late += 1
            return st[1]
        cur = self._state
        if cur is not None and cur[0] == k:
            return cur[1]
        # Dropped while the helper read: nothing to fall back on, same as a first call.
        return self._read_now(k) if cur is None else st[1]

    def _keep(self, k: Any, value: Any, at: float, gen: int) -> None:
        with self._lock:
            if gen != self._gen:
                return                        # dropped while this read ran: what it saw may be the old files
            if self._state is None or self._state[0] != k or self._state[2] <= at:
                self._state = (k, value, at)

    def _timed(self, at: float) -> None:
        self.reads += 1
        self.slowest_s = max(self.slowest_s, time.monotonic() - at)

    def _read_now(self, k: Any) -> Any:
        gen, at = self._gen, time.monotonic()
        try:
            value = self._read()
        finally:
            self._timed(at)
        self._keep(k, value, at, gen)
        return value

    def _read_behind(self, k: Any) -> Optional[threading.Event]:
        """Start one read on a helper thread. Returns the event set when it ends, None when none was started."""
        now = time.monotonic()
        with self._lock:
            if self._busy or now - self._asked < RECHECK_S:
                return None
            self._busy, self._asked = True, now
        done = threading.Event()

        def job() -> None:
            gen, at = self._gen, time.monotonic()
            try:
                value = self._read()
            except Exception as e:  # noqa: BLE001 - the kept value stays; the next call asks again after RECHECK_S
                print(f"[kept] {self.name}: {type(e).__name__}: {e}", file=sys.stderr)
            else:
                self._keep(k, value, at, gen)
            finally:
                self._timed(at)
                self._busy = False
                done.set()
        _behind(job)
        return done

    def drop(self) -> None:
        """Forget the value: the next call reads the disk, whichever thread makes it."""
        with self._lock:
            self._gen += 1
            self._state = None

    def age(self) -> Optional[float]:
        """Seconds since the kept value was read, None when nothing is kept. For tests and diagnostics."""
        st = self._state
        return None if st is None else time.monotonic() - st[2]


class Keyed:
    """A `Value` per argument, for a read that takes one (a path): `get(arg)` follows the same rules per argument.

    Holds at most `limit` arguments; past that it starts over, so a caller feeding it endless different paths
    cannot grow it without bound."""

    def __init__(self, read: Callable[[Any], Any], fresh_s: Union[float, Callable[[], float]] = 0.0,
                 limit: int = 256, name: str = ""):
        self._read = read
        self._fresh = fresh_s
        self._limit = max(1, int(limit))
        self.name = name or getattr(read, "__name__", "values")
        self._values: dict = {}
        self._lock = threading.Lock()

    def get(self, arg: Any) -> Any:
        v = self._values.get(arg)
        if v is None:
            with self._lock:
                v = self._values.get(arg)
                if v is None:
                    if len(self._values) >= self._limit:
                        self._values = {}
                    v = Value(lambda: self._read(arg), self._fresh, name=f"{self.name}[{arg}]")
                    self._values[arg] = v
        return v.get()

    def drop(self, arg: Any = None) -> None:
        """Forget one argument's value, or every value when called without one."""
        with self._lock:
            if arg is None:
                self._values = {}
            else:
                self._values.pop(arg, None)


_RESOLVED = Keyed(lambda p: str(Path(p).resolve()), name="resolved path")


def resolved(path: Any) -> str:
    """`str(Path(path).resolve())` by the rules above. Resolving walks every folder of the path on the disk, and
    the scheduler does it for every brain on every 30-second beat, on the event loop."""
    return _RESOLVED.get(str(path))


def forget_resolved() -> None:
    """Folders were created, removed or renamed through Javis: resolve them again from now on."""
    _RESOLVED.drop()


def report() -> dict:
    """What the disk did behind the event loop, for GET /health/loop: the reads the loop went on without (`late`)
    and the slow ones. An empty `slow` list on a machine that used to freeze means the disk was fine since the
    start; a long one with no freeze in `slow_top` means the disk was slow and the loop did not wait for it."""
    with _all_lock:
        values = list(_all)
    rows = [{"what": v.name, "late": v.late, "slowest_s": round(v.slowest_s, 3), "reads": v.reads}
            for v in values if v.late or v.slowest_s >= SLOW_READ_S]
    rows.sort(key=lambda r: (-r["late"], -r["slowest_s"]))
    return {"wait_s": WAIT_S, "recheck_s": RECHECK_S, "late_total": sum(r["late"] for r in rows), "slow": rows[:15]}
