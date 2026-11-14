"""Messenger sender names (issue 1449): a failed name lookup no longer leaves a person shown as a bare id.

    python tests/run.py messenger_names      (no network: Graph is faked)

Guarded, in order of what would hurt most if it broke:

  1. The User Profile API refused (Meta error) or giving no name: the name comes from the participants of the Page's
     conversation with that person, read with the Page token and appsecret_proof. One full turn hands that name to
     the bot as `user_name`.
  2. Both lookups fail: the name is empty, one log line carries Meta's error code and message but never the token,
     Graph is not asked again on every message during the cool-down, and it is asked again after it.
  3. A name found is cached; Instagram never takes the Messenger-only conversations path.
  4. A name or conversation title already stored is never wiped by a later message that came without a name.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextlib
import io
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-names-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import messenger_bot  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


PAGE = "1234567890123"
SECRET = "b" * 32
TOKEN = "EAA" + "n" * 60
PSID = "24000000000555"
PROOF = messenger_bot.appsecret_proof(TOKEN, SECRET)


class FakeGraph:
    """`profile`: "name" / "error" / "empty"; `conversations`: "name" / "error" / "other"."""

    def __init__(self, profile="error", conversations="name"):
        self.profile, self.conversations = profile, conversations
        self.calls = []

    def __call__(self, req: httpx.Request):
        p = req.url.path.split("/", 2)[-1]
        q = dict(req.url.params)
        self.calls.append((p, q))
        if q.get("access_token") != TOKEN or q.get("appsecret_proof") != PROOF:
            return httpx.Response(400, json={"error": {"code": 190, "message": "bad token"}})
        if p == PSID:
            if self.profile == "name":
                return httpx.Response(200, json={"first_name": "Lan", "last_name": "Nguyễn", "id": PSID})
            if self.profile == "empty":
                return httpx.Response(200, json={"id": PSID})
            return httpx.Response(400, json={"error": {
                "code": 10, "message": "(#10) Requires business_asset_user_profile_access", "error_subcode": 2018218}})
        if p == f"{PAGE}/conversations":
            if q.get("user_id") != PSID or q.get("fields") != "participants":
                return httpx.Response(400, json={"error": {"code": 100, "message": "bad query"}})
            if self.conversations == "error":
                return httpx.Response(403, json={"error": {"code": 200, "message": "(#200) Missing permission"}})
            people = [{"name": "Shop Áo", "id": PAGE}]
            if self.conversations == "name":
                people.append({"name": "Trần Thị Mai", "email": f"{PSID}@facebook.com", "id": PSID})
            return httpx.Response(200, json={"data": [{"id": "t_1", "participants": {"data": people}}]})
        return httpx.Response(404, json={"error": {"message": "unexpected " + p}})


def make_bot(answer=None):
    async def _answer(text, meta, progress):
        return {"text": "Dạ"}
    return messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "",
                                      answer or _answer, giau_trang_thai=True)


async def lookup(bot, g, psid=PSID, instagram=False):
    async with httpx.AsyncClient(transport=httpx.MockTransport(g)) as c:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            name = await (bot._name_of(c, psid, True) if instagram else bot._name_of(c, psid))
    return name, err.getvalue()


# ============================================================
# 1. Profile refused -> the conversation's participants
# ============================================================
bot, g = make_bot(), FakeGraph(profile="error", conversations="name")
name, log = run(lookup(bot, g))
check("profile refused: the name comes from the Page conversation's participants", name == "Trần Thị Mai", (name, g.calls))
check("the participant picked is the sender, not the Page", name != "Shop Áo")
check("both reads carry the Page token with appsecret_proof",
      [c[0] for c in g.calls] == [PSID, f"{PAGE}/conversations"]
      and all(c[1].get("appsecret_proof") == PROOF for c in g.calls), g.calls)
check("a name found writes no failure line", "no display name" not in log, log)
n = len(g.calls)
name, _ = run(lookup(bot, g))
check("a name found is cached: no second Graph call", name == "Trần Thị Mai" and len(g.calls) == n, g.calls[n:])

bot, g = make_bot(), FakeGraph(profile="empty", conversations="name")
name, _ = run(lookup(bot, g))
check("profile answers without a name: the participants still give one", name == "Trần Thị Mai", (name, g.calls))

bot, g = make_bot(), FakeGraph(profile="name")
name, _ = run(lookup(bot, g))
check("profile with a name: used as before, no conversations call",
      name == "Lan Nguyễn" and [c[0] for c in g.calls] == [PSID], (name, g.calls))


async def _turn():
    seen = {}

    async def answer(text, meta, progress):
        seen["meta"] = dict(meta)
        return {"text": "Dạ"}

    bot, g = make_bot(answer), FakeGraph(profile="error", conversations="name")

    async def fake_post(client, path, payload):
        return {"ok": True}

    bot._post_json = fake_post
    bot._client = httpx.AsyncClient(transport=httpx.MockTransport(g))
    with contextlib.redirect_stderr(io.StringIO()):
        await bot._on_event({"sender": {"id": PSID}, "recipient": {"id": PAGE},
                             "message": {"mid": "mid.n1", "text": "Còn hàng không?"}})
        for task in list(bot._current.values()):
            await task
        await asyncio.sleep(0)
    await bot._client.aclose()
    return seen.get("meta") or {}

meta = run(_turn())
check("a full turn hands the participant name to the bot as user_name",
      meta.get("user_name") == "Trần Thị Mai" and meta.get("chat_id") == PSID, meta)


# ============================================================
# 2. Both fail: logged with Meta's code, cool-down, retried after it
# ============================================================
bot, g = make_bot(), FakeGraph(profile="error", conversations="error")
name, log = run(lookup(bot, g))
check("both lookups fail: empty name", name == "", name)
check("the log line names Meta's code and message for each lookup",
      "10/2018218" in log and "business_asset_user_profile_access" in log and "200" in log
      and "Missing permission" in log, log)
check("the log never carries the token or the app secret", TOKEN not in log and SECRET not in log and PROOF not in log, log)
n = len(g.calls)
name, log2 = run(lookup(bot, g))
check("within the cool-down Graph is not asked again", name == "" and len(g.calls) == n and not log2, g.calls[n:])
check("the cool-down is about ten minutes", 540 <= messenger_bot.NAME_RETRY_S <= 900, messenger_bot.NAME_RETRY_S)
bot._name_retry[PSID] -= messenger_bot.NAME_RETRY_S + 1
g.conversations = "name"
name, _ = run(lookup(bot, g))
check("after the cool-down the name is looked up again and found", name == "Trần Thị Mai" and len(g.calls) > n,
      (name, g.calls[n:]))
check("a found name clears the cool-down", PSID not in bot._name_retry, bot._name_retry)


def _explode(req):
    raise httpx.ConnectError(f"boom {req.url}")

bot = make_bot()
name, log = run(lookup(bot, _explode))
check("a network error: empty name, logged by type only (the URL holds the token)",
      name == "" and "ConnectError" in log and TOKEN not in log and PROOF not in log, log)


# ============================================================
# 3. Instagram keeps its own path
# ============================================================
bot, g = make_bot(), FakeGraph(profile="error", conversations="name")
name, log = run(lookup(bot, g, instagram=True))
check("Instagram: no Messenger conversations lookup", name == "" and [c[0] for c in g.calls] == [PSID], g.calls)
check("Instagram failure is logged too", "10/2018218" in log, log)
check("pure helpers: profile and participant names",
      messenger_bot.profile_name({"username": "shop.vn"}) == "@shop.vn"
      and messenger_bot.profile_name({"first_name": "A", "last_name": "B"}) == "A B"
      and messenger_bot.profile_name(None) == ""
      and messenger_bot.participant_name({"data": [{"participants": {"data": [{"id": "1", "name": "X"}]}}]}, "1") == "X"
      and messenger_bot.participant_name({"data": []}, "1") == "" and messenger_bot.participant_name(None, "1") == "")


# ============================================================
# 4. An empty name never wipes a stored one
# ============================================================
import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402

cfg = {"id": "bot_names", "name": "Bot", "channel": "messenger", "accounts": []}
base = {"platform": "messenger", "chat_id": PSID, "chat_type": "private", "chat_title": "", "user_id": PSID,
        "account_id": "acc_names"}
chatbot_runtime.ghi_tin_khach(cfg, dict(base, user_name="Trần Thị Mai", username="Trần Thị Mai", message_id="w1"), "Chào shop")
chatbot_runtime.ghi_tin_khach(cfg, dict(base, user_name="", username="", message_id="w2"), "Còn size M không?")
cid = conversations.conversation_id_of("messenger", "acc_names", PSID)
c = conversations.chi_tiet(cid) or {}
check("a later message without a name keeps the conversation title and the customer name",
      c.get("title") == "Trần Thị Mai" and c.get("customer_name") == "Trần Thị Mai" and c.get("message_count") == 2, c)

chatbot_runtime.ghi_tin_khach(cfg, dict(base, chat_id="24000000000777", user_id="24000000000777", user_name="",
                                        username="", message_id="w3"), "Hi")
cid2 = conversations.conversation_id_of("messenger", "acc_names", "24000000000777")
chatbot_runtime.ghi_tin_khach(cfg, dict(base, chat_id="24000000000777", user_id="24000000000777", user_name="Mai",
                                        username="Mai", message_id="w4"), "Shop ơi")
c2 = conversations.chi_tiet(cid2) or {}
check("a name found later fills a conversation that started nameless", c2.get("title") == "Mai"
      and c2.get("customer_name") == "Mai", c2)

chatbot_runtime._ghi_nhom_cho("bot_names", {"chat_id": PSID, "chat_type": "private", "user_name": "Trần Thị Mai"})
chatbot_runtime._ghi_nhom_cho("bot_names", {"chat_id": PSID, "chat_type": "private", "user_name": ""})
row = next((x for x in chatbot_runtime.nhom_cho("bot_names") if x["chat_id"] == PSID), {})
check("the waiting list keeps the name too", row.get("ten") == "Trần Thị Mai" and row.get("lan") == 2, row)

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + "; ".join(_fails))
    sys.exit(1)
print("OK - test_messenger_names: all pass")
