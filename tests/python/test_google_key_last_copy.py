"""Changing a Google account's key can borrow a saved one, and deleting the last copy of a key says so first.

    python tests/run.py google_key_last_copy

No network: endpoints are called directly with a fake request, OAuth sign-in is stubbed.

Why: Google shows a client secret (and a service account key) only once, when it is made. Javis keeps keys per
connection, with no separate key store (the owner chose that, 2026-11-16), so two moments matter:
- the "change key" form of an account can borrow a key another Google account holds (server-side copy);
- the delete dialog names the case where this account holds the last copy of its key.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-lastkey-")

import main  # noqa: E402
import mcp_store  # noqa: E402
import purge  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


class Request:
    url = SimpleNamespace(scheme="http", netloc="localhost:7777")
    headers = {}

    def __init__(self, data):
        self.data = data

    async def json(self):
        return dict(self.data)


def add(connector_id, label, fields, auth="oauth"):
    cid, err = mcp_store.add_connection(connector_id, {"label": label, "auth": auth, "fields": fields})
    assert cid and not err, err
    return cid


KEY_A = {"client_id": "A.apps.googleusercontent.com", "client_secret": "GOCSPX-A"}
KEY_B = {"client_id": "B.apps.googleusercontent.com", "client_secret": "GOCSPX-B"}
SA = '{"type": "service_account", "client_email": "bot@x.iam.gserviceaccount.com"}'

cal = add("google-calendar", "Lịch", KEY_A)
ads = add("google-ads", "Ads", dict(KEY_A, developer_token="DEV"))
ga = add("google-analytics", "Analytics", KEY_B)
sheets = add("google-sheets", "Sheets", {"service_account": SA, "folder_id": "F"}, auth="apikey")
keep = add("google-keep", "Keep", {"google_email": "x@gmail.com", "master_token": "aas_et/x"}, auth="apikey")

# ---- holds_last_key: yes or no, computed on the server ----
check("Calendar shares key A with Ads: not the last copy", mcp_store.holds_last_key(cal) is False)
check("Ads shares key A with Calendar: not the last copy", mcp_store.holds_last_key(ads) is False)
check("Analytics alone holds key B: the last copy", mcp_store.holds_last_key(ga) is True)
check("Sheets alone holds its service account: the last copy", mcp_store.holds_last_key(sheets) is True)
check("Keep holds no reusable key: nothing to warn about", mcp_store.holds_last_key(keep) is False)
check("an unknown connection: no", mcp_store.holds_last_key("nope") is False)

# A Search Console account with the same service account takes the warning away from Sheets.
gsc = add("google-search-console", "Search Console", {"service_account": SA}, auth="apikey")
check("Sheets and Search Console share the service account: neither is the last copy",
      mcp_store.holds_last_key(sheets) is False and mcp_store.holds_last_key(gsc) is False)

# ---- the delete dialog reads it from purge-plan ----
kinds = lambda cid: [i["kind"] for i in (purge.plan_connection(cid).get("items") or [])]
check("deleting Analytics lists 'last copy of this Google key'", "last_key" in kinds(ga))
check("the line sits right under the connection itself", kinds(ga)[:2] == ["connection", "last_key"])
check("deleting Calendar does not", "last_key" not in kinds(cal))
item = next(i for i in purge.plan_connection(ga)["items"] if i["kind"] == "last_key")
check("the line says why and what to do", bool(item.get("note")) and "GOCSPX" not in str(item))
check("no key value leaks into the plan", "GOCSPX-B" not in str(purge.plan_connection(ga)))

# ---- change key: borrow Calendar's key into Analytics through /connect/update ----
r = asyncio.run(main.connect_update(Request({"id": ga, "fields": {}, "reuse_from": cal})))
sec = mcp_store.connection_secrets(ga)
check("/connect/update with reuse_from copies the donor's client pair",
      r.get("ok") and sec.get("client_id") == KEY_A["client_id"] and sec.get("client_secret") == KEY_A["client_secret"])
check("after borrowing, key B is gone and Analytics is no longer a last copy", mcp_store.holds_last_key(ga) is False)

# A value typed in the form wins over the borrowed one.
asyncio.run(main.connect_update(Request({"id": ga, "fields": {"client_secret": "GOCSPX-typed"}, "reuse_from": cal})))
check("a typed value wins over the borrowed one", mcp_store.connection_secrets(ga).get("client_secret") == "GOCSPX-typed")

# A donor outside the Google family lends nothing.
meta = add("custom", "not google", {}, auth="header")
before = mcp_store.connection_secrets(cal)
asyncio.run(main.connect_update(Request({"id": cal, "fields": {}, "reuse_from": meta})))
check("a donor outside the family changes nothing", mcp_store.connection_secrets(cal) == before)

# ---- change key of an OAuth account: borrow, then sign in again (sign-in stubbed) ----
with patch.object(main.oauth_mcp, "start_auth", AsyncMock(return_value={"ok": True, "url": "https://accounts.google.com/x"})):
    r = asyncio.run(main.connect_oauth_start(Request({"id": cal, "connector_id": "google-calendar",
                                                      "fields": {}, "reuse_from": ga})))
check("the OAuth change-key form borrows the donor's key before signing in",
      r.get("ok") and mcp_store.connection_secrets(cal).get("client_secret") == "GOCSPX-typed")

if _fails:
    print(f"\nFAIL - test_google_key_last_copy: {len(_fails)} failed: {_fails}")
    sys.exit(1)
print("\nOK - test_google_key_last_copy: all passed")
