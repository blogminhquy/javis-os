"""Grant access with Zalo (OAuth v4 + PKCE) for the Zalo OA channel.

    python tests/run.py zalo_oa_oauth

No network: Zalo's OAuth and OpenAPI hosts are faked with httpx.MockTransport. What is guarded:

  1. The permission address is Zalo's v4 one, carries app_id, redirect_uri, state and an S256
     code_challenge that matches the verifier the server keeps (and only the server).
  2. Input is checked before Zalo is opened: App ID digits, App secret key and OA secret key present
     (no OA secret key = every webhook event dropped unnoticed), HTTPS callback.
  3. The callback trades code + code_verifier with grant_type=authorization_code, reads the OA and
     never hands a token or secret to what the dashboard reads; a refreshed callback page does not
     spend the code twice.
  4. /finish saves a new account, or replaces the pair of the account being reconnected, and refuses
     a grant for a different OA than that account's.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import base64
import hashlib
import json
import os
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-oa-oauth-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import zalo_oa_bot as zo  # noqa: E402
import zalo_oa_oauth as zoo  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


APP_ID = "4321987654321098765"
APP_SECRET = "AbCdEfGhIjKlMnOpQrSt"
OA_SECRET = "ZyXwVuTsRqPoNmLkJiHg"
OA_ID = "579745863508352884"
REDIRECT = "https://javis.example.com/zalo-oa/oauth/callback"
ACCESS = "acc_" + "a" * 80
REFRESH = "ref_" + "r" * 120

zalo = {"codes": {}, "exchanges": 0, "oa_id": OA_ID}


async def fake(req):
    if req.url.host == "oauth.zaloapp.com":
        form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        if req.headers.get("secret_key") != APP_SECRET or form.get("app_id") != APP_ID:
            return httpx.Response(200, json={"error": -14014, "error_description": "Invalid secret key"})
        if form.get("grant_type") != "authorization_code":
            return httpx.Response(200, json={"error": -14002, "error_description": "grant_type"})
        want = zalo["codes"].pop(form.get("code", ""), None)
        if want is None:
            return httpx.Response(200, json={"error": -14019, "error_description": "Invalid code"})
        got = base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest()).decode().rstrip("=")
        if got != want:
            return httpx.Response(200, json={"error": -14018, "error_description": "Invalid code verifier"})
        zalo["exchanges"] += 1
        return httpx.Response(200, json={"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": "90000"})
    if req.headers.get("access_token") != ACCESS:
        return httpx.Response(200, json={"error": -216, "message": "Access token is invalid"})
    if req.url.path == "/v2.0/oa/getoa":
        return httpx.Response(200, json={"error": 0, "data": {"oa_id": zalo["oa_id"], "name": "Nước mắm Cô Ba"}})
    return httpx.Response(404, json={"error": -1, "message": "not faked"})


def client():
    return httpx.AsyncClient(transport=httpx.MockTransport(fake))


async def with_zalo(fn):
    async with client() as c:
        return await fn(c)


def grant(code: str, res: dict) -> None:
    """What Zalo does when the admin clicks Allow: remember the challenge the code is bound to."""
    q = parse_qs(urlparse(res["url"]).query)
    zalo["codes"][code] = q["code_challenge"][0]


KEYS = f"{APP_ID} {APP_SECRET} {OA_SECRET}"

# ============================================================
# 1. PKCE and the permission address
# ============================================================
v, ch = zoo.pkce_pair()
check("verifier is 43-128 unreserved characters", 43 <= len(v) <= 128 and all(c.isalnum() or c in "-._~" for c in v), v)
check("challenge is S256 of the verifier, base64url without padding",
      ch == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=") and "=" not in ch)

r = zoo.start(KEYS, REDIRECT, brain="shop", label="OA shop")
u = urlparse(r.get("url", ""))
q = parse_qs(u.query)
check("start gives Zalo's OAuth v4 permission address",
      r["ok"] and f"{u.scheme}://{u.netloc}{u.path}" == "https://oauth.zaloapp.com/v4/oa/permission", r)
check("the address carries app_id, redirect_uri, state and code_challenge",
      q.get("app_id") == [APP_ID] and q.get("redirect_uri") == [REDIRECT] and q.get("state") == [r["state"]]
      and len(q.get("code_challenge", [""])[0]) == 43, q)
check("no secret and no verifier in the address", all(s not in r["url"] for s in (APP_SECRET, OA_SECRET)), r["url"])
check("before the callback the grant is pending", zoo.result(r["state"])["status"] == "pending")

# ============================================================
# 2. Input
# ============================================================
check("a non-numeric App ID is refused", not zoo.start(f"abc {APP_SECRET} {OA_SECRET}", REDIRECT)["ok"])
bad = zoo.start(f"{APP_ID} {APP_SECRET}", REDIRECT)
check("a missing OA secret key is refused and named", not bad["ok"] and "OA secret key" in bad["error"], bad)
bad = zoo.start(KEYS, "http://1.2.3.4:8000/zalo-oa/oauth/callback")
check("plain HTTP is refused", not bad["ok"] and "HTTPS" in bad["error"], bad)
stored = zo.dump_credentials({"app_id": APP_ID, "app_secret": APP_SECRET, "oa_secret": OA_SECRET,
                              "refresh_token": "dead", "oa_id": OA_ID})
check("reconnect with an empty field takes the keys of the saved account",
      zoo.start("", REDIRECT, account_id="acc_x", stored=stored)["ok"])

# ============================================================
# 3. Callback
# ============================================================
r = zoo.start(KEYS, REDIRECT)
st = r["state"]
res = run(with_zalo(lambda c: zoo.callback(st, "", error="access_denied", client=c)))
check("a refused grant reads as an error, also through result()",
      not res["ok"] and zoo.result(st)["status"] == "error", res)

r = zoo.start(KEYS, REDIRECT)
st = r["state"]
zalo["codes"]["wrong"] = "not-the-challenge"
res = run(with_zalo(lambda c: zoo.callback(st, "wrong", OA_ID, client=c)))
check("a code bound to another challenge is refused by Zalo and reported", not res["ok"] and res["error"], res)

check("an unknown state reads as expired",
      not run(with_zalo(lambda c: zoo.callback("nope", "x", client=c)))["ok"] and zoo.result("nope")["status"] == "expired")

r = zoo.start(KEYS, REDIRECT, brain="shop", label="OA shop")
st = r["state"]
grant("good", r)
res = run(with_zalo(lambda c: zoo.callback(st, "good", OA_ID, client=c)))
out = zoo.result(st)
check("the callback exchanges the code with the verifier and reads the OA",
      res["ok"] and out["status"] == "ready" and out["oa_id"] == OA_ID and out["oa_name"] == "Nước mắm Cô Ba", (res, out))
blob = json.dumps(out) + json.dumps(res)
check("no token or secret in anything the dashboard reads",
      all(s not in blob for s in (ACCESS, REFRESH, APP_SECRET, OA_SECRET)), blob)
n = zalo["exchanges"]
again = run(with_zalo(lambda c: zoo.callback(st, "good", OA_ID, client=c)))
check("a refreshed callback page does not spend the code again", again["ok"] and zalo["exchanges"] == n, again)
p = zoo.take(st)
cr = p.get("credentials") or {}
check("take() hands the full credentials to the server side",
      (cr.get("access_token"), cr.get("refresh_token"), cr.get("oa_secret"), cr.get("oa_id"))
      == (ACCESS, REFRESH, OA_SECRET, OA_ID) and p.get("brain") == "shop", cr)

# ============================================================
# 4. Routes
# ============================================================
import channel_accounts  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

http = TestClient(main.app, base_url="http://localhost",
                  headers={"x-forwarded-proto": "https", "x-forwarded-host": "javis.example.com"})
check("the callback is a public path", "/zalo-oa/oauth/callback" in main._AUTH_PUBLIC_EXACT)
d = http.get("/channels/webhook-info?channel=zalo_oa").json()
check("the form gets the Callback URL to paste into the Zalo app", d.get("oauth_redirect") == REDIRECT, d)

d = http.post("/zalo-oa/oauth/start", json={"credentials": KEYS, "brain": "shop"}).json()
check("start route builds the redirect from the outside address", d.get("ok") and d.get("redirect_uri") == REDIRECT, d)


def ready_state(label="") -> str:
    r = zoo.start(KEYS, REDIRECT, brain="shop", label=label)
    grant("c-" + r["state"], r)
    assert run(with_zalo(lambda c: zoo.callback(r["state"], "c-" + r["state"], OA_ID, client=c)))["ok"]
    return r["state"]


d = http.post("/zalo-oa/oauth/finish", json={"state": "nope"})
check("finish refuses a grant that is not ready", d.status_code == 400)
st = ready_state("OA shop")
d = http.post("/zalo-oa/oauth/finish", json={"state": st}).json()
aid = (d.get("account") or {}).get("id", "")
saved = zo.split_credentials(channel_accounts.get_token(aid))
check("finish saves a new Zalo OA account with the granted pair",
      d.get("ok") and not d.get("updated") and (d.get("account") or {}).get("external_id") == OA_ID
      and saved["refresh_token"] == REFRESH and saved["oa_secret"] == OA_SECRET and saved["access_token"] == ACCESS, d)
check("the saved account is in the brain it was added from and has the label",
      (d.get("account") or {}).get("brain") == "shop" and (d.get("account") or {}).get("label") == "OA shop", d)
check("the account view carries no token", REFRESH not in json.dumps(d) and ACCESS not in json.dumps(d))
check("a finished grant is forgotten", zoo.result(st)["status"] == "expired")

# Reconnect: the old refresh token died; a new grant replaces the pair of the same account.
channel_accounts.update_account(aid, {"token": zo.dump_credentials({**saved, "refresh_token": "dead", "access_token": ""})})
ACCESS, REFRESH = "acc2_" + "b" * 80, "ref2_" + "s" * 120
d = http.post("/zalo-oa/oauth/start", json={"account_id": aid}).json()
check("reconnect start works with the saved keys only", d.get("ok"), d)
grant("re", d)
run(with_zalo(lambda c: zoo.callback(d["state"], "re", OA_ID, client=c)))
d = http.post("/zalo-oa/oauth/finish", json={"state": d["state"]}).json()
saved = zo.split_credentials(channel_accounts.get_token(aid))
check("reconnect replaces the pair of that account",
      d.get("ok") and d.get("updated") and saved["refresh_token"] == REFRESH and saved["access_token"] == ACCESS, d)
check("still one Zalo OA account", len(channel_accounts.list_accounts(channel="zalo_oa")) == 1)

# Granting the same OA again from Add channel updates the account that holds it, no duplicate.
d = http.post("/zalo-oa/oauth/finish", json={"state": ready_state()}).json()
check("a second grant of the same OA updates its account", d.get("ok") and d.get("updated")
      and (d.get("account") or {}).get("id") == aid, d)

# Reconnect but the admin picked another OA.
zalo["oa_id"] = "111222333444555666"
d = http.post("/zalo-oa/oauth/start", json={"account_id": aid}).json()
grant("other", d)
run(with_zalo(lambda c: zoo.callback(d["state"], "other", "", client=c)))
r = http.post("/zalo-oa/oauth/finish", json={"state": d["state"]})
check("reconnect refuses a grant for another OA", r.status_code == 400 and "OA" in r.json().get("error", ""), r.text)
check("the account keeps its pair", zo.split_credentials(channel_accounts.get_token(aid))["refresh_token"] == REFRESH)

r = http.post("/zalo-oa/oauth/start", json={"account_id": "acc_nope"})
check("reconnect of an unknown account is refused", r.status_code == 404)

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    sys.exit(1)
print("all passed")
