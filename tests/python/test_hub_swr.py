"""0.382.0: the hub serves a complete tool list past its 60 s while it refreshes in the background (mcp_hub).

A chat turn that opens an engine after a pause used to wait for every MCP source to be dialled again. Now a complete
list up to _CACHE_STALE_MAX old comes back at once and one background refresh replaces it; a partial list, a changed
connection store or invalidate_cache() keep the old synchronous rule.

Run:
    python tests/run.py hub_swr
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-hub-swr-")
BRAIN = Path(tempfile.mkdtemp(prefix="javis-hub-swr-brain-"))

import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or detail is None else f"  -> {detail!r}"))
    if not cond:
        fails.append(name)


calls = []
partial = {"on": False}


async def fake_discover(conns, bo_qua=None):
    calls.append(1)
    if partial["on"] and bo_qua is not None:
        bo_qua.add("dead-source")
    return [], {}

mcp_client.discover_resolved = fake_discover
mcp_store.resolved = lambda enabled_only=True: []


def age_all(seconds):
    for ent in mcp_hub._cache.values():
        ent["ts"] -= seconds


async def main():
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    check("first call dials the sources", len(calls) == 1)
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    check("inside 60 s: cached, no dial", len(calls) == 1)
    age_all(120)
    tools, route = await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    check("past 60 s: the stored list comes back at once, before any dial", len(calls) == 1 and isinstance(tools, list))
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    for _ in range(50):
        await asyncio.sleep(0.01)
    check("one background refresh, even when asked twice meanwhile", len(calls) == 2 and not mcp_hub._refreshing)
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    check("the refreshed list is fresh again", len(calls) == 2)
    age_all(mcp_hub._CACHE_STALE_MAX + 5)
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    check("too old to serve: dials synchronously, as before", len(calls) == 3)
    mcp_hub.invalidate_cache()
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    check("invalidate_cache: dials at once", len(calls) == 4)
    partial["on"] = True
    mcp_hub.invalidate_cache()
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    age_all(30)
    before = len(calls)
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN))
    check("a partial list keeps the short synchronous rule", len(calls) == before + 1)
    partial["on"] = False
    age_all(120)
    before = len(calls)
    await mcp_hub.discover_all("suggest", vault_root=str(BRAIN), force_refresh=True)
    check("force_refresh always dials", len(calls) == before + 1)

asyncio.run(main())
check("no long dashes in mcp_hub.py", not any(c in (SERVER / "mcp_hub.py").read_text(encoding="utf-8") for c in "–—"))

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
