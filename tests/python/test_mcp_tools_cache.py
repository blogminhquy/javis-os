"""The MCP pool reuses a live session's tool list instead of asking the server again (2026-11-09).

    python tests/run.py mcp_tools_cache      (no network)

The owner's /health/loop showed `mcp_client _rpc < list_tools` 6 times in half an hour, up to 1.37 s: the hub keeps one
tool list per mode, plugin set, bot or coding session, and each one refreshed every 60 s by asking every server for its
whole list again and parsing it on the event loop. Now `SessionPool.list_tools` answers from the live session's last
list for `_TOOLS_TTL` seconds. Checks: discovery asks once, the health check and the Test button still ask for real,
and the cache is dropped when the answer is old, the process died, the config changed, the session was replaced, or
the server said its tools changed (a real stdio server sending notifications/tools/list_changed).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-toolscache-"))

import mcp_client  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def conn(i, **kw):
    c = {"id": f"c{i}", "connector_id": "x", "label": f"source {i}", "slug": f"s{i}",
         "namespace": f"ns{i}", "transport": "http", "url": f"http://127.0.0.1:9/{i}",
         "command": "", "args": [], "headers": {}, "env": {}, "internal": "", "secrets": {},
         "config": {}, "perm": "full", "deny_tools": [], "is_default": False,
         "auth": None, "connector": {}}
    c.update(kw)
    return c


class FakeSession:
    """Counts real tools/list requests; `live` and `tools_changed` stand for the process and the server's notice."""

    def __init__(self):
        self.lists = 0
        self.live = True
        self.tools_changed = False

    def alive(self):
        return self.live

    async def list_tools(self):
        self.lists += 1
        self.tools_changed = False
        return [{"name": f"tool_v{self.lists}", "description": "d", "inputSchema": {"type": "object"}}]

    async def call_tool(self, name, arguments):
        return "done"

    async def close(self):
        pass


made = []


def make_fake(spec):
    s = FakeSession()
    made.append(s)
    return s


real_make = mcp_client.SessionPool._make
mcp_client.SessionPool._make = staticmethod(make_fake)
pool = mcp_client.SessionPool()
mcp_client.pool = pool


async def fake_scenario():
    c = conn(1)
    spec = mcp_client._conn_spec(c)
    tools, _ = await mcp_client.discover_resolved([c])
    tools2, _ = await mcp_client.discover_resolved([c])
    await pool.list_tools(mcp_client._conn_spec(c))
    s = made[0]
    check("three discoveries in a row ask the server once", s.lists == 1, s.lists)
    check("and every one of them gets the tools", [t["name"] for t in tools] == ["tool_v1"]
          and [t["name"] for t in tools2] == ["tool_v1"], (tools, tools2))

    ent = pool._sessions[spec["key"]]
    ent["last"] = time.time() - 100
    await pool.list_tools(spec)
    check("a cache hit counts as use of the session (the idle sweep keeps it)", time.time() - ent["last"] < 5)

    await pool.list_tools(spec, fresh=True)
    check("fresh=True (health check, Test button) reaches the server", s.lists == 2, s.lists)

    ent["tools_at"] = time.time() - mcp_client._TOOLS_TTL - 1
    got = await pool.list_tools(spec)
    check("an answer older than _TOOLS_TTL is asked again", s.lists == 3 and got[0]["name"] == "tool_v3",
          (s.lists, got))

    s.tools_changed = True
    await pool.list_tools(spec)
    check("the server said its tools changed: asked again", s.lists == 4, s.lists)
    await pool.list_tools(spec)
    check("then cached again", s.lists == 4, s.lists)

    s.live = False
    await pool.list_tools(spec)
    check("a dead process is never answered from the cache", s.lists == 5, s.lists)
    s.live = True

    changed = mcp_client._conn_spec(conn(1, url="http://127.0.0.1:9/other"))
    await pool.list_tools(changed)
    check("a changed config gets a new session and a real tools/list", len(made) == 2 and made[1].lists == 1,
          (len(made), made[-1].lists))

    pool.invalidate(changed["key"])
    await pool.list_tools(changed)
    check("after the session is replaced the new one is asked", len(made) == 3 and made[2].lists == 1,
          (len(made), made[-1].lists))

    src = (ROOT / "server" / "connect_health.py").read_text(encoding="utf-8")
    hub = (ROOT / "server" / "mcp_hub.py").read_text(encoding="utf-8")
    check("the health check asks the server for real", "pool.list_tools(spec, fresh=True)" in src)
    check("the Test button asks the server for real", "mcp_client.pool.list_tools(spec, fresh=True)" in hub)


asyncio.run(fake_scenario())

# ---- a real stdio server that announces new tools ----
SERVER_SRC = r'''
import json, sys
version = 1
for line in sys.stdin:
    msg = json.loads(line or "{}")
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": True}},
                  "serverInfo": {"name": "changing", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": f"tool_v{version}", "description": "d", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        version += 1
        print(json.dumps({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}), flush=True)
        result = {"content": [{"type": "text", "text": "added a tool"}]}
    else:
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)
'''
helper = Path(tempfile.mkdtemp(prefix="javis-toolscache-srv-")) / "changing_server.py"
helper.write_text(SERVER_SRC, encoding="utf-8")
mcp_client.SessionPool._make = real_make
pool2 = mcp_client.SessionPool()
mcp_client.pool = pool2


async def stdio_scenario():
    c = conn(9, transport="stdio", url="", command=sys.executable, args=[str(helper)])
    spec = mcp_client._conn_spec(c)
    try:
        first = await pool2.list_tools(spec)
        again = await pool2.list_tools(spec)
        check("stdio: the second list comes from the cache", again is first, (first, again))
        await pool2.call_tool(spec, "add", {})
        after = await pool2.list_tools(spec)
        check("stdio: after notifications/tools/list_changed the new tool list is fetched",
              [t["name"] for t in after] == ["tool_v2"], after)
        cached = await pool2.list_tools(spec)
        check("stdio: and that new list is cached in turn", cached is after)
    finally:
        await pool2.close_all()


asyncio.run(stdio_scenario())

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails[:4]))
    raise SystemExit(1)
print("OK - test_mcp_tools_cache: all pass")
