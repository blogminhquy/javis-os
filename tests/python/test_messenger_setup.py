"""Messenger setup wizard and health check (0.301.0).

    python tests/run.py messenger_setup

No network: a fake Graph API answers every call. Guarded, in order of what hurt owners most:

  1. A USER token pasted into the wizard is turned into a Page token (long-lived exchange, then
     the Page's access_token). This is the error 100 / error 210 trap from real setups.
  2. A Page token for another Page, or made in another app, is refused with a reason.
  3. The app webhook is registered with `messages` and `messaging_postbacks`; a webhook saved
     without them shows red in the checklist and is marked repairable.
  4. Missing permissions are named, an expiring token is a warning, not a failure.
  5. Inputs are checked before any call, and plain HTTP is refused (Meta only calls HTTPS).
  6. No token ever appears in what the checklist returns.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-setup-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import messenger_setup  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


PAGE = "123456789012345"
APP = "987654321098765"
SECRET = "a" * 32
USER_SHORT = "EAAuser" + "s" * 60
USER_LONG = "EAAuser" + "l" * 60
PAGE_TOKEN = "EAApage" + "p" * 60
OTHER_PAGE_TOKEN = "EAAother" + "o" * 60
URL = "https://javis.example.com/messenger/webhook"
ALL_SCOPES = ["pages_messaging", "pages_manage_metadata", "pages_read_engagement", "pages_show_list"]


class FakeGraph:
    def __init__(self, scopes=None, webhook_fields=("messages", "messaging_postbacks"), page_token_expires=0):
        self.scopes = list(scopes if scopes is not None else ALL_SCOPES)
        self.webhook = {"callback_url": URL, "fields": list(webhook_fields), "active": True} if webhook_fields is not None else None
        self.page_fields = []
        self.page_token_expires = page_token_expires
        self.calls = []

    def __call__(self, req: httpx.Request):
        p = req.url.path.split("/", 2)[-1]
        q = dict(req.url.params)
        self.calls.append((req.method, p, q))
        if p == "debug_token":
            t = q.get("input_token")
            if t in (USER_SHORT, USER_LONG):
                d = {"is_valid": True, "type": "USER", "app_id": APP, "user_id": "9", "scopes": self.scopes,
                     "expires_at": 0 if t == USER_LONG else 1}
            elif t == PAGE_TOKEN:
                d = {"is_valid": True, "type": "PAGE", "app_id": APP, "profile_id": PAGE, "scopes": self.scopes,
                     "expires_at": self.page_token_expires}
            elif t == OTHER_PAGE_TOKEN:
                d = {"is_valid": True, "type": "PAGE", "app_id": APP, "profile_id": "999", "scopes": self.scopes}
            else:
                return httpx.Response(200, json={"error": {"code": 190, "message": "bad"}})
            return httpx.Response(200, json={"data": d})
        if p == "oauth/access_token":
            ok = q.get("fb_exchange_token") == USER_SHORT and q.get("client_secret") == SECRET
            return httpx.Response(200, json={"access_token": USER_LONG} if ok else {"error": {"code": 190}})
        if p == PAGE and req.method == "GET":
            tok = q.get("access_token")
            if q.get("fields") == "name,access_token" and tok == USER_LONG:
                return httpx.Response(200, json={"id": PAGE, "name": "Em Mị làm nông", "access_token": PAGE_TOKEN})
            if tok == PAGE_TOKEN:
                return httpx.Response(200, json={"id": PAGE, "name": "Em Mị làm nông"})
            return httpx.Response(200, json={"error": {"code": 100, "message": "missing permission"}})
        if p == f"{APP}/subscriptions":
            if req.method == "POST":
                if not q.get("verify_token") or q.get("callback_url") != URL:
                    return httpx.Response(200, json={"error": {"code": 2200, "message": "verify failed"}})
                self.webhook = {"callback_url": q["callback_url"], "fields": q["fields"].split(","), "active": True}
                return httpx.Response(200, json={"success": True})
            data = []
            if self.webhook:
                data.append({"object": "page", "callback_url": self.webhook["callback_url"],
                             "active": self.webhook["active"],
                             "fields": [{"name": f, "version": "v23.0"} for f in self.webhook["fields"]]})
            return httpx.Response(200, json={"data": data})
        if p == f"{PAGE}/subscribed_apps":
            if q.get("access_token") != PAGE_TOKEN:
                return httpx.Response(200, json={"error": {"code": 210, "message": "A page access token is required"}})
            if req.method == "POST":
                self.page_fields = q["subscribed_fields"].split(",")
                return httpx.Response(200, json={"success": True})
            return httpx.Response(200, json={"data": [{"id": APP, "subscribed_fields": self.page_fields}]
                                             if self.page_fields else []})
        return httpx.Response(404, json={"error": {"message": "unexpected " + p}})


async def with_graph(g, fn):
    async with httpx.AsyncClient(transport=httpx.MockTransport(g)) as c:
        return await fn(c)


def run(coro):
    return asyncio.run(coro)


# ============================================================
# 1. User token -> Page token, whole wizard
# ============================================================
g = FakeGraph(webhook_fields=None)
r = run(with_graph(g, lambda c: messenger_setup.connect(PAGE, APP, SECRET, USER_SHORT, URL, "vt", client=c)))
check("connect succeeds from a short user token", r.get("ok"), r)
check("the stored token is the Page token", r.get("page_token") == PAGE_TOKEN)
check("page name read", r.get("page_name") == "Em Mị làm nông", r.get("page_name"))
check("app webhook registered with both fields", g.webhook and g.webhook["fields"] == ["messages", "messaging_postbacks"], g.webhook)
check("page subscribed", g.page_fields == ["messages", "messaging_postbacks"], g.page_fields)
check("exchange used the app secret", any(p == "oauth/access_token" for _, p, _ in g.calls))
chk = r.get("check") or {}
check("checklist all green", chk.get("ok"), [i for i in chk.get("items", []) if i["ok"] is False])
check("no token in the checklist", all(t not in json.dumps(chk) for t in (PAGE_TOKEN, USER_LONG, USER_SHORT, SECRET)))

# ============================================================
# 2. Page token passes straight through; wrong Page refused
# ============================================================
g = FakeGraph()
r = run(with_graph(g, lambda c: messenger_setup.connect(PAGE, APP, SECRET, PAGE_TOKEN, URL, "vt", client=c)))
check("page token accepted as is", r.get("ok") and r.get("page_token") == PAGE_TOKEN, r)
check("no exchange for a page token", not any(p == "oauth/access_token" for _, p, _ in g.calls))
r = run(with_graph(FakeGraph(), lambda c: messenger_setup.connect(PAGE, APP, SECRET, OTHER_PAGE_TOKEN, URL, "vt", client=c)))
check("token of another Page refused", not r.get("ok") and "999" in r.get("error", ""), r)
r = run(with_graph(FakeGraph(), lambda c: messenger_setup.connect(PAGE, "1111", SECRET, PAGE_TOKEN, URL, "vt", client=c)))
check("token from another app refused", not r.get("ok") and APP in r.get("error", ""), r)

# ============================================================
# 3. Webhook without `messages` -> red and repairable; repair fixes it
# ============================================================
g = FakeGraph(webhook_fields=())
g.page_fields = ["messages", "messaging_postbacks"]
chk = run(with_graph(g, lambda c: messenger_setup.run_checks(c, PAGE, PAGE_TOKEN, SECRET, APP, URL)))
row = next((i for i in chk["items"] if i["id"] == "webhook_fields"), {})
check("webhook without fields is red", row.get("ok") is False, row)
check("and marked repairable", row.get("auto") is True)
check("checklist not ok", chk["ok"] is False)
rep = run(with_graph(g, lambda c: messenger_setup.repair(c, PAGE, PAGE_TOKEN, APP, SECRET, URL, "vt")))
check("repair ok", rep.get("ok"), rep)
chk = run(with_graph(g, lambda c: messenger_setup.run_checks(c, PAGE, PAGE_TOKEN, SECRET, APP, URL)))
check("green after repair", chk["ok"], [i for i in chk["items"] if i["ok"] is False])

# ============================================================
# 4. A user token saved as the account token: error 210 trap is named
# ============================================================
g = FakeGraph()
chk = run(with_graph(g, lambda c: messenger_setup.run_checks(c, PAGE, USER_LONG, SECRET, APP, URL)))
row = next((i for i in chk["items"] if i["id"] == "token_type"), {})
check("user token flagged red", row.get("ok") is False and "210" in row.get("fix", ""), row)

# ============================================================
# 5. Missing scope named; expiring token is a warning only
# ============================================================
g = FakeGraph(scopes=["pages_messaging", "pages_show_list"], page_token_expires=1900000000)
g.page_fields = ["messages", "messaging_postbacks"]
chk = run(with_graph(g, lambda c: messenger_setup.run_checks(c, PAGE, PAGE_TOKEN, SECRET, APP, URL)))
sc = next(i for i in chk["items"] if i["id"] == "scopes")
check("missing scopes listed", sc["ok"] is False and "pages_read_engagement" in sc["detail"]
      and "pages_manage_metadata" in sc["detail"], sc)
ex = next(i for i in chk["items"] if i["id"] == "expiry")
check("expiry is a warning", ex["ok"] is None and ex["detail"], ex)

# ============================================================
# 6. Inputs refused before any network call
# ============================================================
g = FakeGraph()
for name, args in (("non-digit page id", ("abc", APP, SECRET, PAGE_TOKEN, URL)),
                   ("short app secret", (PAGE, APP, "abc", PAGE_TOKEN, URL)),
                   ("short token", (PAGE, APP, SECRET, "EAA", URL)),
                   ("plain http", (PAGE, APP, SECRET, PAGE_TOKEN, "http://1.2.3.4/messenger/webhook"))):
    r = run(with_graph(g, lambda c, a=args: messenger_setup.connect(*a, "vt", client=c)))
    check(f"refused: {name}", not r.get("ok") and r.get("error"), r)
check("no Graph call for bad input", not g.calls, g.calls)
r = run(with_graph(g, lambda c: messenger_setup.connect(PAGE, APP, SECRET, PAGE_TOKEN, "http://x/messenger/webhook", "vt", client=c)))
check("http refusal names the step", r.get("step") == "https", r)

# ============================================================
# 7. Routes: the account is stored with the Page token, a second connect updates it,
#    and no response carries a secret
# ============================================================
from fastapi.testclient import TestClient  # noqa: E402

import channel_accounts  # noqa: E402
import main  # noqa: E402
import messenger_bot  # noqa: E402

seen = {}


async def fake_connect(page_id, app_id, app_secret, token, webhook_url, verify_token, client=None):
    seen["webhook_url"], seen["verify"] = webhook_url, verify_token
    return {"ok": True, "page_token": PAGE_TOKEN, "page_name": "Em Mị làm nông",
            "repair_errors": [], "check": {"ok": True, "items": []}}


real_connect = messenger_setup.connect
messenger_setup.connect = fake_connect
# Behind the HTTPS tunnel the server sees localhost plus the forwarded headers set by the proxy.
client = TestClient(main.app, base_url="http://localhost",
                    headers={"x-forwarded-proto": "https", "x-forwarded-host": "javis.example.com"})
body = {"page_id": PAGE, "app_id": APP, "app_secret": SECRET, "token": USER_SHORT, "label": ""}
r = client.post("/messenger/connect", json=body)
d = r.json()
check("connect route ok", r.status_code == 200 and d.get("ok"), d)
check("webhook url built from the request", seen.get("webhook_url") == URL, seen)
check("verify token passed", bool(seen.get("verify")))
acc = channel_accounts.list_accounts(channel="messenger")
check("one account saved", len(acc) == 1, acc)
cr = messenger_bot.split_credentials(channel_accounts.get_token(acc[0]["id"])) if acc else {}
check("saved secret holds the Page token, not the pasted one",
      cr == {"page_id": PAGE, "access_token": PAGE_TOKEN, "app_secret": SECRET}, cr)
check("label falls back to the Page name", acc and acc[0]["label"] == "Em Mị làm nông", acc)
check("app id kept in meta", acc and (acc[0].get("meta") or {}).get("app_id") == APP)
check("no secret in the response", all(t not in r.text for t in (PAGE_TOKEN, USER_SHORT, SECRET)))
r2 = client.post("/messenger/connect", json=body).json()
check("second connect updates, not duplicates",
      r2.get("updated") and len(channel_accounts.list_accounts(channel="messenger")) == 1, r2)
info = client.get("/messenger/setup").json()
check("setup lists the account and https", info.get("https") and len(info.get("accounts", [])) == 1, info)
check("setup carries no secret", all(t not in json.dumps(info) for t in (PAGE_TOKEN, SECRET)))

messenger_setup.connect = real_connect
r = client.post("/messenger/connect", json={**body, "app_secret": "short"})
check("bad input is a 400 with a reason", r.status_code == 400 and r.json().get("error"), r.text)
r = client.post("/messenger/check", json={"account_id": "acc_nope"})
check("check on unknown account is 404", r.status_code == 404)

if _fails:
    print(f"\n{len(_fails)} FAILED")
    sys.exit(1)
print("\nall ok")
