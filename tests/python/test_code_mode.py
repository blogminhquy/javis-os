"""javis_code: a read-only script that chains connection reads and returns only what it prints.

    python tests/run.py code_mode

What must hold, whatever the script says:
  - a script reaches connection tools only through call(), and only declared reads get through;
  - every call goes through the tool's guarded route, and the raw result never reaches the model;
  - the script cannot read files, open sockets, start processes, import outside the allowlist or see keys;
  - calls, time and the answer are bounded; a broken script answers with its error, never a crash;
  - switched off or for a customer bot, the tool is absent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-code-mode-"))
os.environ["JAVIS_SECRET_FOR_TEST"] = "sk-should-never-leak"

import code_mode  # noqa: E402
import config  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


# ============================================================
# A fake shop: two read tools, one write tool
# ============================================================
_calls = []
ORDERS = {1: [{"id": 1, "customer": "c1", "total": 100}, {"id": 2, "customer": "c2", "total": 250}],
          2: [{"id": 3, "customer": "c1", "total": 50}], 3: []}
CUSTOMERS = {"c1": {"name": "An", "city": "Hanoi"}, "c2": {"name": "Binh", "city": "Hue"}}


class _Pool:
    async def call_tool(self, spec, tool, args):
        _calls.append((tool, dict(args or {})))
        if tool == "list_orders":
            n = int((args or {}).get("page") or 1)
            return json.dumps({"data": ORDERS.get(n, []), "page": n, "total_pages": 2})
        if tool == "get_customer":
            c = CUSTOMERS.get((args or {}).get("id"))
            return json.dumps(c) if c else "ERROR: customer not found"
        if tool == "get_big":
            return "x" * (code_mode.CALL_RESULT_MAX + 10)
        if tool == "create_order":
            return json.dumps({"created": True})
        return "OK"


CONN = {"id": "shop1", "connector_id": "custom-test-shop", "label": "Shop", "slug": "shop", "namespace": "shop",
        "perm": "full", "deny_tools": []}
TOOLS = [("list_orders", {"page": {"type": "integer"}}), ("get_customer", {"id": {"type": "string"}}),
         ("get_big", {}), ("create_order", {"name": {"type": "string"}})]


async def _fake_discover(conns, bo_qua=None):
    spec = {"transport": "http", "url": "https://shop.test/mcp", "headers": {}}
    tools, route = [], {}
    for name, props in TOOLS:
        fn = f"shop__{name}"
        route[fn] = {"spec": spec, "tool": name, "conn": dict(CONN)}
        tools.append({"fn": fn, "server": "shop", "name": name, "description": name.replace("_", " "),
                      "schema": {"type": "object", "properties": props}, "conn_id": "shop1",
                      "connector_id": CONN["connector_id"], "namespace": "shop", "label": "Shop"})
    return tools, route


_real_get = mcp_catalog.get
SHOP = {"id": "custom-test-shop", "name": "Shop", "tool_meta": {"read": ["list_*", "get_*"], "write": ["create_*"]}}
mcp_catalog.get = lambda cid: SHOP if cid == "custom-test-shop" else _real_get(cid)
mcp_store.resolved = lambda enabled_only=True: [dict(CONN, transport="http", url="https://shop.test/mcp", headers={}, env={})]
mcp_client.discover_resolved = _fake_discover
mcp_client.pool = _Pool()
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
_settings = {"mcp": {"lazy_tools": "off"}}
config.read_settings = lambda: json.loads(json.dumps(_settings))
mcp_hub._cache.clear()
BRAIN = tempfile.mkdtemp(prefix="code-brain-")

tools, route = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True))
names = {t["fn"] for t in tools}
check("an owner with a connected source gets javis_code", "javis_code" in names, sorted(names))


def code(src):
    _calls.clear()
    return run(mcp_client.call_route(route, "javis_code", {"code": src}))


# ============================================================
# 1. Chaining reads, only the printed result comes back
# ============================================================
out = code("""
by_city = {}
page = 1
while True:
    rows = call("shop__list_orders", {"page": page})["data"]
    if not rows:
        break
    for o in rows:
        c = call("shop__get_customer", {"id": o["customer"]})
        by_city[c["city"]] = by_city.get(c["city"], 0) + o["total"]
    page += 1
print(json.dumps(by_city, sort_keys=True))
""")
check("a script pages, looks up each item, joins and prints only the answer",
      '{"Hanoi": 150, "Hue": 250}' in out and "customer" not in out.split("\n", 2)[-1], out)
check("the header names the calls it made", "shop__list_orders x3" in out and "shop__get_customer x3" in out, out[:200])
check("every call really went through the connection", [c[0] for c in _calls].count("list_orders") == 3, _calls)

# ============================================================
# 2. Read only: writes and unknown tools are refused inside the script
# ============================================================
out = code("""
try:
    call("shop__create_order", {"name": "x"})
    print("WROTE")
