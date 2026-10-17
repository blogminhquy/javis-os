"""Keep the prompt cache of a Claude Code chat warm across a short break (0.202.0). OFF by default.

Idea borrowed from OpenMausBot, which ported it from Cache Tax (MIT, Karan Bansal,
github.com/karanb192/claude-code-mods). On a Pro/Max plan, Claude Code's prompt cache lives one hour.
Step away for 70 minutes and the next message re-writes the whole conversation prefix (the
system prompt, the tools, every earlier turn), which on a long chat is tens of thousands of tokens
of the plan's allowance. One tiny request just before the hour is up re-reads that prefix and keeps
it alive for another hour, for a few output tokens.

How a ping works (claude_sdk_engine.ClaudeSDK.warm_ping): the same engine the chat used, resumed
from the chat's Claude session with `fork_session` and `--no-session-persistence`, so nothing is
written to the conversation; every tool call is denied; the prompt asks for one word.

Rules, so it never turns into background use of the plan:
  - Only when the person switched it on (setting `cache_keepwarm.enabled`), only for chats on the
    Claude Code subscription engine (an API key's cache lives five minutes: pinging costs more).
  - A chat is pinged only inside WINDOW_MIN minutes after its last real message, at most every
    PING_AFTER_S, and never while a turn is running.
  - A ping that comes back cold (it had to write the prefix instead of reading it) stops the window:
    the cache was already gone, more pings would only spend.
  - A usage-limit answer stops every window until the next real message.
State is in memory only: after a restart the next message misses the cache anyway.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

PING_AFTER_S = 50 * 60
DEFAULT_WINDOW_MIN = 120
MAX_WINDOW_MIN = 8 * 60
MAX_WRITE_RATIO = 0.1
MIN_PREFIX_TOKENS = 20_000


def ping_was_warm(cache_read: int, cache_write: int) -> bool:
    """A warm ping read the prefix and wrote only its own few tokens."""
    return cache_read > 0 and cache_write < MAX_WRITE_RATIO * cache_read


@dataclass
class _Window:
    key: str
    engine: Any
    last_real_at: float
    last_ping_at: float = 0.0
    prefix_tokens: int = 0
    pings: int = 0
    stopped: str = ""


@dataclass
class KeepWarm:
    enabled: Callable[[], bool] = lambda: False
    window_min: Callable[[], int] = lambda: DEFAULT_WINDOW_MIN
    busy: Callable[[str], bool] = lambda key: False
    now: Callable[[], float] = time.time
    windows: Dict[str, _Window] = field(default_factory=dict)
    limited_until_real: bool = False
    log: list = field(default_factory=list)

    def note_turn(self, key: str, engine: Any, prefix_tokens: int = 0) -> None:
        """A real chat turn on the subscription engine finished: (re)open its window."""
        if not key or engine is None:
            return
        self.limited_until_real = False
        self.windows[key] = _Window(key=key, engine=engine, last_real_at=self.now(),
                                    prefix_tokens=int(prefix_tokens or 0))

    def forget(self, key: str) -> None:
        self.windows.pop(key, None)

    def due(self) -> list:
        """Windows that should be pinged now."""
        if not self.enabled() or self.limited_until_real:
            return []
        now = self.now()
        span = max(1, min(int(self.window_min() or DEFAULT_WINDOW_MIN), MAX_WINDOW_MIN)) * 60
        out = []
        for w in list(self.windows.values()):
            if w.stopped:
                continue
            if now - w.last_real_at > span:
                self.windows.pop(w.key, None)
                continue
            if w.prefix_tokens and w.prefix_tokens < MIN_PREFIX_TOKENS:
                continue
            since = now - max(w.last_real_at, w.last_ping_at)
            if since >= PING_AFTER_S and not self.busy(w.key):
                out.append(w)
        return out

    async def tick(self) -> int:
        """Ping every due window once. Returns how many pings were sent. Never raises."""
        sent = 0
        for w in self.due():
            try:
                res = await w.engine.warm_ping()
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
            w.last_ping_at = self.now()
            w.pings += 1
            sent += 1
            self.log.append({"key": w.key, "at": w.last_ping_at, **{k: res.get(k) for k in
                             ("ok", "cache_read", "cache_write", "reason", "limit")}})
            self.log = self.log[-50:]
            if not res.get("ok"):
                if res.get("limit"):
                    self.limited_until_real = True
                w.stopped = str(res.get("reason") or "ping failed")[:200]
            elif not ping_was_warm(int(res.get("cache_read") or 0), int(res.get("cache_write") or 0)):
                w.stopped = "cold"
        return sent

    def status(self) -> dict:
        return {"enabled": bool(self.enabled()), "windows": len(self.windows),
                "limited": self.limited_until_real, "recent": self.log[-10:]}
