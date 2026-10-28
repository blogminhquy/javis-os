"""Engine processes kept warm between the owner's chat turns (0.382.0).

Spec: docs/dev/2026-10-toc-do-luot-chat-spec.md. Measured on 28/10/2026: a chat turn that opens a new `claude` process
costs 3.4 to 4.9 s for a one-word answer, the same turn on a process kept alive 1.3 to 1.6 s. Every MCP the turn
connects to adds to the cold side. Keeping one process per conversation forever would grow RAM with the number of
conversations (228 MB per idle `claude`, 57 MB per idle `codex app-server`), so this pool keeps them WITH A CEILING:

- one slot per conversation, carrying a fingerprint of the engine configuration it was opened with; a turn whose
  fingerprint differs closes the old slot and runs cold;
- a memory budget: a quarter of the free RAM (the container's own limit when there is one), at most 1,200 MB, or
  JAVIS_WARM_BUDGET_MB (0 turns the pool off). A full pool evicts the idle slot used longest ago, never a busy one;
  with nothing idle to evict the turn simply runs cold and its process is closed as before;
- an idle slot closes after JAVIS_WARM_IDLE_S (300 s, the provider's prompt-cache lifetime: past it the next turn
  reloads the context anyway, the process would only save the start-up);
- a closed idle slot leaves its recipe, so `prewarm` (the owner started typing) can reopen it before the message lands.

Only owner chat turns use it. Background work and customer bots keep one process per run (they need parallel runs,
not seconds). A miss always means "run exactly as before".
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import threading
import time
from typing import Awaitable, Callable, Dict, Optional

SLOT_MB = {"claude": 300, "codex": 80}
DEFAULT_IDLE_S = 300.0
MAX_BUDGET_MB = 1200
# A recipe older than this is not worth a speculative start. 12 h (0.387.0, was 1 h) so a chat left over lunch or
# overnight-ish still opens warm; the recipe is only in memory, and a stale one costs at most one discarded start
# (its fingerprint no longer matches) within the same RAM budget.
RECIPE_TTL_S = 12 * 3600.0
REAP_EVERY_S = 30.0
MAX_RECIPES = 200          # each holds the engine options and prompt text of one chat (tens of KB)


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.getenv(name)
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def idle_s() -> float:
    return max(10.0, _env_float("JAVIS_WARM_IDLE_S", DEFAULT_IDLE_S))


def _cgroup_free_mb() -> Optional[float]:
    """Room left under the container's memory limit (cgroup v2, then v1). None without a limit."""
    for limit_p, used_p in (("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
                            ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
                             "/sys/fs/cgroup/memory/memory.usage_in_bytes")):
        try:
            with open(limit_p) as f:
                raw = f.read().strip()
            if raw == "max":
                return None
            limit = int(raw)
            if limit <= 0 or limit >= 1 << 60:   # v1 reports "no limit" as a huge number
                return None
            with open(used_p) as f:
                used = int(f.read().strip())
            return max(0.0, (limit - used) / 2 ** 20)
        except (OSError, ValueError):
            continue
    return None


def free_ram_mb() -> float:
    """Free RAM in MB, or 2048 when the platform does not say. Never raises."""
    free = None
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        free = int(line.split()[1]) / 1024
                        break
            cg = _cgroup_free_mb()
            if cg is not None:
                free = cg if free is None else min(free, cg)
        elif os.name == "nt":
            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                free = ms.ullAvailPhys / 2 ** 20
    except Exception:  # noqa: BLE001 - a wrong guess only sizes the pool, it must never break a turn
        free = None
    return float(free) if free is not None else 2048.0


def budget_mb(in_use_mb: float = 0.0) -> float:
    """What the pool may hold. Free RAM already excludes what the pool's own processes use, so they are added back."""
    raw = os.getenv("JAVIS_WARM_BUDGET_MB")
    if raw not in (None, ""):
        return max(0.0, _env_float("JAVIS_WARM_BUDGET_MB", 0.0))
    return min(float(MAX_BUDGET_MB), (free_ram_mb() + in_use_mb) * 0.25)


class Handle:
    """What an engine keeps in a slot. Subclasses: claude_warm.ClaudeHandle, codex_steer.CodexHandle."""
    kind = ""

    def alive(self) -> bool:
        return False

    async def close(self) -> None:
        return None


class Slot:
    __slots__ = ("key", "kind", "fingerprint", "handle", "busy", "last_used", "loop", "recipe", "turns")

    def __init__(self, key: str, kind: str, fingerprint: str, handle: Handle, recipe=None):
        self.key = key
        self.kind = kind
        self.fingerprint = fingerprint
        self.handle = handle
        self.busy = True
        self.last_used = time.monotonic()
        self.loop = asyncio.get_running_loop()
        self.recipe = recipe        # async () -> Handle, to reopen the same process later (prewarm)
        self.turns = 0

    @property
    def weight(self) -> int:
        return SLOT_MB.get(self.kind, 300)


