"""OAuth discovery follows a `resource_metadata` hint on another host when it is safe (#1343, impact.com).

    python tests/run.py mcp_oauth_cross_host_prm      (no network)

The bug: `oauth_mcp._discover` fetched the hint of a 401 `WWW-Authenticate` only when it sat on the MCP url's own host.
impact.com serves MCP at https://mcp.impact.com/mcp and answers 401 with
resource_metadata="https://app.impact.com/.well-known/oauth-protected-resource" and no scope. Every candidate on
mcp.impact.com is a 404 or a 401, so the card said the server declares no OAuth, while Claude, Cursor and VS Code
connect. The values below are what impact.com served on 2026-11-11.

Pinned here:
  1. impact.com as it is: sign-in metadata found through the cross-host hint, resource and scopes come along
  2. the cross-host hint is fetched without following redirects
  3. metadata whose `resource` is not the URL called is dropped (RFC 9728 section 3.3)
  4. no cross-host fetch for an http hint, an IP literal, userinfo, a non-443 port, a host resolving to a private,
     loopback, link-local or mixed set of addresses, a failed lookup, or an http MCP url
  5. a same-host hint is unchanged (fetched with the client's own defaults, no address lookup)
  6. read-only connections ask for read scopes only; other levels, write-only menus and blocked scopes unchanged
  7. start_auth end to end: a read-only connection gets scope=mcp:read and resource=https://mcp.impact.com/mcp,
     a full one keeps both scopes
  8. the 401 must come from the URL the owner typed: a redirect to another host never gets its hint fetched
  9. the real resolver runs (offline, localhost from the hosts file) and a localhost hint is refused
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import urllib.parse
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-oauth-xhost-"))

import mcp_store  # noqa: E402
import oauth_mcp  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class Resp:
    def __init__(self, status=200, body=None, headers=None, url=None):
        self.status_code, self._body, self.headers = status, body if body is not None else {}, headers or {}
        self.url = url

    def json(self):
        return self._body


IMPACT = "https://mcp.impact.com/mcp"
HINT = "https://app.impact.com/.well-known/oauth-protected-resource"
AS_URL = "https://app.impact.com/.well-known/oauth-authorization-server"
REG = "https://app.impact.com/oauth2/register"
PRM = {"bearer_methods_supported": ["header"], "resource": IMPACT, "scopes_supported": ["mcp:read", "mcp:write"],
       "authorization_servers": ["https://app.impact.com"]}
AS_META = {"issuer": "https://app.impact.com", "authorization_endpoint": "https://app.impact.com/oauth2/authorize",
           "token_endpoint": "https://app.impact.com/oauth2/token", "registration_endpoint": REG,
           "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token"],
           "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
           "code_challenge_methods_supported": ["S256"]}
PUBLIC = {"151.101.1.1"}


def hinted(hint=HINT, final_url=None):
    return Resp(401, {"message": "Unauthorized"}, {"www-authenticate": f'Bearer resource_metadata="{hint}"'},
                url=final_url)


def fake_client(gets, post_answer=None, reg_answer=None):
    """`gets`: url -> Resp; everything else is a 404. POSTs to REG get `reg_answer`, the rest `post_answer`.
    Records (method, url, kwargs) of every request."""
    sent = []

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **k):
            sent.append(("POST", url, k))
            if url == REG:
                return reg_answer or Resp(404)
            ans = post_answer or Resp(200, {"jsonrpc": "2.0", "id": 1, "result": {}})
            if ans.url is None:          # no redirect: the answer comes from the URL asked
                ans.url = url
            return ans

        async def get(self, url, **k):
            sent.append(("GET", url, k))
            return gets.get(url) or Resp(404)
    return Client, sent


def resolver(table):
    looked = []

    async def _resolve(host):
        looked.append(host)
        if host not in table:
            raise OSError("no such host")
        return set(table[host])
    return _resolve, looked


def discover(gets, url=IMPACT, post_answer=None, dns=None):
    client, sent = fake_client(gets, post_answer)
    res, looked = resolver(dns if dns is not None else {"app.impact.com": PUBLIC})
    with patch.object(oauth_mcp.httpx, "AsyncClient", client), patch.object(oauth_mcp, "_resolve", res):
        return asyncio.run(oauth_mcp._discover(url)), sent, looked


IMPACT_GETS = {HINT: Resp(200, dict(PRM)), AS_URL: Resp(200, dict(AS_META))}

# 1. impact.com as it is
md, sent, looked = discover(IMPACT_GETS, post_answer=hinted())
check("1. impact.com: sign-in metadata found", bool(md) and md.get("token_endpoint") == AS_META["token_endpoint"], sent)
check("1. the declared resource comes along", (md or {}).get("_prm_resource") == IMPACT, md)
check("1. the scopes of the protected resource come along", (md or {}).get("_prm_scopes") == ["mcp:read", "mcp:write"], md)
check("1. the hint host was looked up before the fetch", looked == ["app.impact.com"], looked)
hint_gets = [k for m, u, k in sent if m == "GET" and u == HINT]
check("1. the hint is fetched exactly once", len(hint_gets) == 1, sent)

# 2. no redirects on the cross-host fetch
check("2. the cross-host hint is fetched with follow_redirects=False",
      hint_gets[:1] == [{"follow_redirects": False}], hint_gets)

# 3. RFC 9728 3.3: resource must be the URL called
for label, res_value in (("another URL on the same host", "https://mcp.impact.com/other"),
                         ("the metadata host", "https://app.impact.com/"),
                         ("missing", None)):
    prm = dict(PRM)
    if res_value is None:
        prm.pop("resource")
    else:
        prm["resource"] = res_value
    md3, sent3, _ = discover({HINT: Resp(200, prm), AS_URL: Resp(200, dict(AS_META))}, post_answer=hinted())
    check(f"3. resource {label}: metadata dropped, nothing found", md3 is None, md3)
    check(f"3. resource {label}: the authorization server named in it is never asked",
          not any(u == AS_URL for m, u, k in sent3), sent3)
md3b, _, _ = discover({HINT: Resp(200, dict(PRM, resource=IMPACT + "/")), AS_URL: Resp(200, dict(AS_META))},
                      post_answer=hinted())
check("3. a trailing slash on resource still matches", bool(md3b), md3b)
md3c, _, _ = discover({HINT: Resp(200, dict(PRM, resource="HTTPS://MCP.IMPACT.COM/mcp")), AS_URL: Resp(200, dict(AS_META))},
                      post_answer=hinted())
check("3. scheme and host compare case-insensitively", bool(md3c), md3c)
for label, res_value in (("another query", IMPACT + "?tenant=x"), ("path parameters", IMPACT + ";x"),
                         ("two trailing slashes", IMPACT + "//"), ("another path case", "https://mcp.impact.com/MCP")):
    md3d, _, _ = discover({HINT: Resp(200, dict(PRM, resource=res_value)), AS_URL: Resp(200, dict(AS_META))},
                          post_answer=hinted())
    check(f"3. resource with {label}: dropped", md3d is None, md3d)

# 4. guards on the cross-host fetch
cases = [
    ("http hint", "http://app.impact.com/.well-known/oauth-protected-resource", {"app.impact.com": PUBLIC}),
    ("IP literal hint", "https://151.101.1.1/.well-known/oauth-protected-resource", {"151.101.1.1": {"151.101.1.1"}}),
    ("loopback IP literal hint", "https://127.0.0.1/.well-known/oauth-protected-resource", {"127.0.0.1": {"127.0.0.1"}}),
    ("userinfo in hint", "https://user@app.impact.com/.well-known/oauth-protected-resource", {"app.impact.com": PUBLIC}),
    ("non-443 port", "https://app.impact.com:8443/.well-known/oauth-protected-resource", {"app.impact.com": PUBLIC}),
    ("host resolving to a private address", HINT, {"app.impact.com": {"10.1.2.3"}}),
    ("host resolving to loopback", HINT, {"app.impact.com": {"127.0.0.1"}}),
    ("host resolving to link-local (cloud metadata)", HINT, {"app.impact.com": {"169.254.169.254"}}),
    ("host resolving to IPv6 loopback", HINT, {"app.impact.com": {"::1"}}),
    ("host resolving to shared CGNAT space (not private, not global)", HINT, {"app.impact.com": {"100.64.0.1"}}),
    ("host resolving to IPv6 unique-local", HINT, {"app.impact.com": {"fd00::1"}}),
    ("host resolving to a NAT64 address carrying 10.0.0.1", HINT, {"app.impact.com": {"64:ff9b::a00:1"}}),
    ("non-ASCII host", "https://b\u00fccher.example/.well-known/oauth-protected-resource", {"b\u00fccher.example": PUBLIC}),
    ("host resolving to a public and a private address", HINT, {"app.impact.com": {"151.101.1.1", "10.0.0.7"}}),
    ("host that does not resolve", HINT, {}),
    ("host resolving to no address at all", HINT, {"app.impact.com": set()}),
]
for label, hint, dns in cases:
    gets = {hint: Resp(200, dict(PRM)), AS_URL: Resp(200, dict(AS_META))}
    md4, sent4, _ = discover(gets, post_answer=hinted(hint), dns=dns)
    check(f"4. {label}: hint not fetched", not any(m == "GET" and u == hint for m, u, k in sent4), sent4)
    check(f"4. {label}: nothing found", md4 is None, md4)
md4n, sent4n, _ = discover(IMPACT_GETS, post_answer=hinted(), dns={"app.impact.com": {"64:ff9b::9765:101"}})
check("4. NAT64 address carrying a public IPv4 is accepted", bool(md4n), sent4n)


def slow_resolver():
    async def _resolve(host):
        await asyncio.sleep(2)
        return set(PUBLIC)
    return _resolve


client_s, sent_s = fake_client(IMPACT_GETS, hinted())
with patch.object(oauth_mcp.httpx, "AsyncClient", client_s), patch.object(oauth_mcp, "_resolve", slow_resolver()), \
        patch.object(oauth_mcp, "_RESOLVE_TIMEOUT", 0.05):
    md4s = asyncio.run(oauth_mcp._discover(IMPACT))
check("4. a lookup slower than the timeout: hint not fetched", md4s is None and not any(u == HINT for m, u, k in sent_s),
      sent_s)
md4h, sent4h, looked4h = discover(IMPACT_GETS, url="http://mcp.impact.com/mcp", post_answer=hinted())
check("4. http MCP url: cross-host hint not fetched", not any(u == HINT for m, u, k in sent4h), sent4h)
check("4. http MCP url: no address lookup", looked4h == [], looked4h)

# 5. same-host hint unchanged
SAME = "https://mcp.example.com/.well-known/oauth-protected-resource/mcp"
md5, sent5, looked5 = discover(
    {SAME: Resp(200, {"resource": "https://mcp.example.com/mcp", "authorization_servers": ["https://id.example.com"],
                      "scopes_supported": ["read"]}),
     "https://id.example.com/.well-known/oauth-authorization-server": Resp(200, dict(AS_META))},
    url="https://mcp.example.com/mcp", post_answer=hinted(SAME), dns={})
check("5. same-host hint: found", bool(md5) and md5.get("_prm_scopes") == ["read"], sent5)
check("5. same-host hint: fetched with the client's defaults",
      [k for m, u, k in sent5 if u == SAME] == [{}], sent5)
check("5. same-host hint: no address lookup", looked5 == [], looked5)

# 6. scopes by connection level
mdi = {"_prm_scopes": ["mcp:read", "mcp:write"], "scopes_supported": ["openid"]}
check("6. readonly: read scope only", oauth_mcp._pick_scopes(mdi, {}, "readonly") == ["mcp:read"])
check("6. full: both scopes", oauth_mcp._pick_scopes(mdi, {}, "full") == ["mcp:read", "mcp:write"])
check("6. safe: both scopes", oauth_mcp._pick_scopes(mdi, {}, "safe") == ["mcp:read", "mcp:write"])
check("6. no level given (old callers): both scopes", oauth_mcp._pick_scopes(mdi, {}) == ["mcp:read", "mcp:write"])
check("6. readonly, write-only menu: kept so sign-in still works",
      oauth_mcp._pick_scopes({"_prm_scopes": ["mcp:write"]}, {}, "readonly") == ["mcp:write"])
check("6. readonly: other write spellings dropped",
      oauth_mcp._pick_scopes({"_prm_scopes": ["files.read", "files.write", "write", "user/write", "rewrite_rules"]},
                             {}, "readonly") == ["files.read", "rewrite_rules"])
check("6. readonly: WWW-Authenticate scope still wins",
      oauth_mcp._pick_scopes({"_www_scope": "read", "_prm_scopes": ["mcp:read", "mcp:write"]}, {}, "readonly") == ["read"])
check("6. readonly: blocked scopes still dropped",
      oauth_mcp._pick_scopes({"_prm_scopes": ["mcp:read", "profile", "mcp:write"]}, {"blocked_scopes": ["profile"]},
                             "readonly") == ["mcp:read"])
check("6. scope_omit still sends nothing", oauth_mcp._pick_scopes(mdi, {"scope_omit": True}, "readonly") == [])
check("6. readonly: sign-in scopes alone do not count, write menu kept",
      oauth_mcp._pick_scopes({"_prm_scopes": ["offline_access", "mcp:write"]}, {}, "readonly")
      == ["offline_access", "mcp:write"])
check("6. readonly: sign-in scopes stay next to the read scope",
      oauth_mcp._pick_scopes({"_prm_scopes": ["openid", "offline_access", "mcp:read", "mcp:write"]}, {}, "readonly")
      == ["openid", "offline_access", "mcp:read"])

# 7. start_auth end to end
REDIRECT = "https://javis.example.com/connect/oauth/callback"


def start(perm):
    conn_id, err = mcp_store.add_connection("custom", {"label": f"Impact {perm}", "url": IMPACT, "auth": "oauth",
                                                       "perm": perm})
    assert not err, err
    client, sent = fake_client(IMPACT_GETS, post_answer=hinted(),
                               reg_answer=Resp(201, {"client_id": f"dcr-{perm}", "redirect_uris": [REDIRECT]}))
    res, _ = resolver({"app.impact.com": PUBLIC})
    with patch.object(oauth_mcp.httpx, "AsyncClient", client), patch.object(oauth_mcp, "_resolve", res):
        out = asyncio.run(oauth_mcp.start_auth(conn_id, REDIRECT))
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(out.get("url") or "").query))
    return out, q, sent


out, q, sent7 = start("readonly")
check("7. readonly: sign-in URL built", out.get("ok") is True and out["url"].startswith(AS_META["authorization_endpoint"] + "?"), out)
check("7. readonly: asks for mcp:read only", q.get("scope") == "mcp:read", q)
check("7. readonly: resource is the MCP url", q.get("resource") == IMPACT, q)
check("7. readonly: client from registration, PKCE S256",
      q.get("client_id") == "dcr-readonly" and q.get("code_challenge_method") == "S256", q)
reg = [k.get("json") for m, u, k in sent7 if m == "POST" and u == REG]
check("7. registration names the Javis callback", reg[:1] and reg[0].get("redirect_uris") == [REDIRECT], reg)
out_f, q_f, _ = start("full")
check("7. full: keeps both scopes", out_f.get("ok") is True and q_f.get("scope") == "mcp:read mcp:write", q_f)

# 8. the 401 must come from the URL the owner typed
md8, sent8, looked8 = discover(IMPACT_GETS, post_answer=hinted(final_url="https://c.attacker.example/mcp"))
check("8. initialize redirected to another host: hint not fetched",
      md8 is None and not any(u == HINT for m, u, k in sent8) and looked8 == [], sent8)
md8b, _, _ = discover(IMPACT_GETS, post_answer=hinted(final_url="https://mcp.impact.com:443/mcp/"))
check("8. a redirect on the same host and port is fine", bool(md8b), md8b)
md8c, sent8c, _ = discover(IMPACT_GETS, post_answer=hinted(final_url="http://mcp.impact.com/mcp"))
check("8. initialize downgraded to http: hint not fetched", md8c is None and not any(u == HINT for m, u, k in sent8c),
      sent8c)
md8d, sent8d, _ = discover(IMPACT_GETS, post_answer=Resp(401, {}, {"www-authenticate":
                                                                  f'Bearer resource_metadata="{HINT}"'}, url=""))
check("8. answer with no URL: hint not fetched", md8d is None, sent8d)

# 9. the real resolver
addrs = asyncio.run(oauth_mcp._resolve("localhost"))
check("9. real resolver: localhost gives a loopback address", bool({"127.0.0.1", "::1"} & set(addrs)), addrs)
check("9. real resolver: a localhost hint is refused",
      asyncio.run(oauth_mcp._public_https_url("https://localhost/.well-known/oauth-protected-resource")) is False)

src = (SERVER / "oauth_mcp.py").read_text(encoding="utf-8")
check("oauth_mcp.py has no long dash", chr(0x2014) not in src and chr(0x2013) not in src)

print("\n" + ("all ok" if not fails else f"{len(fails)} FAIL"))
raise SystemExit(1 if fails else 0)
