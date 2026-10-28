"""A hub turn key that outlives one turn, for an engine process kept warm across turns (warm_pool.py, 0.382.0).

A warm `claude` or `codex app-server` connects to the hub ONCE, so the `X-Javis-Turn` header it sends is fixed for its
whole life. A lane gives it one fixed key, and `attach` points that key at the turn running now: the key goes into
turn_context's key table with that turn and onto the turn's own key list, so the turn's `reset` removes it like any
key the turn issued. Between two turns the key resolves to None, which keeps turn_context's rule that a key dies with
its turn: a command left running by the last turn cannot act as anyone.

`context()` is a context whose current turn follows the lane, for the Claude SDK's background task (hooks and
in-process plugin tools run there; the SDK creates it once at connect time, so it would otherwise see the first turn
forever).

Kept out of turn_context.py on purpose: that file is pinned by the native qualification evidence
(improvement_claude.PROFILE_SOURCES), so this module works through its table instead of editing it.
"""
from __future__ import annotations

import contextvars
import secrets
import time
from typing import Optional

import turn_context as tc


class _LaneBinding(tc._Binding):
    """A binding that mirrors the turn it is attached to: alive, turn and key list are the owner turn's own, so the
    turn's reset() ends everything done in the lane's context (current() reads None, minted keys are dropped)."""

    def __init__(self):   # no super().__init__: every slot is a view on the owner
        self.owner = None

    @property
    def alive(self):
        o = self.owner
        return o is not None and o.alive

    @alive.setter
    def alive(self, value):
        pass

    @property
    def turn(self):
        o = self.owner
        return o.turn if o is not None else {}

    @turn.setter
    def turn(self, value):
        pass

    @property
    def keys(self):
        o = self.owner
        return o.keys if o is not None else []

    @keys.setter
    def keys(self, value):
        pass


class Lane:
    def __init__(self):
        self.key = secrets.token_urlsafe(24)
        self._binding = _LaneBinding()

    def attach(self) -> bool:
        """Point the lane at the current turn until that turn resets. False (and nobody) outside a live turn."""
        b = tc._CURRENT.get()
        if b is None or not b.alive or isinstance(b, _LaneBinding):
            self.detach()
            return False
        with tc._LOCK:
            tc._KEYS[self.key] = (tc._copy(b.turn), time.time() + tc._KEY_TTL_S)
            self._binding.owner = b
        if self.key not in b.keys:
            b.keys.append(self.key)   # the turn's reset() drops it from the table
        return True

    def detach(self) -> None:
        """Back to nobody now (the end of the query; the turn's reset() does the same if this never runs)."""
        with tc._LOCK:
            tc._KEYS.pop(self.key, None)
            owner, self._binding.owner = self._binding.owner, None
        if owner is not None:
            try:
                owner.keys.remove(self.key)
            except ValueError:
                pass

    def close(self) -> None:
        self.detach()

    def turn(self) -> Optional[dict]:
        return tc.resolve_key(self.key)

    def context(self) -> contextvars.Context:
        ctx = contextvars.copy_context()
        ctx.run(tc._CURRENT.set, self._binding)
        return ctx