except ToolError as e:
    print("refused:", e)
""")
check("a write tool is refused and never reaches the shop",
      "refused:" in out and "WROTE" not in out and not any(c[0] == "create_order" for c in _calls), out)
out = code('call("javis_code", {"code": "print(1)"})')
check("a script cannot start another script", "ERROR in the script" in out and "no tool named" in out, out)
out = code('call("shop__get_customer", {"id": "nobody"})')
check("a tool error raises ToolError with the tool's text", "ToolError" in out and "customer not found" in out, out)
out = code('call("shop__get_big")')
check("an oversized result is refused with advice, not passed whole", "more than a script may take" in out, out[:300])

# ============================================================
# 3. Isolation
# ============================================================
for label, src in [
        ("reading a file", 'print(open("/etc/passwd").read())'),
        ("importing os", "import os\nprint(os.listdir('/'))"),
        ("importing subprocess", "import subprocess\nprint(subprocess.run(['id']))"),
        ("importing socket", "import socket\nprint(socket.socket())"),
        ("escaping through object subclasses",
         "w = [c for c in ().__class__.__base__.__subclasses__() if c.__name__ == '_wrap_close']\n"
         "print(w[0].__init__.__globals__['system']('id') if w else 'NO_WRAP')"),
        ("escaping to the real open through a module",
         "import json\nprint(json.decoder.__builtins__['open']('/etc/hostname').read())")]:
    out = code(src)
    check(f"isolation: {label} is refused", "ERROR in the script" in out and "root:" not in out
          and "uid=" not in out, out[:400])
out = code("import json\nprint(sorted(k for k in json.decoder.__builtins__.get('__import__')('os').environ))")
check("isolation: the script sees no keys from the server's environment", "JAVIS_SECRET_FOR_TEST" not in out, out[:300])
out = code("import math, statistics, datetime, collections, re\n"
           "print(statistics.mean([1, 2, 3]), math.sqrt(16), collections.Counter('aab')['a'])")
check("the allowed standard modules work", "2 4.0 2" in out, out)

# ============================================================
# 4. Bounds and errors
# ============================================================
os.environ["JAVIS_CODE_MODE_MAX_CALLS"] = "3"
out = code("for i in range(10):\n    call('shop__list_orders', {'page': 1})")
check("calls are capped per run", "call limit reached (3 calls per run)" in out and len(_calls) == 3, out)
del os.environ["JAVIS_CODE_MODE_MAX_CALLS"]
os.environ["JAVIS_CODE_MODE_MAX_WALL_S"] = "5"
out = code("while True:\n    pass")
check("a script that never ends is stopped", out.startswith("ERROR:") and ("seconds" in out or "limit" in out), out)
del os.environ["JAVIS_CODE_MODE_MAX_WALL_S"]
out = code("x = 1 / 0")
check("a broken script answers with its own error line", "ZeroDivisionError" in out and "line 1" in out, out)
out = code("x = 1")
check("a script that prints nothing is told so", "printed nothing" in out, out)
out = code("print('row ' * 5000)")
check("a long answer is stored and shown as a view", len(out) < code_mode.ANSWER_CHARS + 2000 and "tr_" in out, len(out))
check("empty code is refused before any process starts", code("   ").startswith("ERROR:"))

# ============================================================
# 5. Who gets it
# ============================================================
tools_b, route_b = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True,
                                            for_bot=True))
check("a customer bot never gets javis_code", "javis_code" not in {t["fn"] for t in tools_b} and "javis_code" not in route_b)
_settings["mcp"]["code_mode"] = False
mcp_hub._cache.clear()
tools_off, _ = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True))
check("switched off in settings, it is absent", "javis_code" not in {t["fn"] for t in tools_off})
_settings["mcp"]["code_mode"] = True
_settings["mcp"]["lazy_tools"] = "on"
mcp_hub._cache.clear()
tools_l, route_l = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True))
search = next(t for t in tools_l if t["fn"] == mcp_hub._LAZY_SEARCH)
check("behind the tool search it costs one short line per turn",
      "javis_code" not in {t["fn"] for t in tools_l} and "javis_code(code)" in search["description"]
      and len(mcp_hub.CODE_MODE_HINT.format(run=mcp_hub._LAZY_RUN)) < 160)
out = run(mcp_client.call_route(route_l, mcp_hub._LAZY_RUN, {
    "name": "javis_code", "args": {"code": "print(len(call('shop__list_orders', {'page': 1})['data']))"}}))
check("through javis_run_tool it runs against the full route", out.rstrip().endswith("2"), out)

print()
print(f"{len(_fails)} failed" if _fails else "all passed")
raise SystemExit(1 if _fails else 0)
