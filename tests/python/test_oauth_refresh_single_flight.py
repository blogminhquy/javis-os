"""OAuth MCP connections keep working across a token refresh (0.400.0).

Owner report 2026-10-29 (a user on Canva): "Canva often loses its connection mid-session, or only says it is
connecting". Four causes, one check each:

1. Parallel callers near expiry each refreshed with the SAME refresh token. Canva's refresh tokens are single use,
   so the second use fails and may revoke the grant. One refresh per connection now; the rest read its result.
2. A refresh forced by a 401 is skipped when another caller already replaced the rejected token.
3. A tool call answered 401 refreshes once and runs again (the server refused before doing anything).
4. A new bearer no longer closes the open MCP session (hash ignores it, the session gets the new header).
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-oauth-refresh-")

import mcp_client  # noqa: E402
import oauth_mcp  # noqa: E402
import secrets_store  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def seed(conn_id, token, refresh, expires_in):
    store = oauth_mcp._load()
    store[conn_id] = {"access_token": secrets_store.encrypt(token), "refresh_token": secrets_store.encrypt(refresh),
                      "token_endpoint": "https://auth.example/token", "client_id": "cid",
                      "expires_at": time.time() + expires_in}
    oauth_mcp._save(store)


# ---- 1. concurrent refresh hits the network once ----
calls = []


async def fake_refresh(conn_id, ent):
    calls.append(secrets_store.decrypt(ent.get("refresh_token", "")))
    await asyncio.sleep(0.05)                       # let the other callers pile up behind the lock
    ent = dict(ent, access_token=secrets_store.encrypt("tok-2"), refresh_token=secrets_store.encrypt("rt-2"),
               expires_at=time.time() + 3600)
    store = oauth_mcp._load()
    store[conn_id] = ent
    oauth_mcp._save(store)
    return ent


real_refresh = oauth_mcp._refresh
oauth_mcp._refresh = fake_refresh
oauth_mcp.mcp_store.connection_secrets = lambda cid: {}

seed("c1", "tok-1", "rt-1", expires_in=10)          # inside the 60 s margin


async def many():
    return await asyncio.gather(*(oauth_mcp.auth_headers("c1") for _ in range(5)))


res = asyncio.run(many())
check("five callers near expiry: one refresh request", calls == ["rt-1"], calls)
check("every caller gets the new token", all(r == {"Authorization": "Bearer tok-2"} for r in res), res)
check("the rotated refresh token is stored",
      secrets_store.decrypt(oauth_mcp._load()["c1"]["refresh_token"]) == "rt-2")

# ---- 2. forced refresh only when the rejected token is still the stored one ----
calls.clear()
seed("c2", "tok-new", "rt-x", expires_in=3000)
r = asyncio.run(oauth_mcp.auth_headers("c2", force=True, rejected="Bearer tok-old"))
check("401 on a token someone already replaced: no refresh", calls == [] and r == {"Authorization": "Bearer tok-new"},
      (calls, r))
r = asyncio.run(oauth_mcp.auth_headers("c2", force=True, rejected="Bearer tok-new"))
check("401 on the stored token: refresh even before expires_at", calls == ["rt-x"], calls)
calls.clear()
r = asyncio.run(oauth_mcp.auth_headers("c2"))
check("a fresh token needs no network", calls == [], calls)
oauth_mcp._refresh = real_refresh


# ---- 3. tool call answered 401: refresh once, run again ----
class FakeHttp(mcp_client.McpHttpSession):
    """Answers 401 to an old bearer, works with the new one. No network."""
    sent = []

    def __init__(self, url, headers=None):
        super().__init__(url, headers)

    async def ensure_init(self):
        return None

    async def call_tool(self, name, arguments):
        auth = self.base_headers.get("Authorization", "")
        FakeHttp.sent.append(auth)
        if auth != "Bearer good":
            raise mcp_client.McpHttpError("HTTP 401: invalid_token")
        return "design created"

    async def close(self):
        return None


pool = mcp_client.SessionPool()
pool._make = lambda spec: FakeHttp(spec.get("url", ""), spec.get("headers"))
asked = []


async def fake_auth(cid, force=False, rejected=""):
    asked.append((cid, force, rejected))
    return {"Authorization": "Bearer good" if force else "Bearer stale"}


oauth_mcp.auth_headers = fake_auth
spec = {"key": "canva", "transport": "http", "url": "https://mcp.canva.example/mcp",
        "headers": {}, "oauth_conn_id": "canva", "label": "Canva"}
out = asyncio.run(pool.call_tool(spec, "generate-design", {"query": "poster"}))
check("401 then refresh: the call succeeds", out == "design created", out)
check("the forced refresh names the rejected bearer", ("canva", True, "Bearer stale") in asked, asked)
check("the tool ran once with the good token", FakeHttp.sent.count("Bearer good") == 1, FakeHttp.sent)


async def same_token(cid, force=False, rejected=""):
    return {"Authorization": "Bearer stale"}


oauth_mcp.auth_headers = same_token
FakeHttp.sent = []
out = asyncio.run(pool.call_tool(dict(spec, key="canva2"), "generate-design", {}))
check("no new token (refresh token revoked): the 401 comes back, no loop",
      str(out).startswith("ERROR") and "401" in str(out) and len(FakeHttp.sent) == 1, (out, FakeHttp.sent))

# ---- 4. a new bearer keeps the open session ----
a = dict(spec, headers={"Authorization": "Bearer one"})
b = dict(spec, headers={"Authorization": "Bearer two"})
check("the spec hash ignores the OAuth bearer", mcp_client._spec_hash(a) == mcp_client._spec_hash(b))
check("a non-OAuth header still changes the hash",
      mcp_client._spec_hash(dict(a, oauth_conn_id="")) != mcp_client._spec_hash(dict(b, oauth_conn_id="")))
p2 = mcp_client.SessionPool()
p2._make = lambda sp: FakeHttp(sp.get("url", ""), sp.get("headers"))
k1, s1 = p2._get(a)
k2, s2 = p2._get(b)
check("same session object after the token changed", s1 is s2)
check("and it now sends the new bearer", s2.base_headers.get("Authorization") == "Bearer two", s2.base_headers)
check("the connection spec carries the OAuth id",
      mcp_client._conn_spec({"id": "x", "auth": "oauth", "url": "u"}).get("oauth_conn_id") == "x"
      and mcp_client._conn_spec({"id": "y", "url": "u"}).get("oauth_conn_id") == "")

if fails:
    print(f"\nFAIL - test_oauth_refresh_single_flight: {len(fails)}: {fails}")
    raise SystemExit(1)
print("\nOK - test_oauth_refresh_single_flight: all pass")
