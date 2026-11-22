"""Qualified tool calls (`namespace__tool`) in `javis_run_tool` must never silently route to another connector.

    python tests/python/test_lazy_run_namespace_guard.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ns-guard-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402

fails = []
CALLS = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:200]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


async def fake_call_route(route, name, args):
    entry = route[name]
    if "call" in entry:
        return await entry["call"](args)
    CALLS.append((name, dict(args)))
    return f"ran:{name}"


mcp_client.call_route = fake_call_route

pool = [
    {"fn": "shop-b__list_orders", "name": "list_orders", "namespace": "shop-b", "label": "Shop B",
     "description": "List orders for Shop B", "schema": {"type": "object", "properties": {}}},
    {"fn": "zalo-main__zalo_get_history", "name": "zalo_get_history", "namespace": "zalo-main", "label": "Zalo Main",
     "description": "Get Zalo history", "schema": {"type": "object", "properties": {}}},
]
full_route = {
    "shop-b__list_orders": {"tool": "list_orders", "spec": {"transport": "http", "url": "http://invalid/b"}},
    "zalo-main__zalo_get_history": {"tool": "zalo_get_history", "spec": {"transport": "http", "url": "http://invalid/z"}},
}
_tools, route = mcp_hub._lazy_tools_and_route([], {}, pool, full_route, top_k=10)
run_tool = route["javis_run_tool"]["call"]

# 1. Bare name with single match still auto-resolves
out = asyncio.run(run_tool({"name": "zalo_get_history", "args": {"limit": 5}}))
check("bare name with unique match still auto-routes", out == "ran:zalo-main__zalo_get_history", out)
check("bare name dispatched to zalo-main", CALLS == [("zalo-main__zalo_get_history", {"limit": 5})], CALLS)

# 2. Explicit qualified name for an unavailable account must NOT route to another account
CALLS.clear()
out2 = asyncio.run(run_tool({"name": "shop-a__list_orders", "args": {"day": "today"}}))
check("qualified missing name returns ERROR", out2.startswith("ERROR:"), out2)
check("qualified missing name suggests available copy", "shop-b__list_orders" in out2, out2)
check("qualified missing name never calls other connector", CALLS == [], CALLS)

# 3. Exact qualified name still runs normally
out3 = asyncio.run(run_tool({"name": "shop-b__list_orders", "args": {"day": "today"}}))
check("exact qualified name runs normally", out3 == "ran:shop-b__list_orders", out3)
check("exact qualified name dispatched once", CALLS == [("shop-b__list_orders", {"day": "today"})], CALLS)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
