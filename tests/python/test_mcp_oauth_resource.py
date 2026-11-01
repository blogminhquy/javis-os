"""Custom MCP OAuth names the canonical resource and reports a shared DCR client honestly (#939).

    python tests/run.py mcp_oauth_resource      (no network)

Reported with the official Spacemail MCP: the server is https://mcp.spacemail.com/mcp but its protected-resource metadata
(RFC 9728) declares resource https://mcp.spacemail.com/. Javis sent the transport URL as the RFC 8707 `resource`, which the
authorization server answers with invalid_target. Its DCR also hands back a shared client ("starlight.mcp") whose callback
allowlist does not hold Javis's callback, so the provider's sign-in page fails and never comes back to Javis.

This file guards:
  1. canonical_resource takes the declared resource only when it covers the MCP URL (same origin, path prefix).
  2. _discover keeps the declared resource; start_auth sends it, and the code exchange and refresh send the same value.
  3. A DCR answer whose redirect_uris lack Javis's callback stops before the sign-in page, with an honest error.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import urllib.parse
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-oauth-resource-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import oauth_mcp  # noqa: E402
import mcp_store  # noqa: E402
import secrets_store  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


MCP = "https://mcp.spacemail.com/mcp"
REDIR = "https://javis.example/connect/oauth/callback"

# ---- 1. canonical_resource
cr = oauth_mcp.canonical_resource
check("the declared origin resource covers /mcp", cr(MCP, "https://mcp.spacemail.com/") == "https://mcp.spacemail.com/")
check("a declared resource without a trailing slash still covers /mcp",
      cr(MCP, "https://mcp.spacemail.com") == "https://mcp.spacemail.com")
check("a declared resource equal to the URL is kept", cr(MCP, MCP) == MCP)
check("CANARY: no declared resource falls back to the URL", cr(MCP, "") == MCP)
check("another host is refused (the grant must not name another site)", cr(MCP, "https://evil.example/") == MCP)
check("another scheme is refused", cr(MCP, "http://mcp.spacemail.com/") == MCP)
check("a sibling path is refused", cr(MCP, "https://mcp.spacemail.com/other") == MCP)
check("a path that only shares a prefix is refused", cr("https://h.example/mcpx", "https://h.example/mcp") == "https://h.example/mcpx")
check("a fragment is dropped", cr(MCP, "https://mcp.spacemail.com/#x") == "https://mcp.spacemail.com/")
check("host case does not matter", cr(MCP, "https://MCP.Spacemail.com/") == "https://MCP.Spacemail.com/")


# ---- fake network
class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}

    def json(self):
        return self._body


SENT = []


def fake_client(dcr_answer):
    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, data=None, headers=None, **k):
            SENT.append(("POST", url, json, data))
            if url == MCP:
                return Resp(401, headers={"www-authenticate":
                            'Bearer resource_metadata="https://mcp.spacemail.com/.well-known/oauth-protected-resource"'})
            if url.endswith("/register"):
                return Resp(201, dcr_answer)
            if url.endswith("/token"):
                return Resp(200, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})
            return Resp(404)

        async def get(self, url, **k):
            SENT.append(("GET", url, None, None))
            if url == "https://mcp.spacemail.com/.well-known/oauth-protected-resource":
                return Resp(200, {"resource": "https://mcp.spacemail.com/",
                                  "authorization_servers": ["https://id.example"]})
            if url == "https://id.example/.well-known/oauth-authorization-server":
                return Resp(200, {"authorization_endpoint": "https://id.example/authorize",
                                  "token_endpoint": "https://id.example/token",
                                  "registration_endpoint": "https://id.example/register"})
            return Resp(404)
    return Client


def q_of(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


async def flow():
    # ---- 2. discovery keeps the declared resource; authorize, token and refresh all name it
    md = None
    with patch.object(oauth_mcp.httpx, "AsyncClient", fake_client({})):
        md = await oauth_mcp._discover(MCP)
    check("_discover keeps the declared resource", (md or {}).get("_prm_resource") == "https://mcp.spacemail.com/", md)

    conn_id, err = mcp_store.add_connection("custom", {"label": "Mail", "url": MCP, "auth": "oauth"})
    assert not err, err
    with patch.object(oauth_mcp.httpx, "AsyncClient", fake_client({"client_id": "own-client", "redirect_uris": [REDIR]})):
        r = await oauth_mcp.start_auth(conn_id, REDIR)
        check("start_auth opens the sign-in page", r.get("ok") and r.get("url", "").startswith("https://id.example/authorize"), r)
        q = q_of(r.get("url", ""))
        check("the authorize request names the canonical resource", q.get("resource") == "https://mcp.spacemail.com/", q)
        check("the client from DCR is used", q.get("client_id") == "own-client", q)
        SENT.clear()
        cb = await oauth_mcp.handle_callback(q.get("state"), "code-1")
        check("the callback stores a token", cb.get("ok"), cb)
        tok = [d for (m, u, j, d) in SENT if m == "POST" and u.endswith("/token")]
        check("the code exchange names the same resource", tok and tok[0].get("resource") == "https://mcp.spacemail.com/", tok)
        ent = oauth_mcp._load().get(conn_id) or {}
        SENT.clear()
        await oauth_mcp._refresh(conn_id, ent)
        ref = [d for (m, u, j, d) in SENT if m == "POST" and u.endswith("/token")]
        check("the refresh names the same resource", ref and ref[0].get("resource") == "https://mcp.spacemail.com/"
              and ref[0].get("grant_type") == "refresh_token", ref)

    # ---- 3. a shared client that does not allow Javis's callback stops before the sign-in page
    conn2, err = mcp_store.add_connection("custom", {"label": "Mail 2", "url": MCP, "auth": "oauth"})
    assert not err, err
    shared = {"client_id": "starlight.mcp", "redirect_uris": ["https://provider-app.example/callback"]}
    with patch.object(oauth_mcp.httpx, "AsyncClient", fake_client(shared)):
        r2 = await oauth_mcp.start_auth(conn2, REDIR)
    check("a callback mismatch is reported, no sign-in URL", r2.get("ok") is False and not r2.get("url"), r2)
    check("the error names Javis's callback", REDIR in str(r2.get("error")), r2)
    check("the shared client is not saved for the next attempt",
          (oauth_mcp._load().get(conn2) or {}).get("client_id", "") == "")
    # CANARY: a DCR answer that does not list callbacks (many servers) still proceeds.
    conn3, err = mcp_store.add_connection("custom", {"label": "Mail 3", "url": MCP, "auth": "oauth"})
    with patch.object(oauth_mcp.httpx, "AsyncClient", fake_client({"client_id": "c3"})):
        r3 = await oauth_mcp.start_auth(conn3, REDIR)
    check("CANARY: a DCR answer without redirect_uris still proceeds", r3.get("ok") and q_of(r3["url"]).get("client_id") == "c3", r3)


asyncio.run(flow())
_ = secrets_store

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nOK - test_mcp_oauth_resource: all passed")
