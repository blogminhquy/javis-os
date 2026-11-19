"""A tool hidden by the hub's lazy tier still answers when the model calls it by name (2026-11-19).

Real case: with lazy on, `javis_team` sat behind `javis_search_tools`. The prompt tells the model to use `javis_team`,
so it called it by name, and the hub answered "ERROR: tool 'javis_team' không tồn tại". Asked why, the model blamed
having too many tools. The tool was there the whole time.

    python tests/run.py lazy_direct_call      (no network)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-lazy-direct-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def run(c):
    return asyncio.run(c)


VAULT = tempfile.mkdtemp(prefix="javis-lazy-direct-vault-")
tools, route = run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True, force_lazy=True))
shown = {t["fn"] for t in tools}
check("lazy on: javis_team is hidden behind the search tool", "javis_team" not in shown and mcp_hub._LAZY_RUN in shown)
check("lazy on: javis_team is not in the visible route", "javis_team" not in route)

out = str(run(mcp_client.call_route(route, "javis_team", {"op": "list"})))
check("calling javis_team by name reaches the tool, not 'không tồn tại'", "không tồn tại" not in out, out[:200])

out = str(run(mcp_client.call_route(route, "khong_co_tool_nay", {})))
check("a name that really is missing still errors", out.startswith("ERROR"), out[:200])
check("...and points the model at the search tool", mcp_hub._LAZY_SEARCH in out, out[:200])

out = str(run(mcp_client.call_route(route, mcp_hub._LAZY_RUN, {"name": mcp_hub._LAZY_RUN})))
check("javis_run_tool cannot call itself through the fallback", out.startswith("ERROR"), out[:200])

# A customer-facing bot never reaches an owner-only tool, by name or through the lazy tier.
_t, route_b = run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True, force_lazy=True, for_bot=True))
out = str(run(mcp_client.call_route(route_b, "javis_team", {"op": "list"})))
check("a bot calling javis_team by name is still refused", out.startswith("ERROR"), out[:200])

# A workflow with an allowlist gets no lazy tier, so a name outside the list has no back door.
_t, route_w = run(mcp_hub.discover_all("full", vault_root=VAULT, force_refresh=True, force_lazy=True,
                                       tool_allowlist=["javis_read_file"]))
out = str(run(mcp_client.call_route(route_w, "javis_team", {"op": "list"})))
check("an allowlisted workflow cannot reach a tool outside its list", out.startswith("ERROR"), out[:200])

# The menu names what the javis group holds, so a model looking for team chats knows to search there.
menu = mcp_hub._connector_menu([{"fn": "javis_team", "server": "javis", "namespace": "javis"}])
check("the lazy menu says the javis group holds team chats", "nhóm chat" in menu, menu)

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
