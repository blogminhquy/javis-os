"""Facebook Messenger channel (0.134.0): a dedicated bot answers a Facebook Page's inbox.

    python tests/run.py messenger

No network. What is guarded, in order of what would hurt most if it broke:

  1. The webhook is a PUBLIC URL. A POST no known app secret signed is refused before anything
     reads it; the GET handshake only echoes the challenge for the right verify token.
  2. Events reach the bot of the Page they were sent to, never another Page's bot; the Page's
     own echoes are skipped; Meta's retries of the same message are answered once.
  3. One full turn: seen marker, typing, answer to the sender as plain text (Messenger shows
     Markdown literally), split under the 2000-character limit.
  4. The channel is in the registry as a bot channel with a webhook, so the Chatbot page, the
     inbox and the bot store pick it up without per-channel code.
  5. Credentials pasted in one field split correctly; Meta errors read as words.
  6. Start-up: a wrong or missing App secret stops the bot with a reason (otherwise every webhook
     fails its signature and the bot hears nothing while looking healthy); a failed automatic
     subscribe only warns, because a Page subscribed by hand in the Meta app still delivers.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import chatbot_store  # noqa: E402
import messenger_bot  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


SECRET = "b" * 32
TOKEN = "EAA" + "y" * 60
PAGE = "1234567890123"

# ============================================================
# 1. Credentials, formatting, errors
# ============================================================
cr = messenger_bot.split_credentials(f"{TOKEN} {PAGE}\n{SECRET}")
check("credentials split by shape, any order",
      cr == {"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, cr)
check("missing part stays empty", messenger_bot.split_credentials(PAGE + " " + TOKEN)["app_secret"] == "")

plain = messenger_bot.md_to_plain("## Học phí\n**Lớp 9**: 1.200.000đ\n- Thứ 2\n* Thứ 5\n[Đăng ký](https://mtm.vn/dk)\n`mã`")
check("Markdown stripped for Messenger",
      plain == "Học phí\nLớp 9: 1.200.000đ\n• Thứ 2\n• Thứ 5\nĐăng ký (https://mtm.vn/dk)\nmã", plain)
check("math stars left alone", messenger_bot.md_to_plain("2 * 3 * 4 = 24") == "2 * 3 * 4 = 24")

long = ("Một câu khá dài về lịch học. " * 200).strip()
parts = messenger_bot._chunks(long)
check("long answer split under the 2000-char limit",
      len(parts) > 1 and all(len(p) <= 2000 for p in parts) and " ".join(parts).split() == long.split(),
      [len(p) for p in parts])

e = messenger_bot._explain_error(10, "x", 2018278)
check("24-hour window error reads as words (subcode wins)", "24" in e and "2018278" in e, e)
check("1545041 is the 24-hour window too", "24" in messenger_bot._explain_error(1545041))
check("pages_messaging review explained on 200", "pages_messaging" in messenger_bot._explain_error(200))
check("unknown code keeps Meta's message", messenger_bot._explain_error(999, "boom") == "boom (999)")

# ============================================================
# 2. Registry: Messenger is a bot channel with a webhook
# ============================================================
s = channels.spec("messenger")
check("messenger is in the channel registry", s is not None and s.kind == "bot")
check("messenger can carry a dedicated bot, no groups, sends text and files",
      s and s.nl("bot") and not s.nl("nhom") and s.nl("gui_chu") and s.nl("gui_file")
      and s.nl("tra_loi_tu_javis"), s and s.nang_luc)
ui = {k["id"]: k for k in channels.cho_giao_dien()}
check("UI entry carries the webhook path", ui.get("messenger", {}).get("webhook") == "/messenger/webhook",
      ui.get("messenger"))
check("other channels carry no webhook path", ui.get("telegram", {}).get("webhook") == "")
# 0.436.1: the add-account form links a step-by-step guide; both files must exist or the link is dead.
g = ui.get("messenger", {}).get("huong_dan") or {}
check("UI entry carries the step-by-step guide, and both files exist",
      g.get("vi") and g.get("en") and (ROOT / "docs" / g["vi"]).is_file() and (ROOT / "docs" / "en" / g["en"]).is_file(), g)
check("channels without a guide carry none", ui.get("telegram", {}).get("huong_dan") == {})
# 0.436.2: the add-account form points Messenger to its Connections card instead of a second connect.
check("Messenger has a Connections card, other channels do not",
      ui.get("messenger", {}).get("the_ket_noi") is True and ui.get("telegram", {}).get("the_ket_noi") is False)
check("bot store accepts messenger as a channel", "messenger" in chatbot_store.KENH, chatbot_store.KENH)
check("a Messenger PSID passes the chat id check", bool(chatbot_store._CHAT_ID_RE.match("24987361234567890")))


# ============================================================
# 3. Webhook routing
# ============================================================
class Probe(messenger_bot.MessengerBot):
    def __init__(self, page):
        super().__init__({"page_id": page, "access_token": TOKEN, "app_secret": SECRET}, "", None,
                         giau_trang_thai=True)
        self.got = []

    async def _safe_event(self, ev):
        self.got.append(ev)


def ev(mid, text="hi", sender="555", **msg):
    m = {"mid": mid, "text": text}
    m.update(msg)
    return {"sender": {"id": sender}, "recipient": {"id": PAGE}, "timestamp": 1, "message": m}


async def _route():
    a, b = Probe(PAGE), Probe("999")
    messenger_bot._REGISTRY.clear()
    messenger_bot._REGISTRY.update({PAGE: a, "999": b})
    n = await messenger_bot.handle_webhook({"object": "page", "entry": [
        {"id": PAGE, "messaging": [ev("m1"), ev("m2", is_echo=True),
                                   {"sender": {"id": "555"}, "recipient": {"id": PAGE}, "read": {"watermark": 1}},
                                   {"sender": {"id": "555"}, "postback": {"title": "Bắt đầu", "payload": "GET_STARTED"}}]},
        {"id": "777", "messaging": [ev("m3")]}]})
    await asyncio.sleep(0)
    other = await messenger_bot.handle_webhook({"object": "instagram", "entry": [{"id": PAGE, "messaging": [ev("m4")]}]})
    messenger_bot._REGISTRY.clear()
    return n, a.got, b.got, other

n, got_a, got_b, other = run(_route())
check("message and postback reach the bot of that Page", [g.get("message", {}).get("mid") or "postback" for g in got_a]
      == ["m1", "postback"], got_a)
check("echo and read receipt are skipped", n == 2, n)
check("another Page's bot hears nothing", got_b == [], got_b)
check("non-page objects are ignored", other == 0)


# ============================================================
# 4. One full turn (Graph faked)
# ============================================================
async def _turn():
    calls = []
    seen = {}

    async def answer(text, meta, progress):
        seen["text"], seen["meta"] = text, dict(meta)
        return {"text": "**Dạ**, lớp 9 học tối thứ 3 ạ."}

    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "",
                                     answer, giau_trang_thai=True)

    async def fake_post(client, path, payload):
        calls.append((path, payload))
        return {"ok": True}

    async def fake_name(client, psid):
        return "Phụ huynh A"

    bot._post_json = fake_post
    bot._name_of = fake_name
    await bot._on_event(ev("mid.1", "Lớp 9 học khi nào ạ?"))
    await bot._on_event(ev("mid.1", "Lớp 9 học khi nào ạ?"))      # Meta retry
    for task in list(bot._current.values()):
        await task
    await asyncio.sleep(0)
    if bot._client:
        await bot._client.aclose()
    return calls, seen

calls, seen = run(_turn())
actions = [c[1].get("sender_action") for c in calls if c[1].get("sender_action")]
texts = [c[1]["message"]["text"] for c in calls if c[1].get("message")]
check("customer text and meta handed to the bot",
      seen.get("text") == "Lớp 9 học khi nào ạ?" and seen["meta"].get("chat_id") == "555"
      and seen["meta"].get("platform") == "messenger" and seen["meta"].get("chat_type") == "private"
      and seen["meta"].get("user_name") == "Phụ huynh A" and seen["meta"].get("message_id") == "mid.1", seen)
check("seen marker first, typing while answering", actions[:2] == ["mark_seen", "typing_on"], actions)
check("answer goes to the sender as plain text, once", texts == ["Dạ, lớp 9 học tối thứ 3 ạ."], texts)
check("answer is a RESPONSE to the sender on the Page's endpoint",
      any(c[0] == f"{PAGE}/messages" and c[1].get("messaging_type") == "RESPONSE"
          and c[1]["recipient"] == {"id": "555"} for c in calls), calls)
check("customer bot shows no tool trail", not any("⚙" in t for t in texts), texts)


async def _silent():
    calls = []

    async def answer(text, meta, progress):
        return {"text": "", "files": [], "im_lang": True}

    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "",
                                     answer, giau_trang_thai=True)

    async def fake_post(client, path, payload):
        calls.append(payload)
        return {"ok": True}

    async def fake_name(client, psid):
        return ""
    bot._post_json, bot._name_of = fake_post, fake_name
    await bot._on_event(ev("mid.2", "ok"))
    for task in list(bot._current.values()):
        await task
    if bot._client:
        await bot._client.aclose()
    return calls

check("a silent turn sends no text", not any(c.get("message") for c in run(_silent())))


async def _precheck():
    calls = []
    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "",
                                     None, giau_trang_thai=True,
                                     precheck_fn=lambda text, meta: {})

    async def fake_post(client, path, payload):
        calls.append(payload)
        return {"ok": True}

    async def fake_name(client, psid):
        return ""
    bot._post_json, bot._name_of = fake_post, fake_name
    await bot._on_event(ev("mid.3", "3h sáng hỏi"))
    if bot._client:
        await bot._client.aclose()
    return calls

check("precheck {} (e.g. outside active hours) keeps the bot silent",
      not any(c.get("message") for c in run(_precheck())))


# ============================================================
# 4b. Start-up: App secret checked through appsecret_proof, subscribe failure only warns
# ============================================================
import httpx  # noqa: E402

seen_params = []


def graph(req):
    seen_params.append(dict(req.url.params))
    if req.url.params.get("appsecret_proof") != messenger_bot.appsecret_proof(TOKEN, SECRET):
        return httpx.Response(400, json={"error": {"message": "Invalid appsecret_proof provided in the API argument",
                                                   "code": 100}})
    return httpx.Response(200, json={"id": PAGE, "name": "Trung tâm"})


async def ask(secret):
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as c:
        return await messenger_bot.whoami(c, PAGE, TOKEN, secret)


ok_info = run(ask(SECRET))
check("whoami sends appsecret_proof and accepts the right App secret",
      ok_info.get("ok") and ok_info.get("bot_name") == "Trung tâm" and "appsecret_proof" in seen_params[-1], ok_info)
bad_info = run(ask("c" * 32))
check("a wrong App secret is refused at connect time with a reason in words",
      not bad_info.get("ok") and "App secret" in bad_info.get("error", ""), bad_info)


async def start_with(creds, who, sub):
    orig = (messenger_bot.whoami, messenger_bot.subscribe_page)

    async def fake_who(c, page_id, token, app_secret=""):
        return who

    async def fake_sub(c, page_id, token):
        return sub
    messenger_bot.whoami, messenger_bot.subscribe_page = fake_who, fake_sub
    try:
        bot = messenger_bot.MessengerBot(creds, "", None)
        bot.start()
        for _ in range(50):
            await asyncio.sleep(0)
            if bot.status != "starting":
                break
        registered = messenger_bot.registered().get(PAGE) is bot
        bot.stop()
        return bot, registered
    finally:
        messenger_bot.whoami, messenger_bot.subscribe_page = orig


full = {"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}
bot, reg = run(start_with(full, {"ok": True, "username": PAGE}, {"ok": True}))
check("start: healthy Page registers with no warning", reg and not bot.loi_danh_tinh, (reg, bot.loi_danh_tinh))
bot, reg = run(start_with(full, {"ok": True, "username": PAGE}, {"ok": False, "error": "(200)"}))
check("start: failed subscribe still registers the Page and warns how to subscribe by hand",
      reg and "Webhooks" in bot.loi_danh_tinh and not bot.last_error, (reg, bot.loi_danh_tinh, bot.last_error))
bot, reg = run(start_with(dict(full, app_secret=""), {"ok": True}, {"ok": True}))
check("start: missing App secret refuses to start (webhook would 401 forever)",
      not reg and bot.status in ("error", "stopped") and "App secret" in bot.last_error, (reg, bot.last_error))
bot, reg = run(start_with(full, {"ok": False, "error": "App secret không khớp"}, {"ok": True}))
check("start: wrong App secret refuses to start", not reg and "App secret" in bot.last_error, bot.last_error)

# ============================================================
# 5. Webhook endpoints (TestClient)
# ============================================================
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://localhost")
settings = {"messenger": {"verify_token": "ms-vt-1"}}
orig = (main.cfgmod.read_settings, main.cfgmod.update_settings, main._ms_account_secrets, messenger_bot.handle_webhook)
main.cfgmod.read_settings = lambda: settings
main.cfgmod.update_settings = lambda p: settings.update(p) or settings
main._ms_account_secrets = lambda: [SECRET]
handled = []


async def fake_handle(payload):
    handled.append(payload)
    return 1
messenger_bot.handle_webhook = fake_handle
try:
    r = client.get("/messenger/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "ms-vt-1",
                                                "hub.challenge": "1158201444"})
    check("GET handshake echoes the challenge for the right verify token",
          r.status_code == 200 and r.text == "1158201444", (r.status_code, r.text))
    r = client.get("/messenger/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                "hub.challenge": "1"})
    check("GET handshake refuses a wrong verify token", r.status_code == 403, r.status_code)
    body = json.dumps({"object": "page", "entry": []}).encode()
    r = client.post("/messenger/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=00"})
    check("POST with a bad signature is refused and not parsed", r.status_code == 401 and not handled, r.status_code)
    r = client.post("/messenger/webhook", content=body)
    check("POST without a signature is refused", r.status_code == 401, r.status_code)
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    r = client.post("/messenger/webhook", content=body, headers={"X-Hub-Signature-256": sig})
    check("POST signed with a Messenger account's app secret is accepted",
          r.status_code == 200 and len(handled) == 1, (r.status_code, r.text))
    r = client.get("/channels/webhook-info", params={"channel": "messenger"})
    d = r.json()
    check("webhook info gives the address and verify token to paste into Meta",
          d.get("webhook_url", "").endswith("/messenger/webhook") and d.get("verify_token") == "ms-vt-1"
          and d.get("https") is False, d)
    r = client.get("/channels/webhook-info", params={"channel": "telegram"})
    check("webhook info refuses a channel without a webhook", r.status_code == 400, r.status_code)
finally:
    (main.cfgmod.read_settings, main.cfgmod.update_settings, main._ms_account_secrets,
     messenger_bot.handle_webhook) = orig

print()
if _fails:
    print(f"{len(_fails)} FAIL:")
    for f in _fails:
        print("  - " + f)
    sys.exit(1)
print("OK - test_messenger: all passed")
