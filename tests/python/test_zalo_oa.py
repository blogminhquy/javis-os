"""Zalo OA channel (0.412.0): a dedicated bot answers a Zalo Official Account's inbox.

    python tests/run.py zalo_oa

No network: Zalo's OAuth and OpenAPI hosts are faked with httpx.MockTransport. What is guarded,
in order of what would hurt most if it broke:

  1. The webhook is a PUBLIC URL. A POST no known OA secret key signed is refused before any bot
     sees it; the signature is sha256(app_id + body + timestamp + OA secret key).
  2. Tokens rotate and a refresh token works once. Every new pair is written to the account store
     at once, two callers never refresh one account at the same time, and checking a pasted token
     (which spends it) hands the newer pair to the account saved right after.
  3. Events reach the bot of the OA they were sent to; the OA's own messages and follow events
     are skipped; Zalo's retries of one message are answered once.
  4. One full turn: the answer goes back to the sender as a plain-text consultation message.
  5. The channel is in the registry as a bot channel with a webhook; domain verification works.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import types

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-oa-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import channel_accounts  # noqa: E402
import channels  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_oa_bot as zo  # noqa: E402

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
USER = "2512523625412515"
REFRESH0 = "r0_" + "x" * 120

# ---- Fake Zalo ---------------------------------------------------------------------------
state = {"refresh": REFRESH0, "n": 0, "access": "", "sent": [], "bad_access": set(), "delay": 0.0}


async def zalo(req):
    if req.url.host == "oauth.zaloapp.com":
        form = dict(x.split("=", 1) for x in req.content.decode().split("&"))
        if state["delay"]:
            await asyncio.sleep(state["delay"])
        if req.headers.get("secret_key") != APP_SECRET or form.get("app_id") != APP_ID:
            return httpx.Response(200, json={"error": -14014, "error_description": "Invalid secret key"})
        if form.get("refresh_token") != state["refresh"]:
            return httpx.Response(200, json={"error": -14020, "error_description": "Invalid refresh token"})
        state["n"] += 1
        state["access"] = f"a{state['n']}_" + "y" * 80
        state["refresh"] = f"r{state['n']}_" + "z" * 120
        return httpx.Response(200, json={"access_token": state["access"], "refresh_token": state["refresh"],
                                         "expires_in": "90000"})
    tok = req.headers.get("access_token", "")
    if tok != state["access"] or tok in state["bad_access"]:
        return httpx.Response(200, json={"error": -216, "message": "Access token is invalid"})
    if req.url.path == "/v2.0/oa/getoa":
        return httpx.Response(200, json={"error": 0, "data": {"oa_id": OA_ID, "name": "Nước mắm Cô Ba"}})
    if req.url.path == "/v3.0/oa/user/detail":
        return httpx.Response(200, json={"error": 0, "data": {"user_id": USER, "display_name": "Chị Lan"}})
    if req.url.path == "/v3.0/oa/message/cs":
        state["sent"].append(json.loads(req.content))
        return httpx.Response(200, json={"error": 0, "data": {"message_id": "m1", "user_id": USER}})
    return httpx.Response(404, json={"error": -1, "message": "not faked"})


_RealClient = httpx.AsyncClient


def _client(**kw):
    kw.pop("transport", None)
    return _RealClient(transport=httpx.MockTransport(zalo), **kw)


zo.httpx = types.SimpleNamespace(AsyncClient=_client, Timeout=httpx.Timeout)

# ============================================================
# 1. Credentials
# ============================================================
pasted = f"{APP_ID} {APP_SECRET}\n{OA_SECRET} {REFRESH0}"
cr = zo.split_credentials(pasted)
check("pasted credentials split by shape, short keys in order",
      (cr["app_id"], cr["app_secret"], cr["oa_secret"], cr["refresh_token"]) == (APP_ID, APP_SECRET, OA_SECRET, REFRESH0), cr)
cr2 = zo.split_credentials(f"oa_secret={OA_SECRET} {REFRESH0} app_secret={APP_SECRET} {APP_ID}")
check("key=value parts are read by name", cr2["oa_secret"] == OA_SECRET and cr2["app_secret"] == APP_SECRET, cr2)
back = zo.split_credentials(zo.dump_credentials({**cr, "access_token": "t", "expires_at": 123.0}))
check("JSON written after a refresh reads back", back["access_token"] == "t" and back["expires_at"] == 123.0
      and back["oa_secret"] == OA_SECRET, back)
check("missing OA secret key is named", zo.missing_parts(zo.split_credentials(f"{APP_ID} {APP_SECRET} {REFRESH0}"))
      == ["OA secret key"])

check("window error reads as words", "khung" in zo._explain_error(-230) or "window" in zo._explain_error(-230))
check("unknown code keeps Zalo's message", zo._explain_error(-9999, "boom") == "boom (-9999)")

# ============================================================
# 2. Webhook signature
# ============================================================
body = json.dumps({"app_id": APP_ID, "event_name": "user_send_text", "timestamp": "1700000000000",
                   "sender": {"id": USER}, "recipient": {"id": OA_ID},
                   "message": {"msg_id": "mid1", "text": "Giá bao nhiêu ạ?"}}, ensure_ascii=False).encode()
mac = hashlib.sha256((APP_ID + body.decode() + "1700000000000" + OA_SECRET).encode()).hexdigest()
keys = [(APP_ID, OA_SECRET)]
check("documented signature accepted", zo.verify_signature(body, "mac=" + mac, keys))
check("HMAC variant accepted", zo.verify_signature(body, hmac.new(OA_SECRET.encode(), body, hashlib.sha256).hexdigest(), keys))
check("wrong secret refused", not zo.verify_signature(body, "mac=" + mac, [(APP_ID, "nope" * 5)]))
check("another app's secret refused", not zo.verify_signature(body, "mac=" + mac, [("111111", OA_SECRET)]))
check("empty signature refused", not zo.verify_signature(body, "", keys))
check("tampered body refused", not zo.verify_signature(body.replace(b"bao", b"bau"), "mac=" + mac, keys))
check("no accounts = nothing accepted", not zo.verify_signature(body, "mac=" + mac, []))

# ============================================================
# 3. Registry
# ============================================================
s = channels.spec("zalo_oa")
check("zalo_oa is a bot channel in the registry", s is not None and s.kind == "bot")
check("zalo_oa carries a bot, private only, sends text and files",
      s and s.nl("bot") and not s.nl("nhom") and s.nl("gui_chu") and s.nl("gui_file") and s.nl("tra_loi_tu_javis"),
      s and s.nang_luc)
ui = {k["id"]: k for k in channels.cho_giao_dien()}
check("UI entry carries the webhook path", ui.get("zalo_oa", {}).get("webhook") == "/zalo-oa/webhook")
check("bot store accepts zalo_oa", "zalo_oa" in chatbot_store.KENH, chatbot_store.KENH)
check("a Zalo user id passes the chat id check", bool(chatbot_store._CHAT_ID_RE.match(USER)))

# ============================================================
# 4. Token rotation
# ============================================================
r = run(zo.check_credentials(pasted))
check("checking the paste refreshes once and reads the OA", r.get("ok") and r.get("username") == OA_ID
      and r.get("bot_name") == "Nước mắm Cô Ba" and state["n"] == 1, (r, state["n"]))
r = run(zo.check_credentials(pasted))
check("checking the same paste again does not spend a refresh token", r.get("ok") and state["n"] == 1, (r, state["n"]))

aid, loi = channel_accounts.create_account({"channel": "zalo_oa", "token": pasted, "external_id": OA_ID})
check("account saved with the pasted string", aid and not loi, loi)
cr = zo.KEEPER.load(aid)
stored = zo.split_credentials(channel_accounts.get_token(aid))
check("first read swaps in the rotated pair and writes it to the store",
      cr["refresh_token"] == state["refresh"] and stored["refresh_token"] == state["refresh"]
      and stored["oa_secret"] == OA_SECRET and stored["oa_id"] == OA_ID, stored)

tok, _, err = run(zo.KEEPER.access_token(aid))
check("a fresh access token is used without refreshing", tok == state["access"] and state["n"] == 1, (err, state["n"]))

# Expire it: two callers at once must cause ONE refresh (a second would use a dead refresh token).
channel_accounts.update_account(aid, {"token": zo.dump_credentials({**stored, "expires_at": time.time() - 5})})
state["delay"] = 0.05


async def both():
    return await asyncio.gather(zo.KEEPER.access_token(aid), zo.KEEPER.access_token(aid))

res = run(both())
state["delay"] = 0.0
check("concurrent callers share one refresh", state["n"] == 2 and res[0][0] == res[1][0] == state["access"]
      and not res[0][2] and not res[1][2], (state["n"], [x[2] for x in res]))
check("the rotated refresh token is in the store",
      zo.split_credentials(channel_accounts.get_token(aid))["refresh_token"] == state["refresh"])

tok, _, err = run(zo.KEEPER.access_token("", fallback=pasted))
check("no account id: never refreshes (could not save the new pair)", not tok and err and state["n"] == 2, err)

dead = run(zo.check_credentials(f"{APP_ID} {APP_SECRET} {OA_SECRET} {'q' * 100}"))
check("a spent refresh token is refused with a reason", not dead.get("ok") and "refresh" in dead.get("error", "").lower(), dead)

# ============================================================
# 5. Webhook routing and one full turn
# ============================================================


class Probe(zo.ZaloOABot):
    def __init__(self):
        super().__init__(pasted, "", None, giau_trang_thai=True)
        self.got = []

    async def _safe_event(self, ev):
        self.got.append(ev)


async def _route():
    a, b = Probe(), Probe()
    zo._REGISTRY.clear()
    zo._REGISTRY.update({OA_ID: a, "999": b})
    ev = json.loads(body)
    n = await zo.handle_webhook(ev)
    n += await zo.handle_webhook({**ev, "event_name": "oa_send_text", "sender": {"id": OA_ID}})
    n += await zo.handle_webhook({"event_name": "follow", "oa_id": OA_ID, "follower": {"id": USER}})
    await asyncio.sleep(0)
    zo._REGISTRY.clear()
    return n, a.got, b.got

n, got_a, got_b = run(_route())
check("customer text reaches the bot of that OA only", n == 1 and len(got_a) == 1 and got_b == [], (n, got_a, got_b))


async def _turn():
    seen = {}
    state["sent"].clear()

    async def answer(text, meta, progress):
        seen["text"], seen["meta"] = text, dict(meta)
        return {"text": "**Dạ** chai 500ml giá 85.000đ ạ."}

    bot = zo.ZaloOABot(pasted, "", answer, giau_trang_thai=True, account_id=aid)
    ev = json.loads(body)
    await bot._on_event(ev)
    await bot._on_event(ev)            # Zalo retry
    for t in list(bot._current.values()):
        await t
    if bot._client:
        await bot._client.aclose()
    return seen

real = zo.httpx
seen = {}
try:
    zo.httpx = types.SimpleNamespace(AsyncClient=_client, Timeout=httpx.Timeout)
    # The turn creates its client through httpx.AsyncClient inside the module too.
    seen = run(_turn())
finally:
    zo.httpx = real
check("customer text and meta handed to the bot",
      seen.get("text") == "Giá bao nhiêu ạ?" and seen["meta"].get("platform") == "zalo_oa"
      and seen["meta"].get("chat_id") == USER and seen["meta"].get("user_name") == "Chị Lan", seen)
check("answer sent once, plain text, to the sender, as a consultation message",
      state["sent"] == [{"recipient": {"user_id": USER}, "message": {"text": "Dạ chai 500ml giá 85.000đ ạ."}}],
      state["sent"])

# A token Zalo suddenly calls invalid is refreshed once and the send repeated.
state["bad_access"].add(state["access"])
n0 = state["n"]
ok, err = run(zo.ZaloOABot("", "", None, giau_trang_thai=True, account_id=aid).send_text(USER, "Dạ"))
check("-216 on send refreshes and retries once", ok and state["n"] == n0 + 1, (ok, err, state["n"]))

# ============================================================
# 6. Endpoints (TestClient)
# ============================================================
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://localhost")
handled = []
orig_handle = zo.handle_webhook


async def fake_handle(payload):
    handled.append(payload)
    return 1
zo.handle_webhook = fake_handle
try:
    r = client.post("/zalo-oa/webhook", content=body, headers={"X-ZEvent-Signature": "mac=00"})
    check("POST with a bad signature is refused", r.status_code == 401 and not handled, r.status_code)
    r = client.post("/zalo-oa/webhook", content=body)
    check("POST without a signature is refused", r.status_code == 401, r.status_code)
    r = client.post("/zalo-oa/webhook", content=body, headers={"X-ZEvent-Signature": "mac=" + mac})
    check("POST signed with the account's OA secret key is handed over", r.status_code == 200 and len(handled) == 1,
          (r.status_code, r.text))
finally:
    zo.handle_webhook = orig_handle

r = client.get("/channels/webhook-info", params={"channel": "zalo_oa"})
check("webhook-info gives the Zalo OA address", r.status_code == 200 and r.json()["webhook_url"].endswith("/zalo-oa/webhook")
      and r.json().get("site_verify") is True, r.text)
r = client.get("/zalo_verifierABCdef123456.html")
check("an unknown verifier file is 404", r.status_code == 404, r.status_code)
r = client.post("/zalo-oa/site-verification", json={"code": "zalo_verifierABCdef123456.html"})
check("saving the verifier from its file name", r.status_code == 200 and r.json().get("code") == "ABCdef123456", r.text)
r = client.get("/zalo_verifierABCdef123456.html")
check("the saved verifier file carries the meta tag",
      r.status_code == 200 and 'content="ABCdef123456"' in r.text and "zalo-platform-site-verification" in r.text, r.text)
check("meta tag paste is read too", zo.parse_site_code(
    '<meta name="zalo-platform-site-verification" content="QWErty98765" />') == "QWErty98765")
r = client.post("/zalo-oa/site-verification", json={"code": "!!"})
check("garbage verifier code is refused", r.status_code == 400)
check("verifier path is public, nested paths are not",
      'path.startswith("/zalo_verifier")' in open(os.path.join(SERVER, "main.py"), encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
