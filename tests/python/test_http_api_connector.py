"""Custom API connector: a REST API with an API key, called by every engine through the hub.

    python tests/run.py http_api_connector     (no network: httpx.MockTransport)

Owner, 15/11/2026: "many people need to connect an advanced API key into Javis OS to wire other tools". Many tools
(POS, CRM, shipping, e-invoices) publish a REST API and a key but no MCP server. Before this the only ways were a
Python plugin (no place for the key, off by default) or the terminal (the key lands in the chat with the model).

The rules this file keeps:
- the key never reaches the model: it is added server side and scrubbed from every result;
- the key only goes to the host of the base URL (paths, absolute URLs and redirects are checked);
- GET/HEAD/OPTIONS are reads, every other method needs Full access (hub `call_rules`), and the tricks that turn a
  GET into a write (a body, a method-override header) are refused.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import sys

import httpx

import http_api_mcp as api
import mcp_catalog
import mcp_client

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


KEY = "sk-live-9f8e7d6c5b4a3210"
seen = []


def handler(request: httpx.Request):
    seen.append(request)
    path = request.url.path
    if path == "/v1/orders":
        return httpx.Response(200, json={"orders": [{"id": 1}], "echo_key": KEY})
    if path == "/v1/hop":
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})
    if path == "/v1/hop-local":
        return httpx.Response(302, headers={"location": "/v1/orders"})
    if path == "/v1/big":
        return httpx.Response(200, text="x" * 200_000, headers={"content-type": "text/plain"})
    if path == "/v1/bin":
        return httpx.Response(200, content=b"\x89PNG\r\n" + b"\x00" * 50, headers={"content-type": "image/png"})
    if path == "/v1/denied":
        return httpx.Response(401, json={"error": "invalid key"})
    return httpx.Response(200, json={"method": request.method, "path": path})


api._transport = httpx.MockTransport(handler)


def spec(**fields):
    base = {"base_url": "https://api.shop.example/v1", "api_key": KEY}
    base.update(fields)
    return {"secrets": base, "label": "Shop API"}


def run(args, s=None):
    return asyncio.run(api.call("api_request", args, s or spec()))


def last():
    return seen[-1]


# ---- 1. the key is added server side, Bearer by default ----
out = run({"method": "GET", "path": "/orders"})
res = json.loads(out)
check("GET returns status and parsed JSON", res.get("status") == 200 and res["body"]["orders"] == [{"id": 1}], out)
check("default auth is Authorization: Bearer <key>", last().headers.get("authorization") == "Bearer " + KEY)
check("path joins under the base URL", str(last().url) == "https://api.shop.example/v1/orders", str(last().url))
check("the key echoed by the API is scrubbed from the result", KEY not in out, out)
check("result names the host (used as the connection label)", res.get("host") == "api.shop.example")

# ---- 2. other ways to send the key ----
run({"path": "orders"}, spec(auth_style="X-API-Key: {key}"))
check("custom header with {key}", last().headers.get("x-api-key") == KEY and "authorization" not in last().headers)
run({"path": "orders"}, spec(auth_style="X-Token"))
check("bare header name sends the raw key", last().headers.get("x-token") == KEY)
run({"path": "orders", "query": {"api_key": "model-guess", "page": 2}}, spec(auth_style="?api_key={key}"))
check("query style puts the key in the query, overriding the model's value",
      last().url.params.get("api_key") == KEY and last().url.params.get("page") == "2", str(last().url))
out = run({"path": "orders"}, spec(auth_style="?api_key={key}"))
check("query key is scrubbed from the reported URL too", KEY not in out, out)
run({"path": "orders"}, spec(auth_style="Authorization: Basic {key}", api_key="ck_user:cs_secret"))
check("Basic with user:secret is base64-encoded",
      last().headers.get("authorization") == "Basic Y2tfdXNlcjpjc19zZWNyZXQ=", last().headers.get("authorization"))
out = run({"path": "orders"}, spec(extra_headers="X-Shop-Id: 4242\n# a comment\n\nX-Secret: hush-hush-77"))
check("extra headers are sent", last().headers.get("x-shop-id") == "4242" and last().headers.get("x-secret") == "hush-hush-77")
check("extra header values are scrubbed too", "hush-hush-77" not in out)

# ---- 3. the key never leaves the base host ----
n = len(seen)
out = run({"path": "https://evil.example/collect"})
check("absolute URL on another host is refused, nothing sent", out.startswith("ERROR") and len(seen) == n, out)
run({"path": "https://api.shop.example/v1/orders"})
check("absolute URL on the same host is allowed", last().url.host == "api.shop.example" and len(seen) == n + 1)
n = len(seen)
out = run({"path": "/hop"})
check("redirect to another host is not followed", len(seen) == n + 1 and json.loads(out)["status"] == 302, out)
check("the report keeps the off-host Location so the model can tell", "evil.example" in out)
n = len(seen)
out = run({"path": "/hop-local"})
check("same-host redirect is followed with the key", len(seen) == n + 2 and json.loads(out)["status"] == 200, out)
n = len(seen)
out = run({"path": "//evil.example/x"})
check("scheme-relative path cannot switch host", out.startswith("ERROR") or seen[-1].url.host == "api.shop.example", out)

# ---- 4. model headers cannot override auth or smuggle a write ----
run({"path": "orders", "headers": {"Authorization": "Bearer stolen", "X-Request-Id": "r1"}})
check("model cannot override the auth header", last().headers.get("authorization") == "Bearer " + KEY)
check("ordinary model headers pass", last().headers.get("x-request-id") == "r1")
n = len(seen)
out = run({"method": "GET", "path": "orders", "headers": {"X-HTTP-Method-Override": "DELETE"}})
check("method-override header is refused", out.startswith("ERROR") and len(seen) == n, out)
out = run({"method": "GET", "path": "orders", "body": {"a": 1}})
check("GET with a body is refused", out.startswith("ERROR") and len(seen) == n, out)
out = run({"method": "TRACE", "path": "orders"})
check("unknown method is refused", out.startswith("ERROR") and len(seen) == n, out)
out = run({"path": "orders", "headers": {"X-Bad": "a\r\nInjected: 1"}})
check("header with a line break is refused", out.startswith("ERROR") and len(seen) == n, out)

# ---- 5. bodies ----
run({"method": "POST", "path": "orders", "body": {"sku": "A1", "qty": 2}})
check("object body goes as JSON", last().method == "POST" and json.loads(last().content) == {"sku": "A1", "qty": 2}
      and last().headers.get("content-type", "").startswith("application/json"))
run({"method": "POST", "path": "orders", "body": {"amount": 100, "currency": "vnd"}, "body_format": "form"})
check("form body is urlencoded", last().content == b"amount=100&currency=vnd"
      and "x-www-form-urlencoded" in last().headers.get("content-type", ""))

# ---- 6. results stay small and honest ----
out = run({"path": "big"})
check("large body is clipped", len(out) < 40_000 and "truncated" in out.lower(), len(out))
out = run({"path": "bin"})
check("binary body is described, not dumped", "image/png" in out and "\\u0000" not in out and "PNG" not in out, out[:200])
out = run({"path": "denied"})
check("HTTP 401 is a result with its status, not a crash", json.loads(out)["status"] == 401, out)

# ---- 7. base URL rules ----
for bad in ("", "ftp://x.example", "not a url", "http://api.public-shop.example/v1"):
    out = run({"path": "orders"}, spec(base_url=bad))
    check(f"base URL refused: {bad!r}", out.startswith("ERROR"), out)
n = len(seen)
run({"path": "orders"}, spec(base_url="http://192.168.1.20:8080/api"))
check("plain http is allowed on a private address", len(seen) == n + 1 and last().url.host == "192.168.1.20")
run({"path": "orders"}, spec(base_url="http://localhost:3000"))
check("plain http is allowed on localhost", last().url.host == "localhost")
out = run({"path": "orders"}, spec(auth_style="Authorization: Bearer"))
check("auth style with ':' but no {key} is refused", out.startswith("ERROR"), out)
out = asyncio.run(api.call("api_request", {"path": "orders"}, {"secrets": {"base_url": "https://a.example"}}))
check("missing key is refused", out.startswith("ERROR"), out)

# ---- 8. what the model sees ----
tools = asyncio.run(api.list_tools(spec(docs_url="https://docs.shop.example", notes="Orders live under /orders.")))
check("one tool, api_request", [t["name"] for t in tools] == ["api_request"])
desc = tools[0]["description"]
check("description names the base URL, docs and the owner's notes",
      "https://api.shop.example/v1" in desc and "https://docs.shop.example" in desc and "/orders" in desc, desc)
check("description never holds the key", KEY not in json.dumps(tools))
check("method is an enum in the schema", "GET" in tools[0]["inputSchema"]["properties"]["method"]["enum"])
out = asyncio.run(api.call("other_tool", {}, spec()))
check("an unknown tool name is an error", out.startswith("ERROR"))

# ---- 9. wiring: catalog entry, permissions, dial ----
con = mcp_catalog.get("http-api")
check("catalog has the http-api connector", bool(con) and con.get("transport") == "internal"
      and con.get("internal") == "http_api", con)
check("default permission is read-only", (con or {}).get("default_perm") == "readonly")
check("hub can dial it", mcp_client.co_server_de_dial({"transport": "internal", "internal": "http_api"}))
cls = lambda a: mcp_catalog.classify(con, "api_request", a)  # noqa: E731
check("GET is a read", cls({"method": "GET", "path": "x"}) == "read")
check("no method means GET, a read", cls({"path": "x"}) == "read")
check("lower-case get is a read", cls({"method": "get"}) == "read")
for m in ("POST", "PUT", "PATCH", "DELETE", "post", "weird"):
    check(f"{m} needs Full access", cls({"method": m}) == "danger")
check("listed at Read-only (it has reads)", cls(None) == "read")
ok, _ = mcp_catalog.allowed(con, "readonly", "full", "api_request", {"method": "GET"})
check("read-only connection may GET", ok)
ok, _ = mcp_catalog.allowed(con, "readonly", "full", "api_request", {"method": "POST"})
check("read-only connection may not POST", not ok)
ok, _ = mcp_catalog.allowed(con, "safe", "full", "api_request", {"method": "DELETE"})
check("draft-level connection may not DELETE", not ok)
ok, _ = mcp_catalog.allowed(con, "full", "full", "api_request", {"method": "DELETE"})
check("full connection may DELETE", ok)
ok, _ = mcp_catalog.allowed(con, "full", "suggest", "api_request", {"method": "POST"})
check("a suggest-mode loop may not POST even on a full connection", not ok)

print()
if fails:
    print(f"FAILED {len(fails)}: " + "; ".join(fails))
    sys.exit(1)
print("OK - test_http_api_connector: all pass")
