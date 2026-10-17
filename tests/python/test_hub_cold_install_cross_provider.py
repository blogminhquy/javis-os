"""A connector on its first start must survive the hub being asked by every engine at once.

    python tests/run.py hub_cold_install_cross_provider      (no network; spawns a small Python server)

Every brain reaches MCP connectors through the same hub, by different doors:
  - Claude Code and Codex, Grok, Antigravity: HTTP POST /hub/mcp with a Bearer token, each with
    its own X-Javis-Mode (chat turns "full", a Codex background job its own level, e.g. "suggest");
  - API engines (OpenRouter, Anthropic API...): in-process `mcp_hub.discover_all(mode)`.
Each door has its own tool-list cache entry, so right after a restart they all trigger discovery
of the same cold source, through ONE pooled session. On 2026-10-13 that is how an `npx -y`
connector was killed in the middle of its first install (see test_mcp_cold_install_not_killed).
A connection edit on the Connections page (`invalidate_cache`) used to close it as well.

Locked here, with the real hub handler and a real stdio process: while the source is still
starting, every engine gets a working tool list without it and nothing kills it; once it is up,
every engine can call it; and it was spawned exactly once.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import glob
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-hub-cold-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_SESSIONS_DB"] = str(_TMP / "conversations.db")
os.environ["BRAINS_DIR"] = str(_TMP / "brains")
os.environ["HOME"] = str(_TMP / "home")
for _d in ("state", "brains/Brain Default/Javis", "home"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)
os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.4"

import httpx  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Route  # noqa: E402

import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402

HELPER = str(Path(__file__).resolve().parent / "_slow_start_mcp_server.py")
MARKER = _TMP / "marker"
MARKER.mkdir()
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


CONN = {"id": "slowsrc", "connector_id": "custom", "label": "slow source", "slug": "slowsrc",
        "namespace": "slowsrc", "transport": "stdio", "url": "", "command": sys.executable,
        "args": [HELPER, "--delay", "8.0", "--marker", str(MARKER)], "headers": {}, "env": {},
        "internal": "", "secrets": {}, "config": {}, "perm": "readonly", "deny_tools": [],
        "is_default": True, "enabled": True, "auth": None, "connector": {}}
mcp_store.resolved = lambda enabled_only=True, *a, **k: [dict(CONN)]
mcp_store.list_connections = lambda *a, **k: [dict(CONN)]

async def _hub_endpoint(request):
    return await mcp_hub.handle_http(request)


app = Starlette(routes=[Route("/hub/mcp", _hub_endpoint, methods=["POST"])])
TOKEN = mcp_hub.hub_token()
# The headers each engine really sends (mcp_hub config writers, aux_engine).
PROVIDERS = {
    "claude-code chat": {"X-Javis-Mode": "full", "X-Javis-Engine": "claude"},
    "codex background job": {"X-Javis-Mode": "suggest"},
    "grok / antigravity job": {"X-Javis-Mode": "auto"},
}


async def rpc(client, headers, method, params=None, mid=1):
    body = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        body["params"] = params
    r = await client.post("/hub/mcp", json=body, headers={"Authorization": f"Bearer {TOKEN}", **headers})
    return r.status_code, (r.json() if r.content else None)


def text_of(res):
    """Tool result text without the brain note the hub appends after a blank line."""
    content = ((res or {}).get("result") or {}).get("content") or []
    return "".join(c.get("text", "") for c in content if isinstance(c, dict)).split("\n\n(")[0]


async def echo_over_http(client, headers):
    """What a model does: find the source's tool (directly or through the lazy search) and call it."""
    status, res = await rpc(client, headers, "tools/list", mid=2)
    names = [t["name"] for t in ((res or {}).get("result") or {}).get("tools", [])]
    direct = [n for n in names if n.endswith("__echo")]
    if direct:
        _, out = await rpc(client, headers, "tools/call", {"name": direct[0], "arguments": {"text": "hi"}}, mid=3)
        return status, text_of(out)
    _, found = await rpc(client, headers, "tools/call",
                         {"name": "javis_search_tools", "arguments": {"query": "echo slow source"}}, mid=3)
    try:
        found_tools = json.loads(text_of(found).split("\n\n(")[0]).get("tools", [])
    except ValueError:
        found_tools = []
    fns = [t["name"] for t in found_tools if t.get("name", "").endswith("__echo")]
    if not fns:
        return status, ""
    _, out = await rpc(client, headers, "tools/call",
                       {"name": "javis_run_tool", "arguments": {"name": fns[0], "args": {"text": "hi"}}}, mid=4)
    return status, text_of(out)


