"""An MCP source that just failed to start answers at once instead of being respawned on every call (0.83.2).

    python tests/run.py mcp_fast_fail      (no network)

Before 0.83.2 every `tools/call` to a dead source started a fresh session: a hung stdio server waits up to
90 seconds in `initialize`, and the model usually retries the same tool two or three times, so one loop
iteration could sit for minutes and pay tokens for turns that could never work. `connect_health` already
knew the source was down, but only reported it; nothing on the call path read it.

The pool now remembers a STARTUP failure (the request was never sent) for `_DOWN_TTL` seconds and answers
those calls immediately. It does not remember a failure in the middle of a call: the server may only be
slow, and that case already has its own rule (no resend of a tool that may have taken effect).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-mcp-fast-fail-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + repr(extra) + "]") if not cond else ""))
    if not cond:
        _fails.append(name)


class FakeSession:
    """Session double: `starts` counts how many times the pool had to build and start one."""
    starts = 0
    init_error = None      # raised by ensure_init (startup failure)
    call_error = None      # raised by call_tool after a good start (mid-call failure)

    def __init__(self):
        self._init_done = False

    async def ensure_init(self):
        if self._init_done:
            return
        FakeSession.starts += 1
        if FakeSession.init_error:
            raise FakeSession.init_error
        self._init_done = True

    async def call_tool(self, name, arguments):
        await self.ensure_init()
        if FakeSession.call_error:
            raise FakeSession.call_error
        return {"content": [{"type": "text", "text": "ok"}]}

    async def list_tools(self):
        await self.ensure_init()
        return [{"name": "t"}]

    async def close(self):
        pass


def fresh_pool():
    p = mcp_client.SessionPool()
    p._make = lambda spec: FakeSession()
    FakeSession.starts, FakeSession.init_error, FakeSession.call_error = 0, None, None
    return p


SPEC = {"key": "pos-1", "transport": "stdio", "command": "npx", "args": ["pos-mcp"], "label": "POS"}


def call(pool, spec=SPEC):
    return asyncio.run(pool.call_tool(spec, "list_orders", {}))


# ---- A startup failure is remembered ----
pool = fresh_pool()
FakeSession.init_error = RuntimeError("process closed stdout (ModuleNotFoundError: mcp)")
first = call(pool)
starts_after_first = FakeSession.starts
second = call(pool)
check("the first call reports the startup error", str(first).startswith("ERROR"), first)
check("the second call within the window does not start the source again",
      FakeSession.starts == starts_after_first, (starts_after_first, FakeSession.starts))
check("the fast answer is an error that names the real cause",
      str(second).startswith("ERROR") and "ModuleNotFoundError" in str(second), second)

# ---- The window ends ----
mcp_client._DOWN_TTL, saved_ttl = 0, mcp_client._DOWN_TTL
call(pool)
check("after the window the source is tried again", FakeSession.starts > starts_after_first)
mcp_client._DOWN_TTL = saved_ttl

# ---- Recovery clears the mark ----
pool = fresh_pool()
FakeSession.init_error = RuntimeError("process closed stdout")
call(pool)
FakeSession.init_error = None
tools = asyncio.run(pool.list_tools(SPEC))         # what the Check button and the health sweep do
before = FakeSession.starts
ok = call(pool)
check("a good tools/list (Check button, health sweep) clears the mark", tools and "ok" in str(ok), ok)

# ---- New credentials or config are tried at once ----
pool = fresh_pool()
FakeSession.init_error = RuntimeError("401 unauthorized")
call(pool)
FakeSession.init_error = None
before = FakeSession.starts
ok = call(pool, dict(SPEC, env={"POS_TOKEN": "new"}))
check("a changed spec (new token, new env) is not blocked by the old mark",
      FakeSession.starts == before + 1 and "ok" in str(ok), ok)

# ---- A failure in the middle of a call is not remembered ----
pool = fresh_pool()
FakeSession.call_error = TimeoutError("tool did not answer after 120s")
call(pool)
FakeSession.call_error = None
ok = call(pool)
check("a mid-call timeout does not block the next call", "ok" in str(ok), ok)

check("no em dash in the new source (CLAUDE.md rule)", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
