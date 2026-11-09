"""OAuth discovery finds the sign-in server of an MCP that sends no WWW-Authenticate hint (#1217, CapCut).

    python tests/run.py mcp_oauth_prm_probe      (no network)

The bug: `oauth_mcp._discover` read protected resource metadata (RFC 9728) only from the `resource_metadata` hint of a
401 `WWW-Authenticate`. CapCut's MCP answers `initialize` with 200 and no such header, so no issuer was found, every
candidate built from the MCP URL was a 404, and the CapCut card said no `.well-known` metadata was found. CapCut does
publish the metadata at the RFC 9728 path-inserted URI, which the MCP auth spec (2025-06-18) tells clients to probe.

Pinned here, with the URLs the reporter checked on 2026-11-08:
  1. no hint: the path-inserted RFC 9728 URI is probed, the issuer read, and its metadata returned with scopes
  2. the root RFC 9728 URI is the fallback when the path-inserted one is missing
  3. the probe stays on the MCP url's own origin (no request to another host before an issuer is known)
  4. a server with a hint is still read from the hint, and probing never runs then
  5. nothing published anywhere: still None
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-oauth-prm-"))

import oauth_mcp  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body if body is not None else {}, headers or {}

    def json(self):
        return self._body


CAPCUT = "https://www.capcut.com/api/external_mcp"
CAPCUT_PRM = "https://www.capcut.com/.well-known/oauth-protected-resource/api/external_mcp"
CAPCUT_AS = "https://www.capcut.com/.well-known/oauth-authorization-server/api/external_mcp/oauth"
AS_META = {"authorization_endpoint": "https://www.capcut.com/api/external_mcp/oauth/authorize",
           "token_endpoint": "https://www.capcut.com/api/external_mcp/oauth/token",
           "registration_endpoint": "https://www.capcut.com/api/external_mcp/oauth/register",
           "code_challenge_methods_supported": ["S256"]}


def fake_client(gets, post_answer=None):
    """`gets`: url -> Resp. Everything else is a 404. Records every request."""
    sent = []

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **k):
            sent.append(("POST", url))
            return post_answer or Resp(200, {"jsonrpc": "2.0", "id": 1, "result": {}})

        async def get(self, url, **k):
            sent.append(("GET", url))
            return gets.get(url) or Resp(404)
    return Client, sent


def discover(gets, url=CAPCUT, post_answer=None):
    client, sent = fake_client(gets, post_answer)
    with patch.object(oauth_mcp.httpx, "AsyncClient", client):
        return asyncio.run(oauth_mcp._discover(url)), sent


PRM = {"resource": CAPCUT, "authorization_servers": ["https://www.capcut.com/api/external_mcp/oauth"],
       "scopes_supported": ["capcut:mcp"]}

# 1. CapCut as it is
md, sent = discover({CAPCUT_PRM: Resp(200, PRM), CAPCUT_AS: Resp(200, dict(AS_META))})
check("1. CapCut: sign-in metadata found", bool(md) and md.get("token_endpoint") == AS_META["token_endpoint"], sent)
check("1. the scopes of the protected resource come along", (md or {}).get("_prm_scopes") == ["capcut:mcp"], md)
check("1. the declared resource comes along", (md or {}).get("_prm_resource") == CAPCUT, md)
gets = [u for m, u in sent if m == "GET"]
check("1. the path-inserted RFC 9728 URI is tried first", gets[:1] == [CAPCUT_PRM], gets)

# 2. root fallback
ROOT_PRM = "https://www.capcut.com/.well-known/oauth-protected-resource"
md2, sent2 = discover({ROOT_PRM: Resp(200, PRM), CAPCUT_AS: Resp(200, dict(AS_META))})
check("2. the root RFC 9728 URI is the fallback", bool(md2) and md2.get("_prm_scopes") == ["capcut:mcp"], sent2)

# 3. same origin until an issuer is known
before_issuer = []
for m, u in sent2:
    if u == CAPCUT_AS:
        break
    before_issuer.append(u)
check("3. every request before the issuer is on the MCP url's origin",
      all(u.startswith("https://www.capcut.com/") for u in before_issuer), before_issuer)

# 4. a hint still wins, no probe
HINT = "https://mcp.example.com/meta/prm"
hinted = Resp(401, headers={"www-authenticate": f'Bearer resource_metadata="{HINT}"'})
md4, sent4 = discover({HINT: Resp(200, {"resource": "https://mcp.example.com/mcp",
                                        "authorization_servers": ["https://id.example.com"]}),
                       "https://id.example.com/.well-known/oauth-authorization-server": Resp(200, dict(AS_META))},
                      url="https://mcp.example.com/mcp", post_answer=hinted)
check("4. the hint is read", bool(md4) and md4.get("_prm_resource") == "https://mcp.example.com/mcp", sent4)
check("4. no RFC 9728 probe when the hint works",
      not any("oauth-protected-resource" in u for m, u in sent4), sent4)

# 5. nothing anywhere
md5, _ = discover({})
check("5. nothing published: None", md5 is None, md5)

s = (ROOT / "server" / "oauth_mcp.py").read_text(encoding="utf-8")
check("oauth_mcp.py has no long dash", chr(0x2014) not in s and chr(0x2013) not in s)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
