"""The Asana connector signs in to the official MCP V2 with the owner's own MCP app.

    python tests/run.py asana_connector      (no network)

Asana V2 (https://mcp.asana.com/v2/mcp) refuses dynamic client registration, so the card takes the Client ID and
secret of an MCP app the owner creates once, and goes through the EXPLICIT OAuth branch with Asana's own endpoints.
The token is bound to the resource https://mcp.asana.com/v2 (no /mcp), which that branch cannot discover, so the
catalog declares it and the authorize request, the code exchange and the refresh must all send it. Asana asks for no
scope parameter. The retired V1 server (https://mcp.asana.com/sse) must not come back.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import urllib.parse
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-asana-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_catalog  # noqa: E402
import mcp_store  # noqa: E402
import oauth_mcp  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


RESOURCE = "https://mcp.asana.com/v2"
REDIR = "https://javis.example/connect/oauth/callback"

# ---- 1. the catalog card
cat = {c["id"]: c for c in json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))["connectors"]}
a = cat.get("asana") or {}
auth = a.get("auth") or {}
check("the catalog has an Asana card", bool(a))
check("it points at the V2 server over HTTP", a.get("url") == "https://mcp.asana.com/v2/mcp" and a.get("transport") == "http", a.get("url"))
check("CANARY: the retired V1 SSE server is not used", "/sse" not in a.get("url", "") and a.get("transport") != "sse", a.get("url"))
check("explicit OAuth with Asana's endpoints",
      auth.get("type") == "oauth" and auth.get("authorize_url") == "https://app.asana.com/-/oauth_authorize"
      and auth.get("token_url") == "https://app.asana.com/-/oauth_token", auth.get("authorize_url"))
check("the resource is declared", auth.get("resource") == RESOURCE, auth.get("resource"))
check("no scopes are asked for", not auth.get("scopes"), auth.get("scopes"))
check("the owner pastes client_id and client_secret",
      [f.get("key") for f in auth.get("fields") or []] == ["client_id", "client_secret"])
check("a wizard step copies Javis's redirect URL", any(s.get("copy") == "redirect" for s in auth.get("steps") or []))
check("starts at read-only", a.get("default_perm") == "readonly", a.get("default_perm"))
check("the logo file exists", (ROOT / "dashboard" / "logos" / "asana.svg").exists())

con = mcp_catalog.get("asana")
check("mcp_catalog loads the card", bool(con))
for tool, want in (("get_tasks", "read"), ("search_objects", "read"), ("get_me", "read"), ("list_workspaces", "read"),
                   ("create_task", "write"), ("update_tasks", "write"), ("add_comment", "write"),
                   ("delete_task", "danger"), ("remove_followers_for_task", "danger")):
    got = mcp_catalog.classify(con, tool)
    check(f"{tool} is {want}", got == want, got)
check("read-only blocks creating a task", not mcp_catalog.allowed(con, "readonly", "full", "create_task")[0])
check("draft allows creating a task", mcp_catalog.allowed(con, "safe", "full", "create_task")[0])
check("CANARY: draft does not reach delete", not mcp_catalog.allowed(con, "safe", "full", "delete_task")[0])


# ---- 2. the sign-in flow (fake network)
class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.headers = status, body or {}, {}

    def json(self):
        return self._body


SENT = []


class Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, data=None, headers=None, **k):
        SENT.append((url, data))
        if url == "https://app.asana.com/-/oauth_token":
            return Resp(200, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})
        return Resp(404)

    async def get(self, url, **k):
        SENT.append((url, None))
        return Resp(404)


def q_of(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


async def flow():
    conn_id, err = mcp_store.add_connection("asana", {"fields": {"client_id": "app-123", "client_secret": "sec-xyz"}})
    check("a connection is added from the card", not err, err)
    with patch.object(oauth_mcp.httpx, "AsyncClient", Client):
        r = await oauth_mcp.start_auth(conn_id, REDIR)
        check("start_auth opens Asana's authorize page",
              r.get("ok") and r.get("url", "").startswith("https://app.asana.com/-/oauth_authorize?"), r)
        q = q_of(r.get("url", ""))
        check("the owner's client_id is used", q.get("client_id") == "app-123", q)
        check("the authorize request names the resource", q.get("resource") == RESOURCE, q)
        check("no scope parameter is sent", "scope" not in q, q)
        check("PKCE is used", q.get("code_challenge_method") == "S256", q)
        check("no discovery or registration call was made", not SENT, SENT)
        cb = await oauth_mcp.handle_callback(q.get("state"), "code-1")
        check("the callback stores a token", cb.get("ok"), cb)
        tok = [d for (u, d) in SENT if u == "https://app.asana.com/-/oauth_token"]
        check("the code exchange sends the secret and the resource",
              tok and tok[0].get("client_secret") == "sec-xyz" and tok[0].get("resource") == RESOURCE, tok)
        ent = oauth_mcp._load().get(conn_id) or {}
        SENT.clear()
        await oauth_mcp._refresh(conn_id, ent)
        ref = [d for (u, d) in SENT if u == "https://app.asana.com/-/oauth_token"]
        check("the refresh sends the secret and the same resource",
              ref and ref[0].get("grant_type") == "refresh_token" and ref[0].get("client_secret") == "sec-xyz"
              and ref[0].get("resource") == RESOURCE, ref)

    # CANARY: an explicit card without `resource` (Google) still sends none.
    g, err = mcp_store.add_connection("google-calendar", {"fields": {"client_id": "g-1", "client_secret": "g-s"}})
    check("CANARY: Google card still added", not err, err)
    with patch.object(oauth_mcp.httpx, "AsyncClient", Client):
        r2 = await oauth_mcp.start_auth(g, REDIR)
    check("CANARY: an explicit card without resource sends none", r2.get("ok") and "resource" not in q_of(r2["url"]), r2)


asyncio.run(flow())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nOK - test_asana_connector: all passed")