async def api_engine_has_echo(mode):
    tools, route = await mcp_hub.discover_all(mode, include_plugins=False)
    fns = [fn for fn in route if fn.endswith("__echo")]
    return bool(fns), fns


def spawns():
    return sorted(glob.glob(str(MARKER / "started.*")), key=os.path.getmtime)


def pid_of(path):
    return int(path.rsplit(".", 1)[1])


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:      # a zombie still answers kill(0)
        return Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://hub.test") as client:
        # --- Restart: every engine connects while the source is still downloading ---
        for headers in PROVIDERS.values():
            await rpc(client, headers, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                       "clientInfo": {"name": "t", "version": "1"}})
        first = await asyncio.gather(*(rpc(client, h, "tools/list", mid=2) for h in PROVIDERS.values()),
                                     api_engine_has_echo("full"))
        http_ok = all(s == 200 and (r or {}).get("result") is not None for s, r in first[:-1])
        check("cold start: every HTTP engine still gets a tool list (no error, no hang)", http_ok,
              [s for s, _ in first[:-1]])
        check("cold start: the API engine does not see the source yet", first[-1][0] is False, first[-1])
        await asyncio.sleep(0.5)             # the pool closes sessions in the background
        check("cold start: the source process is alive after every engine gave up on it",
              len(spawns()) == 1 and alive(pid_of(spawns()[0])), spawns())
        # A connection edit elsewhere while the source is still downloading (Connections page,
        # pack install): the download must survive it. Closing it once its handshake is over is
        # intended (the edit may concern it) and covered by test_mcp_cold_install_not_killed.
        # Read with getattr so this file still runs (and turns red) on a tree without the fix.
        starting = getattr(mcp_client.pool, "is_starting_key", lambda key: False)
        # Precondition, not a result: the edit must land while the source is still downloading.
        # The 8 s download leaves room for a slow, loaded CI box; if even that ran out, say so.
        check("precondition: the source is still downloading when the connection edit lands",
              not glob.glob(str(MARKER / "ready.*")), glob.glob(str(MARKER / "ready.*")))
        mcp_hub.invalidate_cache()
        await asyncio.sleep(0.5)
        check("a connection edit (invalidate_cache) does not kill the downloading source",
              len(spawns()) == 1 and alive(pid_of(spawns()[0])) and starting("slowsrc"), spawns())
        while starting("slowsrc"):
            await asyncio.sleep(0.1)
        check("the source that survived the edit finished its download",
              len(glob.glob(str(MARKER / "ready.*"))) == 1, glob.glob(str(MARKER / "ready.*")))
        before_up = len(spawns())

        # --- The download is over: each engine's own cache entry expires, they ask again ---
        deadline = time.time() + 30
        results = {}
        while time.time() < deadline:
            mcp_hub._cache.clear()           # the cache TTL running out, without closing sessions
            results = {name: await echo_over_http(client, h) for name, h in PROVIDERS.items()}
            results["api engine (in-process)"] = await api_engine_has_echo("auto")
            if all((v[1] == "echo: hi") if "api" not in k else v[0] for k, v in results.items()):
                break
            await asyncio.sleep(0.3)
        for name, h in PROVIDERS.items():
            check(f"{name}: calls the source once it is up", results.get(name, (0, ""))[1] == "echo: hi",
                  results.get(name))
        check("api engine (in-process): sees the source once it is up",
              results.get("api engine (in-process)", (False,))[0] is True, results.get("api engine (in-process)"))
        check("all engines together started it once more at most (the restart the edit asked for)",
              len(spawns()) == before_up + (1 if before_up == 1 else 0) and len(spawns()) <= 2, spawns())
    await mcp_client.pool.close_all()


asyncio.run(main())
os.environ.pop("JAVIS_MCP_DISCOVER_TIMEOUT", None)

print()
if fails:
    print(f"RED {len(fails)}: " + "; ".join(fails[:4]))
    raise SystemExit(1)
print("All green.")
