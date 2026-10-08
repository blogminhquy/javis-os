"""Slack and WhatsApp channels (0.71.0): control channel and customer-bot channel.

    python tests/run.py slack_whatsapp

No network. What is guarded here, in order of what would hurt most if it broke:

  1. The WhatsApp webhook is a PUBLIC URL. A POST no known app secret signed must be refused
     before anything reads it, and the GET handshake must only echo the challenge for the right
     verify token.
  2. Control channels are FAIL-CLOSED: an empty allow-list lets nobody in, strangers get a
     pairing code instead of the owner's brain.
  3. Work handed over from Slack or WhatsApp reports back there (prefix routing), not to
     Telegram where the person who asked never sees it.
  4. The Slack event filter: the bot ignores itself, ignores channel chatter it was not called
     into, answers DMs, turns "!stop" into "/stop", and never answers one message twice.
  5. Credentials typed into one field split correctly, secrets are masked on read and kept
     when the form sends an empty field.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-slackwa-"))

import channel_context  # noqa: E402
import channels  # noqa: E402
import chatbot_store  # noqa: E402
import owner_channels  # noqa: E402
import slack_bot  # noqa: E402
import whatsapp_bot  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail!r}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


# ============================================================
# 1. Credentials in one field
# ============================================================
check("Slack: two tokens split in any order",
      slack_bot.split_tokens("xapp-1-A, xoxb-2-B") == ("xoxb-2-B", "xapp-1-A"))
check("Slack: one token missing gives an empty slot",
      slack_bot.split_tokens("xoxb-only") == ("xoxb-only", ""))
cr = whatsapp_bot.split_credentials("123456789012345 " + "EAA" + "x" * 60 + " " + "a" * 32)
check("WhatsApp: phone id, token and secret told apart by shape",
      cr["phone_number_id"] == "123456789012345" and cr["access_token"].startswith("EAA")
      and cr["app_secret"] == "a" * 32, cr)

# ============================================================
# 2. Formatting
# ============================================================
m = slack_bot.md_to_mrkdwn("### Title\n**bold** [site](https://x.io)\n```**raw**```")
check("Slack mrkdwn: heading and bold become *x*, link becomes <url|text>, code untouched",
      "*Title*" in m and "*bold*" in m and "<https://x.io|site>" in m and "```**raw**```" in m, m)
w = whatsapp_bot.md_to_whatsapp("**bold** and [site](https://x.io)")
check("WhatsApp format: bold, link spelled out", w == "*bold* and site (https://x.io)", w)
check("long Slack answers split under the limit",
      all(len(c) <= slack_bot.MAX_MSG for c in slack_bot._chunks("line\n" * 3000)))

# ============================================================
# 3. Webhook signature
# ============================================================
body = b'{"object":"whatsapp_business_account"}'
secret = "f" * 32
good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
check("signature: right secret passes", whatsapp_bot.verify_signature(body, good, ["x" * 32, secret]))
check("signature: wrong secret refused", not whatsapp_bot.verify_signature(body, good, ["x" * 32]))
check("signature: no secret configured refuses everything",
      not whatsapp_bot.verify_signature(body, good, ["", None]))
check("signature: tampered body refused",
      not whatsapp_bot.verify_signature(body + b" ", good, [secret]))
check("signature: missing header refused", not whatsapp_bot.verify_signature(body, "", [secret]))


# ============================================================
# 4. Webhook routing to the bot registered for the number
# ============================================================
class FakeWA:
    def __init__(self):
        self.got = []
        self.last_error = ""

    async def _safe_message(self, msg, contacts):
        self.got.append((msg.get("id"), contacts.get(msg.get("from"))))


async def _route():
    fake = FakeWA()
    whatsapp_bot._REGISTRY["111"] = fake
    payload = {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "111"},
        "contacts": [{"wa_id": "8490", "profile": {"name": "Quy"}}],
        "messages": [{"id": "wamid.1", "from": "8490", "type": "text", "text": {"body": "hi"}}]}},
        {"value": {"metadata": {"phone_number_id": "999"},
                   "messages": [{"id": "wamid.2", "from": "1", "type": "text"}]}}]}]}
    n = await whatsapp_bot.handle_webhook(payload)
    await asyncio.sleep(0)
    whatsapp_bot._REGISTRY.pop("111", None)
    return n, fake.got

n, got = run(_route())
check("webhook: message goes to the bot of ITS phone number id only", n == 1 and got == [("wamid.1", "Quy")],
      (n, got))


# ============================================================
# 5. Owner channel: fail-closed pairing, prefix, routing
# ============================================================
settings = {"slack": {"enabled": True, "bot_token": "xoxb-1", "app_token": "xapp-1", "allow": ""},
            "whatsapp": {"enabled": True, "phone_number_id": "111", "access_token": "EAA" + "x" * 50,
                         "app_secret": "a" * 32, "allow": "84901"}}


def read_settings():
    return json.loads(json.dumps(settings))


def update_settings(patch):
    for k, v in patch.items():
        settings.setdefault(k, {}).update(v)


for ch in owner_channels.ALL:
    ch.wire(read_settings=read_settings, update_settings=update_settings)

S = owner_channels.SLACK
r = S.precheck("hello", {"user_id": "U0STRANGER", "chat_id": "D1", "user_name": "Kim"})
check("Slack control: empty allow-list blocks everyone (fail-closed)", r is not None and "reply" in r, r)
code = S.queue.get("U0STRANGER", {}).get("ma", "")
check("stranger gets a 4-digit pairing code in the reply", len(code) == 4 and code in r["reply"], r)
check("asking again within 10 minutes stays quiet",
      S.precheck("again", {"user_id": "U0STRANGER", "chat_id": "D1"}) == {"reply": ""})
S.allow("U0STRANGER", True)
check("after Allow the same user passes", S.precheck("hi", {"user_id": "U0STRANGER", "chat_id": "D1"}) is None)
check("allow writes the settings", "U0STRANGER" in settings["slack"]["allow"])
check("allowed by SENDER id, so a channel id is not a key",
      S.precheck("hi", {"user_id": "U0OTHER", "chat_id": "D1"}) is not None)

W = owner_channels.WHATSAPP
check("WhatsApp control: allowed number passes", W.precheck("hi", {"user_id": "84901", "chat_id": "84901"}) is None)
check("WhatsApp control: other number gets a code",
      "reply" in (W.precheck("hi", {"user_id": "1555", "chat_id": "1555"}) or {}))
check("by_prefix finds the channel and raw id", owner_channels.by_prefix("whatsapp:84901") == (W, "84901"))
check("by_prefix ignores other prefixes", owner_channels.by_prefix("zalo:abc") == (None, ""))
check("missing() is empty when the channel can carry results", W.missing() == "")
settings["whatsapp"]["allow"] = ""
check("missing() names the gap when nobody is allowed", "WhatsApp" in W.missing())
settings["whatsapp"]["allow"] = "84901"


async def _answer_prefix():
    seen = {}

    async def fake_answer(text, meta, progress, channel=None, bot=None):
        seen.update(meta=meta, channel=channel)
        return {"text": "ok"}
    W.wire(answer=fake_answer)
    await W.answer("hi", {"chat_id": "84901"})
    return seen

seen = run(_answer_prefix())
check("answer prefixes the chat id (session, brain and owner_chat key)",
      seen["meta"]["chat_id"] == "whatsapp:84901" and seen["channel"] == "whatsapp", seen)


# ============================================================
# 6. Background results route back by prefix (main._gui_qua_kenh)
# ============================================================
import main  # noqa: E402

sent = []


async def fake_send_to(raw, text):
    sent.append((raw, text))
    return True, ""

orig = (S.send_to, W.send_to)
S.send_to, W.send_to = fake_send_to, fake_send_to
ok1 = run(main._gui_qua_kenh("slack:D123", "done"))
ok2 = run(main._tg_send_to("whatsapp:84901", "reminder"))
S.send_to, W.send_to = orig
check("loop/Kanban result for slack:... goes to Slack", ok1 == (True, "") and ("D123", "done") in sent, sent)
check("reminder for whatsapp:... goes to WhatsApp", ok2 == (True, "") and ("84901", "reminder") in sent, sent)


# ============================================================
# 7. Webhook endpoints (TestClient)
# ============================================================
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://localhost")
orig_rs = main.cfgmod.read_settings
orig_us = main.cfgmod.update_settings
main.cfgmod.read_settings = read_settings
main.cfgmod.update_settings = update_settings
settings["whatsapp"]["verify_token"] = "vt-123"
try:
    r = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "vt-123",
                                               "hub.challenge": "42"})
    check("GET handshake echoes the challenge for the right verify token", r.status_code == 200 and r.text == "42",
          (r.status_code, r.text))
    r = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                               "hub.challenge": "42"})
    check("GET handshake refuses a wrong verify token", r.status_code == 403, r.status_code)
    payload = json.dumps({"entry": []}).encode()
    r = client.post("/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": "sha256=00"})
    check("POST with a bad signature is refused", r.status_code == 401, r.status_code)
    sig = "sha256=" + hmac.new(("a" * 32).encode(), payload, hashlib.sha256).hexdigest()
    r = client.post("/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": sig})
    check("POST signed with the control number's app secret is accepted", r.status_code == 200, r.status_code)
    r = client.get("/whatsapp/status")
    d = r.json()
    check("status shows the webhook URL and verify token to paste into Meta",
          d.get("webhook_url", "").endswith("/whatsapp/webhook") and d.get("verify_token") == "vt-123", d)
finally:
    main.cfgmod.read_settings = orig_rs
    main.cfgmod.update_settings = orig_us


# ============================================================
# 8. Slack event filter
# ============================================================
class Probe(slack_bot.SlackBot):
    def __init__(self, owner=True):
        super().__init__("xoxb-1 xapp-1", "", None, giau_trang_thai=not owner)
        self.bot_id = "UBOT"
        self.dispatched = []

    async def _display_name(self, client, uid):
        return "Kim"

    async def _dispatch(self, client, chat, text, meta=None):
        self.dispatched.append((chat, text, meta.get("chat_type"), self._thread.get(chat)))

    async def _send(self, client, chat, text, reply_markup=None):
        pass


async def _events():
    p = Probe(owner=True)
    await p._on_event(None, {"type": "message", "channel": "D1", "channel_type": "im", "user": "U1",
                             "text": "hello", "ts": "1.1"})
    await p._on_event(None, {"type": "message", "channel": "D1", "channel_type": "im", "user": "U1",
                             "text": "hello", "ts": "1.1"})
    await p._on_event(None, {"type": "message", "channel": "D1", "channel_type": "im", "bot_id": "B1",
                             "text": "echo", "ts": "1.2"})
    await p._on_event(None, {"type": "message", "channel": "C1", "channel_type": "channel", "user": "U2",
                             "text": "people talking", "ts": "1.3"})
    await p._on_event(None, {"type": "app_mention", "channel": "C1", "user": "U2",
                             "text": "<@UBOT> sales today?", "ts": "1.4"})
    await p._on_event(None, {"type": "message", "channel": "C1", "channel_type": "channel", "user": "U2",
                             "text": "<@UBOT> sales today?", "ts": "1.4"})
    await p._on_event(None, {"type": "message", "channel": "D1", "channel_type": "im", "user": "U1",
                             "text": "!stop", "ts": "1.5"})
    await p._on_event(None, {"type": "message", "subtype": "message_changed", "channel": "D1",
                             "channel_type": "im", "user": "U1", "text": "edit", "ts": "1.6"})
    return p.dispatched

d = run(_events())
check("DM is answered", ("D1", "hello", "private", None) in d, d)
check("the same message is never answered twice", sum(1 for x in d if x[1] == "hello") == 1, d)
check("the bot's own messages and edits are ignored",
      not any(x[1] in ("echo", "edit") for x in d), d)
check("channel chatter without a mention is ignored by the owner bot",
      not any(x[1] == "people talking" for x in d), d)
check("a mention is answered once, in the thread, with the mention stripped",
      [x for x in d if x[0] == "C1"] == [("C1", "sales today?", "group", "1.4")], d)
check("!stop becomes /stop (Slack keeps / for its own commands)", any(x[1] == "/stop" for x in d), d)

# ============================================================
# 8b. One full turn through each transport (Graph / Slack API faked)
# ============================================================
async def _wa_turn():
    calls = []

    async def answer(text, meta, progress):
        await progress("⚙ Đang gọi: pos_statistics")
        return {"text": "**Revenue** up 12%"}

    bot = whatsapp_bot.WhatsAppBot({"phone_number_id": "111", "access_token": "EAA" + "x" * 50,
                                    "app_secret": "a" * 32}, "", answer)

    async def fake_post(client, path, payload):
        calls.append((path, payload))
        return {"ok": True}
    bot._post_json = fake_post
    await bot._on_message({"id": "wamid.9", "from": "8490", "type": "text", "text": {"body": "sales?"}},
                          {"8490": "Quy"})
    for task in list(bot._current.values()):
        await task
    if bot._client:
        await bot._client.aclose()
    return calls

calls = run(_wa_turn())
texts = [c[1]["text"]["body"] for c in calls if c[1].get("type") == "text"]
check("WhatsApp turn: read receipt with typing indicator sent first",
      calls and calls[0][1].get("status") == "read" and "typing_indicator" in calls[0][1], calls[:1])
check("WhatsApp turn: answer goes to the sender, Markdown converted, tool trail attached",
      texts and texts[-1].startswith("*Revenue* up 12%") and "pos_statistics" in texts[-1], texts)


async def _slack_turn():
    calls = []

    async def answer(text, meta, progress):
        await progress("⚙ Đang gọi: pos_statistics")
        return {"text": "**Revenue** up 12%"}

    bot = slack_bot.SlackBot("xoxb-1 xapp-1", "", answer)

    async def fake_api(client, method, token=None, **payload):
        calls.append((method, payload))
        return {"ok": True, "ts": "9.9"}
    bot._api = fake_api
    bot._thread["C1"] = "1.4"
    await bot._handle_turn(None, "C1", "sales?", {"chat_type": "group"})
    return calls

calls = run(_slack_turn())
posts = [c[1] for c in calls if c[0] == "chat.postMessage"]
updates = [c[1] for c in calls if c[0] == "chat.update"]
check("Slack turn: status message, then the answer, both in the thread",
      len(posts) == 2 and all(p.get("thread_ts") == "1.4" for p in posts), posts)
check("Slack turn: answer converted to mrkdwn", posts and posts[-1]["text"] == "*Revenue* up 12%", posts)
check("Slack turn: status message becomes the tool trail",
      updates and "pos_statistics" in updates[-1]["text"], updates)

# ============================================================
# 9. Registry, store and prompt
# ============================================================
check("both channels in the registry as bot channels with a token account",
      {"slack", "whatsapp"} <= set(channels.bot_token_ids()))
check("WhatsApp declares no groups, Slack does",
      channels.spec("slack").nl("nhom") and not channels.spec("whatsapp").nl("nhom"))
check("both can send text from the inbox (owner takeover)",
      channels.spec("slack").nl("tra_loi_tu_javis") and channels.spec("whatsapp").nl("tra_loi_tu_javis"))
check("chatbot store accepts Slack channel ids", chatbot_store._CHAT_ID_RE.match("C0ABC1234") is not None)
for src, prefix in (("slack", "slack:"), ("whatsapp", "whatsapp:")):
    b = channel_context.build_channel_block(src, {"chat_id": prefix + "X1", "user_name": "Kim",
                                                  "chat_type": "private"})
    check(f"{src} prompt keeps the prefix so results come back", f"`{prefix}`" in b and prefix + "X1" in b)
    check(f"{src} prompt forbids tables", "bảng" in b)
    check(f"{src} prompt has no long dashes", b.count("—") + b.count("–") == 0)
check("WhatsApp prompt warns about the 24-hour window",
      "24 GIỜ" in channel_context.build_channel_block("whatsapp", {"chat_id": "whatsapp:1"}))

# ============================================================
# 10. Settings: masked on read, kept when the form sends nothing
# ============================================================
import config as cfgmod  # noqa: E402

# Back to the real (temp-dir) settings: saving restarts the channel, and with the fake settings
# above it would be "enabled" and try to reach Slack. The real ones stay disabled.
for ch in owner_channels.ALL:
    ch.wire(read_settings=cfgmod.read_settings, update_settings=cfgmod.update_settings)
cfgmod.update_settings({"slack": {"bot_token": "xoxb-real-1234", "app_token": "xapp-real-5678"}})
r = client.post("/settings", data={"section": "slack", "data": json.dumps(
    {"enabled": False, "allow": "U1, U2", "bot_token": "", "app_token": "••••5678"})})
c = cfgmod.read_settings().get("slack", {})
check("empty or masked secret fields keep the saved tokens",
      c.get("bot_token") == "xoxb-real-1234" and c.get("app_token") == "xapp-real-5678", c)
check("allow-list normalised", c.get("allow") == "U1, U2", c.get("allow"))
check("a disabled channel does not start a connection", owner_channels.SLACK.bot is None)
g = client.get("/settings").json().get("slack", {})
check("GET /settings masks Slack tokens", g.get("bot_token", "").startswith("••••") and g.get("bot_token_set"), g)
r = client.post("/settings", data={"section": "whatsapp", "data": json.dumps(
    {"phone_number_id": "+1 555-0100 999", "access_token": "EAAnew"})})
c = cfgmod.read_settings().get("whatsapp", {})
check("phone number id keeps digits only, new token saved",
      c.get("phone_number_id") == "15550100999" and c.get("access_token") == "EAAnew", c)

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s) failed")
    sys.exit(1)
print("\nOK - test_slack_whatsapp: all pass")
