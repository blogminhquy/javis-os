"""General `owner_only` and `owner_only_tools` turn scope on MCP connections (`mcp_store` + `mcp_hub`).

    python tests/python/test_mcp_owner_only_scope.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-owner-scope-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import plugins_host  # noqa: E402
import turn_context  # noqa: E402

fails = []
DENIED = "ERROR: owner_scope_required"
SECRET = "secret-filter-value-9a4b"
CALLS = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:250]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(awaitable):
    return asyncio.run(awaitable)


# 1. mcp_store persistence round-trip via add_server / update_server / list_connections / resolved
sid = mcp_store.add_server({
    "name": "ERP Internal",
    "transport": "http",
    "url": "http://127.0.0.1:9999/mcp",
    "perm": "readonly",
    "owner_only": False,
    "owner_only_tools": ["read_crm", "list_ledger", "read_crm", "  "],
})
listed = next((x for x in mcp_store.list_connections() if x["id"] == sid), None)
check("add_server persists deduplicated owner_only_tools",
      listed is not None and listed["owner_only"] is False and listed["owner_only_tools"] == ["read_crm", "list_ledger"],
      listed)
res_conn = next((x for x in mcp_store.resolved(enabled_only=True) if x["id"] == sid), None)
check("resolved exposes owner_only_tools",
      res_conn is not None and res_conn["owner_only_tools"] == ["read_crm", "list_ledger"], res_conn)

check("update_server toggles owner_only",
      mcp_store.update_server(sid, {"owner_only": True, "owner_only_tools": ["only_one"]}))
listed2 = next((x for x in mcp_store.list_connections() if x["id"] == sid), None)
check("updated fields stored cleanly",
      listed2["owner_only"] is True and listed2["owner_only_tools"] == ["only_one"], listed2)
mcp_store.delete_server(sid)

# 2. Discovery cache, lazy/direct visibility, and call-time fail-closed guard
PARTIAL = {"id": "p1", "connector_id": "custom", "label": "partial", "namespace": "erp", "perm": "readonly",
           "transport": "http", "url": "http://invalid/1", "headers": {}, "env": {}, "deny_tools": [],
           "owner_only": False, "owner_only_tools": ["read_crm", "list_ledger"]}
WHOLE = {"id": "w1", "connector_id": "custom", "label": "whole", "namespace": "vault-db", "perm": "readonly",
         "transport": "http", "url": "http://invalid/2", "headers": {}, "env": {}, "deny_tools": [],
         "owner_only": True, "owner_only_tools": []}
PUBLIC = {"id": "o1", "connector_id": "custom", "label": "public", "namespace": "pub", "perm": "readonly",
          "transport": "http", "url": "http://invalid/3", "headers": {}, "env": {}, "deny_tools": [],
          "owner_only": False, "owner_only_tools": []}

SETTINGS = {"mcp": {"lazy_tools": "on", "lazy_top_k": 20}}


async def fake_discover(_conns, bo_qua=None):
    tools, route = [], {}
    for conn, names in ((PARTIAL, ("read_crm", "list_ledger", "public_ping")),
                        (WHOLE, ("secret_dump",)),
                        (PUBLIC, ("read_crm",))):
        spec = {"transport": "http", "url": conn["url"], "headers": {}}
        for name in names:
            fn = f"{conn['namespace']}__{name}"
            tools.append({"fn": fn, "server": conn["namespace"], "name": name, "description": name,
                          "schema": {"type": "object", "properties": {}}, "conn_id": conn["id"],
                          "connector_id": "custom", "namespace": conn["namespace"], "label": conn["label"]})
            route[fn] = {"spec": spec, "tool": name, "conn": dict(conn)}
    return tools, route


async def fake_call_route(route, name, args):
    CALLS.append((name, dict(args)))
    return '{"ok":true}'


mcp_store.resolved = lambda enabled_only=True: [PARTIAL, WHOLE, PUBLIC]
mcp_client.discover_resolved = fake_discover
mcp_client.call_route = fake_call_route
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
plugins_host.has_tool_hooks = lambda *_: False
plugins_host.plugin_tools = lambda *_: ([], {})
config.read_settings = lambda: SETTINGS

RESTRICTED = ("erp__read_crm", "erp__list_ledger", "vault-db__secret_dump")
ALLOWED_NON_OWNER = ("erp__public_ping", "pub__read_crm")


def disc(turn, for_bot=False, lazy_on=True, force_refresh=False):
    SETTINGS["mcp"]["lazy_tools"] = "on" if lazy_on else "off"
    tok = turn_context.bind(turn)
    try:
        return run(mcp_hub.discover_all("suggest", include_plugins=False, force_lazy=lazy_on,
                                        for_bot=for_bot, force_refresh=force_refresh))
    finally:
        turn_context.reset(tok)


def search(route, q):
    return run(route["javis_search_tools"]["call"]({"query": q}))


def audit_records():
    p = mcp_hub._AUDIT_PATH
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


OWNER = turn_context.make("dashboard", la_chu=True)
DENIED_TURNS = (
    ("no turn", None, False),
    ("bot route flag", OWNER, True),
    ("turn with bot_id", dict(OWNER, bot_id="bot_1"), False),
    ("team background turn", turn_context.make("team", chat_id="tm_1"), False),
    ("kanban background turn", turn_context.make("tasks", la_chu=False, job="kanban:7"), False),
)

# Owner sees and calls every tool
mcp_hub.invalidate_cache()
tools_o, route_o = disc(OWNER, lazy_on=False, force_refresh=True)
check("owner direct list includes restricted + public tools",
      all(fn in route_o for fn in RESTRICTED + ALLOWED_NON_OWNER), sorted(route_o))
tok = turn_context.bind(OWNER)
try:
    check("owner calls restricted tools ok",
          all(run(route_o[fn]["call"]({"q": "x"})) == '{"ok":true}' for fn in RESTRICTED))
finally:
    turn_context.reset(tok)

# Non-owner turns never see restricted tools, even sharing cache order both ways
for label, turn, for_bot in DENIED_TURNS:
    tools_d, route_d = disc(turn, for_bot=for_bot, lazy_on=True)
    check(f"{label} (cached after owner): restricted absent from route",
          not any(fn in route_d for fn in RESTRICTED), sorted(route_d))
    tok = turn_context.bind(turn)
    try:
        for fn in RESTRICTED:
            short = fn.split("__", 1)[1]
            check(f"{label}: lazy search hides {fn}", fn not in search(route_d, short))
        check(f"{label}: unrestricted tools stay visible",
              all(fn.split("__", 1)[1] in search(route_d, fn.split("__", 1)[1]) for fn in ALLOWED_NON_OWNER))
    finally:
        turn_context.reset(tok)

# Reverse order: denied turn warms cache first, owner must still see restricted tools
mcp_hub.invalidate_cache()
_td, _rd = disc(DENIED_TURNS[0][1], for_bot=False, lazy_on=False, force_refresh=True)
_to, route_o2 = disc(OWNER, lazy_on=False, force_refresh=False)
check("denied-first cache does not hide tools from subsequent owner turn",
      all(fn in route_o2 for fn in RESTRICTED), sorted(route_o2))

# Stale owner route fails closed at call time with no backend invocation and no arg leak in audit
CALLS.clear()
n_before = len(audit_records())
for turn in (None, dict(OWNER, bot_id="bot_1"), turn_context.make("team", chat_id="tm_2")):
    tok = turn_context.bind(turn)
    try:
        outs = [run(route_o[fn]["call"]({"filter": SECRET})) for fn in RESTRICTED]
        check("stale route refuses closed", outs == [DENIED] * len(RESTRICTED), outs)
    finally:
        turn_context.reset(tok)
check("stale route never reaches backend", CALLS == [], CALLS)
recs = audit_records()[n_before:]
check("audit logs refusals without leaking secret args",
      len(recs) == 3 * len(RESTRICTED)
      and all(r.get("err") == mcp_hub.OWNER_SCOPE_DENIED and r.get("ok") is False for r in recs)
      and SECRET not in json.dumps(recs),
      recs[:2])

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
