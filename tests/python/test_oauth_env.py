"""A STDIO connector can take its Google sign-in as environment variables (`oauth_env`).

    python tests/run.py oauth_env

No network, no pytest: it writes a fake token into the OAuth store, like test_google_ads_oauth.py.

Why: `oauth_file` hands a server an ADC file (Google Ads, Analytics). Stape's Tag Manager MCP reads the same three
values from variables (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN) and never looks at a file, so
without this bridge a Tag Manager pack could not use the Google sign-in Javis already runs.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-oauthenv-"))

import mcp_catalog  # noqa: E402
import mcp_store  # noqa: E402
import oauth_mcp  # noqa: E402
import packs  # noqa: E402
import secrets_store  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


MAPPING = {"client_id": "GOOGLE_CLIENT_ID", "client_secret": "GOOGLE_CLIENT_SECRET",
           "refresh_token": "GOOGLE_REFRESH_TOKEN"}
FAKE = {
    "id": "env-oauth-test", "name": "Env OAuth test", "transport": "stdio",
    "command": "npx", "args": ["-y", "some-mcp@latest"],
    "auth": {"type": "oauth", "provider": "google",
             "fields": [{"key": "client_id"}, {"key": "client_secret"}]},
    "oauth_env": MAPPING,
}
PLAIN = dict(FAKE, id="no-env-oauth-test")
PLAIN.pop("oauth_env")

_real_get = mcp_catalog.get
mcp_catalog.get = lambda cid: {FAKE["id"]: FAKE, PLAIN["id"]: PLAIN}.get(cid) or _real_get(cid)


def sign_in(conn_id, refresh="RT-SECRET"):
    """Fake a finished sign-in, the way handle_callback stores it."""
    store = oauth_mcp._load()
    store[conn_id] = {"access_token": secrets_store.encrypt("AT-SHORT"),
                      "refresh_token": secrets_store.encrypt(refresh) if refresh else "",
                      "provider": "google", "expires_at": 0}
    oauth_mcp._save(store)


def env_of(conn_id):
    res = next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == conn_id), None)
    return (res or {}).get("env") or {}


# ---- credentials_env on its own ----
check("empty mapping -> nothing", oauth_mcp.credentials_env("missing", {}) == {})
check("not a dict -> nothing", oauth_mcp.credentials_env("missing", ["GOOGLE_REFRESH_TOKEN"]) == {})
check("not signed in -> nothing", oauth_mcp.credentials_env("missing", MAPPING) == {})

cid, err = mcp_store.add_connection(FAKE["id"], {
    "label": "gtm", "auth": "oauth",
    "fields": {"client_id": "CID.apps.googleusercontent.com", "client_secret": "GOCSPX-secret"}})
check("connection created", bool(cid) and not err)
check("before sign-in the process gets no half sign-in", oauth_mcp.credentials_env(cid, MAPPING) == {})

sign_in(cid)
got = oauth_mcp.credentials_env(cid, MAPPING)
check("signed in -> all three variables", got == {
    "GOOGLE_CLIENT_ID": "CID.apps.googleusercontent.com", "GOOGLE_CLIENT_SECRET": "GOCSPX-secret",
    "GOOGLE_REFRESH_TOKEN": "RT-SECRET"})
check("the short-lived access token is never handed out",
      "AT-SHORT" not in oauth_mcp.credentials_env(cid, dict(MAPPING, access_token="GOOGLE_ACCESS_TOKEN")).values())
check("a part outside the closed list is ignored",
      oauth_mcp.credentials_env(cid, {"password": "X", "refresh_token": "R"}) == {"R": "RT-SECRET"})
check("only the parts asked for", oauth_mcp.credentials_env(cid, {"refresh_token": "R"}) == {"R": "RT-SECRET"})

# ---- end to end through resolved() ----
env = env_of(cid)
check("resolved() sets GOOGLE_REFRESH_TOKEN", env.get("GOOGLE_REFRESH_TOKEN") == "RT-SECRET")
check("resolved() sets the client pair",
      env.get("GOOGLE_CLIENT_ID") == "CID.apps.googleusercontent.com"
      and env.get("GOOGLE_CLIENT_SECRET") == "GOCSPX-secret")

# A variable set by hand on the connection wins, like a hand-pasted ADC file wins over oauth_file.
mcp_store.update_connection(cid, {"env": {"GOOGLE_REFRESH_TOKEN": "BY-HAND"}})
check("a value set by hand on the connection wins", env_of(cid).get("GOOGLE_REFRESH_TOKEN") == "BY-HAND")

# Missing client secret: nothing at all, so the server starts unconfigured and says which variable is missing.
cid2, _ = mcp_store.add_connection(FAKE["id"], {"label": "no secret", "auth": "oauth",
                                                "fields": {"client_id": "ONLY-ID"}})
sign_in(cid2)
check("no client secret -> no variables", oauth_mcp.credentials_env(cid2, MAPPING) == {})
check("no client secret -> resolved() adds none", "GOOGLE_REFRESH_TOKEN" not in env_of(cid2))

# CANARY: the same sign-in on a connector WITHOUT oauth_env puts nothing in the environment, so the checks above
# measure the oauth_env block and not some other path that copies tokens around.
cid3, _ = mcp_store.add_connection(PLAIN["id"], {"label": "plain", "auth": "oauth",
                                                 "fields": {"client_id": "C", "client_secret": "S"}})
sign_in(cid3)
check("CANARY: without oauth_env the token stays out of the environment",
      "RT-SECRET" not in env_of(cid3).values())

# ---- a pack that declares oauth_env is a code pack ----
check("oauth_env is listed as a field that runs something", "oauth_env" in packs._CODE_FIELD)
empty_dir = Path(tempfile.mkdtemp(prefix="javis-oauthenv-pack-"))
check("a connector with only oauth_env makes the pack tier code",
      packs._tier(empty_dir, [{"id": "x", "transport": "http", "oauth_env": MAPPING}]) == "code")

if _fails:
    print(f"\nFAIL - test_oauth_env: {len(_fails)} failed: {_fails}")
    sys.exit(1)
print("\nOK - test_oauth_env: all passed")