class Pool:
    def __init__(self):
        self._slots: Dict[str, Slot] = {}
        self._recipes: Dict[str, tuple] = {}     # key -> (kind, fingerprint, recipe, saved_at)
        self._lock = threading.Lock()
        self._reaper: Optional[asyncio.Task] = None
        self._prewarming: set = set()
        self._gen: Dict[str, int] = {}           # key -> bumped by every turn that looks for its slot
        self.stats = {"hits": 0, "misses": 0, "admitted": 0, "refused": 0, "evicted": 0, "expired": 0,
                      "prewarmed": 0}

    # ---- turn side ----
    def take(self, key: str, kind: str, fingerprint: str) -> Optional[Slot]:
        """The warm slot of this conversation when it matches, marked busy. None = run cold. A slot that no longer
        matches (other config, dead process, other event loop) is closed."""
        if not key or budget_mb() <= 0:
            return None
        stale = None
        with self._lock:
            self._gen[key] = self._gen.get(key, 0) + 1   # a prewarm started before this turn must not land after it
            slot = self._slots.get(key)
            if slot is not None and not slot.busy:
                try:
                    same_loop = slot.loop is asyncio.get_running_loop()
                except RuntimeError:
                    same_loop = False
                if slot.kind == kind and slot.fingerprint == fingerprint and same_loop and slot.handle.alive():
                    slot.busy = True
                    slot.turns += 1
                    self.stats["hits"] += 1
                    return slot
                stale = self._slots.pop(key)
            self.stats["misses"] += 1
        if stale is not None:
            self._close_soon(stale)
        return None

    def peek(self, key: str) -> Optional[Slot]:
        """The slot of this conversation, untouched (to explain a miss)."""
        with self._lock:
            return self._slots.get(key)

    def admit(self, key: str, kind: str, fingerprint: str, handle: Handle, recipe=None, may_evict: bool = True,
              gen: Optional[int] = None) -> Optional[Slot]:
        """A cold turn opened `handle`: keep it for the next turn if the budget allows (evicting idle slots). Returns
        the slot, busy, or None when it did not fit (the caller closes the handle as before).
        A prewarm passes may_evict=False and the generation it started at: it never pushes anyone out, never replaces a
        slot, and gives up when a turn looked for this conversation meanwhile (that turn's own process is newer)."""
        if not key or not handle.alive():
            return None
        weight = SLOT_MB.get(kind, 300)
        evict = []
        with self._lock:
            old = self._slots.get(key)
            if gen is not None and (old is not None or self._gen.get(key, 0) != gen):
                self.stats["refused"] += 1
                return None
            if old is not None and old.busy:
                self.stats["refused"] += 1
                return None        # the same conversation is running elsewhere: never two warm processes for it
            if old is not None:
                evict.append(self._slots.pop(key))
            used = sum(s.weight for s in self._slots.values())
            cap = budget_mb(used)
            idle = sorted((s for s in self._slots.values() if not s.busy), key=lambda s: s.last_used)
            while may_evict and used + weight > cap and idle:
                s = idle.pop(0)
                self._slots.pop(s.key, None)
                evict.append(s)
                used -= s.weight
                self.stats["evicted"] += 1
            if used + weight > cap:
                self.stats["refused"] += 1
                admitted = None
            else:
                admitted = Slot(key, kind, fingerprint, handle, recipe)
                self._slots[key] = admitted
                self.stats["admitted"] += 1
        for s in evict:
            self._remember(s)
            self._close_soon(s)
        if admitted is not None:
            self._ensure_reaper()
        return admitted

    def release(self, slot: Slot, keep: bool = True, fingerprint: Optional[str] = None) -> None:
        """End of the turn. keep=False (an error, a process that must exit) closes it. `fingerprint` updates what the
        slot now is (a Claude slot's session id moves on with every turn)."""
        if fingerprint:
            slot.fingerprint = fingerprint
        slot.last_used = time.monotonic()
        with self._lock:
            mine = self._slots.get(slot.key) is slot
            if keep and mine and slot.handle.alive():
                slot.busy = False
                return
            if mine:
                self._slots.pop(slot.key, None)
        self._remember(slot)
        self._close_soon(slot)

    # ---- prewarm ----
    def remember(self, key: str, kind: str, fingerprint: str, recipe) -> None:
        if key and recipe is not None:
            with self._lock:
                self._recipes.pop(key, None)
                self._recipes[key] = (kind, fingerprint, recipe, time.monotonic())
                while len(self._recipes) > MAX_RECIPES:   # insertion order = oldest first
                    self._recipes.pop(next(iter(self._recipes)))

    def _remember(self, slot: Slot) -> None:
        if slot.recipe is not None:
            self.remember(slot.key, slot.kind, slot.fingerprint, slot.recipe)

    def prewarm(self, key: str) -> bool:
        """The owner started typing in this conversation: reopen its last process in the background if it has none.
        True when a start was scheduled. Never raises."""
        try:
            if not key or budget_mb() <= 0:
                return False
            with self._lock:
                if key in self._slots or key in self._prewarming:
                    return False
                rec = self._recipes.get(key)
                if rec is None or time.monotonic() - rec[3] > RECIPE_TTL_S:
                    self._recipes.pop(key, None)
                    return False
                self._prewarming.add(key)
                gen = self._gen.get(key, 0)
            self._keep_task(asyncio.get_running_loop().create_task(self._prewarm(key, rec, gen)))
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[warm pool] prewarm {type(e).__name__}: {e}", file=sys.stderr)
            return False

    async def _prewarm(self, key: str, rec: tuple, gen: int) -> None:
        kind, fingerprint, recipe, _ = rec
        handle = None
        try:
            with self._lock:
                used = sum(s.weight for s in self._slots.values())
            if used + SLOT_MB.get(kind, 300) > budget_mb(used):
                return     # no room without evicting someone actually in use recently: not worth a guess
            handle = await recipe()
            slot = self.admit(key, kind, fingerprint, handle, recipe, may_evict=False, gen=gen)
            if slot is None:
                await handle.close()
                return
            self.stats["prewarmed"] += 1
            print(f"[warm pool] prewarmed {kind} {key[:12]}", file=sys.stderr)
            self.release(slot)
        except Exception as e:  # noqa: BLE001 - a failed guess costs nothing but the attempt
            print(f"[warm pool] prewarm {key[:12]} failed: {type(e).__name__}: {e}", file=sys.stderr)
            if handle is not None:
                try:
                    await handle.close()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            with self._lock:
                self._prewarming.discard(key)

    # ---- housekeeping ----
    _tasks: set = set()

    def _keep_task(self, task) -> None:
        """Hold a reference until the task is done (asyncio keeps only weak ones)."""
        Pool._tasks.add(task)
        task.add_done_callback(Pool._tasks.discard)

    def _close_soon(self, slot: Slot) -> None:
        async def _close():
            try:
                await slot.handle.close()
            except Exception as e:  # noqa: BLE001
                print(f"[warm pool] close {slot.kind} {type(e).__name__}: {e}", file=sys.stderr)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop is slot.loop:
            self._keep_task(loop.create_task(_close()))
        elif slot.loop is not None and not slot.loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(_close(), slot.loop)
            except RuntimeError:
                pass

    def _ensure_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            try:
                self._reaper = asyncio.get_running_loop().create_task(self._reap_loop())
            except RuntimeError:
                self._reaper = None

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(REAP_EVERY_S)
            self.reap()
            with self._lock:
                if not self._slots:
                    return

    def reap(self, now: Optional[float] = None) -> int:
        """Close idle slots past their idle time and dead ones. Returns how many."""
        now = time.monotonic() if now is None else now
        limit = idle_s()
        out = []
        with self._lock:
            for key, s in list(self._slots.items()):
                if s.busy:
                    continue
                if now - s.last_used > limit or not s.handle.alive():
                    out.append(self._slots.pop(key))
                    self.stats["expired"] += 1
        for s in out:
            print(f"[warm pool] closed idle {s.kind} {s.key[:12]} after {s.turns + 1} turn(s)", file=sys.stderr)
            self._remember(s)
            self._close_soon(s)
        return len(out)

    def drop_kind(self, kind: str) -> int:
        """Close every idle slot of one engine and forget its recipes (a sign-in or sign-out changed who it runs as).
        A busy slot is taken out of the table, so its turn's release() closes it. Callable from a worker thread."""
        with self._lock:
            out = [s for s in self._slots.values() if s.kind == kind]
            for s in out:
                self._slots.pop(s.key, None)
            for key in [k for k, r in self._recipes.items() if r[0] == kind]:
                self._recipes.pop(key, None)
        for s in out:
            if not s.busy:
                self._close_soon(s)
        return len(out)

    def forget(self, key: str) -> None:
        """The conversation was deleted or reset: close its slot and drop its recipe."""
        with self._lock:
            s = self._slots.pop(key, None)
            self._recipes.pop(key, None)
        if s is not None and not s.busy:
            self._close_soon(s)
        # A busy slot is no longer in the table, so its turn's release() closes it.

    async def close_all(self) -> None:
        with self._lock:
            slots = list(self._slots.values())
            self._slots.clear()
            self._recipes.clear()
        for s in slots:
            try:
                await s.handle.close()
            except Exception:  # noqa: BLE001
                pass

    def status(self) -> dict:
        with self._lock:
            slots = [{"kind": s.kind, "busy": s.busy, "turns": s.turns,
                      "idle_s": round(time.monotonic() - s.last_used, 1)} for s in self._slots.values()]
            used = sum(s.weight for s in self._slots.values())
        return {"slots": slots, "used_mb": used, "budget_mb": round(budget_mb(used)), "idle_s": idle_s(),
                **self.stats}


POOL = Pool()
