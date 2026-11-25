"""Zalo OA customer names (25/11/2026): every OA chat in the inbox showed a bare user id.

    python tests/run.py zalo_oa_names      (no network: Zalo is faked)

`_name_of` kept a failed `user/detail` call as an empty name until a restart, said nothing about why, and chats saved
that way were never named afterwards. Guarded, in order of what would hurt most if it broke:

  1. `user/detail` refused (OA package, app permission): the name comes from the OA's recent messages with that person
     (`/v2.0/oa/conversation`, `from_display_name`). One full event hands that name to the bot as `user_name`.
  2. Both fail: the name is empty, one log line carries Zalo's code, Zalo is not asked again on every message during
     the cool-down, and it is asked again after it.
  3. At start the bot names the customers the inbox already holds without a name, and their private chats; a name
     already stored (the owner's own) is never replaced.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import types

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-oa-names-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import conversations  # noqa: E402
import zalo_oa_bot as zo  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


OA_ID = "579745863508352884"
USER = "2512523625412515"
TOKEN = "a1_" + "y" * 80
RAW = zo.dump_credentials({"app_id": "4321987654321098765", "app_secret": "AbCdEfGhIjKlMnOpQrSt",
                           "oa_secret": "s" * 20, "refresh_token": "r0_" + "x" * 120, "oa_id": OA_ID,
                           "access_token": TOKEN, "expires_at": time.time() + 86400})


class FakeZalo:
    """`detail`: "name" / "error" / "empty"; `conv`: "name" / "error" / "other"."""

    def __init__(self, detail="error", conv="name", names=None):
        self.detail, self.conv, self.names = detail, conv, names or {}
        self.calls = []

    def __call__(self, req):
        path = req.url.path
        uid = str(json.loads(req.url.params.get("data") or "{}").get("user_id") or "")
        self.calls.append((path, uid))
        if req.headers.get("access_token") != TOKEN:
            return httpx.Response(200, json={"error": -216, "message": "Access token is invalid"})
        if path == "/v3.0/oa/user/detail":
            if self.detail == "error":
                return httpx.Response(200, json={"error": -235, "message": "Oa type is not allowed"})
            name = self.names.get(uid, "Chị Lan") if self.detail == "name" else ""
            return httpx.Response(200, json={"error": 0, "data": {"user_id": uid, "display_name": name}})
        if path == "/v2.0/oa/conversation":
            if self.conv == "error":
                return httpx.Response(200, json={"error": -224, "message": "package"})
            who = uid if self.conv == "name" else "999"
            return httpx.Response(200, json={"error": 0, "data": [
                {"src": 0, "from_id": OA_ID, "from_display_name": "Nước mắm Cô Ba", "to_id": who,
                 "to_display_name": "", "message": "Dạ"},
                {"src": 1, "from_id": who, "from_display_name": self.names.get(uid, "Anh Tư"), "to_id": OA_ID,
                 "message": "Giá bao nhiêu"}]})
        return httpx.Response(404, json={"error": -1})


def bot(account_id=""):
    return zo.ZaloOABot(RAW, "", None, giau_trang_thai=True, account_id=account_id)


async def lookup(b, fake, uid=USER):
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as c:
        return await b._name_of(c, uid)


def quiet(fn):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        out = fn()
    return out, buf.getvalue()


# ============================================================
# 1. Fallback to the OA's conversation
# ============================================================
check("conversation_name reads the sender side", zo.conversation_name(
    [{"from_id": USER, "from_display_name": "Chị Lan"}], USER) == "Chị Lan")
check("conversation_name reads the receiver side", zo.conversation_name(
    [{"from_id": OA_ID, "to_id": USER, "to_display_name": "Chị Lan"}], USER) == "Chị Lan")
check("conversation_name never takes the OA's own name", zo.conversation_name(
    [{"from_id": OA_ID, "from_display_name": "Nước mắm Cô Ba", "to_id": USER}], USER) == "")
check("conversation_name survives junk", zo.conversation_name({"x": 1}, USER) == ""
      and zo.conversation_name([None, "a"], USER) == "")

b = bot()
f = FakeZalo(detail="name")
check("user/detail gives the name", run(lookup(b, f)) == "Chị Lan", f.calls)
check("a name found is cached", run(lookup(b, f)) == "Chị Lan" and len(f.calls) == 1, f.calls)

b = bot()
f = FakeZalo(detail="error", conv="name")
check("user/detail refused: the name comes from the conversation", run(lookup(b, f)) == "Anh Tư", f.calls)

b = bot()
f = FakeZalo(detail="empty", conv="name")
check("user/detail with no name: the conversation too", run(lookup(b, f)) == "Anh Tư", f.calls)

# One whole event: the name reaches the bot's turn.
seen = {}


async def answer(text, meta, progress):
    seen["meta"] = meta
    return ""


async def one_event():
    b2 = zo.ZaloOABot(RAW, "", answer, giau_trang_thai=True)
    b2._client = httpx.AsyncClient(transport=httpx.MockTransport(FakeZalo(detail="error", conv="name")))
    await b2._on_event({"event_name": "user_send_text", "sender": {"id": USER}, "recipient": {"id": OA_ID},
                        "timestamp": "1700000000000", "message": {"msg_id": "n1", "text": "Còn hàng không"}})
    for _ in range(50):
        if "meta" in seen:
            break
        await asyncio.sleep(0.02)
    await b2._client.aclose()

run(one_event())
check("a full event hands the fallback name to the turn", (seen.get("meta") or {}).get("user_name") == "Anh Tư", seen)

# ============================================================
# 2. Both fail: logged, cooled down, retried
# ============================================================
b = bot()
f = FakeZalo(detail="error", conv="error")
name, log = quiet(lambda: run(lookup(b, f)))
check("both refused: empty name", name == "", name)
check("the log names Zalo's codes", "-235" in log and "-224" in log and USER in log, log)
check("the log never carries the token", TOKEN not in log, log)
n = len(f.calls)
name, _ = quiet(lambda: run(lookup(b, f)))
check("no new call during the cool-down", name == "" and len(f.calls) == n, f.calls)
b._name_retry[USER] = time.time() - 1
f.detail = "name"
check("asked again after the cool-down, and found", run(lookup(b, f)) == "Chị Lan", f.calls)
check("a found name clears the cool-down", USER not in b._name_retry)

# ============================================================
# 3. Names the inbox already holds as bare ids
# ============================================================
ACC = "acc-oa-1"


def customer_writes(uid, name=""):
    conversations.ghi_su_kien({"channel": "zalo_oa", "account_id": ACC, "account_name": "OA", "bot_id": "b1",
                               "external_chat_id": uid, "chat_type": "private", "sender_type": "customer",
                               "sender_id": uid, "sender_name": name, "text": "chào shop"})


customer_writes("1001")
customer_writes("1002")
customer_writes("1003", "Tên chủ đặt")
check("nameless_customers lists only the nameless", sorted(conversations.nameless_customers("zalo_oa", ACC)) ==
      ["1001", "1002"], conversations.nameless_customers("zalo_oa", ACC))
check("nameless_customers keeps to its account", conversations.nameless_customers("zalo_oa", "other") == [])

b = bot(ACC)
f = FakeZalo(detail="name", names={"1001": "Chị Mai", "1002": "Anh Hùng", "1003": "Tên Zalo"})


async def backfill():
    async with httpx.AsyncClient(transport=httpx.MockTransport(f)) as c:
        return await b.backfill_names(c)

n, _ = quiet(lambda: run(backfill()))
check("backfill names every nameless customer", n == 2, n)
rows = {r["external_chat_id"]: r for r in conversations.danh_sach(channel="zalo_oa", limit=50)}
check("the inbox shows the new names", rows.get("1001", {}).get("title") == "Chị Mai"
      and rows.get("1002", {}).get("title") == "Anh Hùng", {k: v.get("title") for k, v in rows.items()})
check("a stored name is never replaced", rows.get("1003", {}).get("title") == "Tên chủ đặt",
      rows.get("1003", {}).get("title"))
check("the owner-named customer was never looked up", ("/v3.0/oa/user/detail", "1003") not in f.calls, f.calls)
check("nothing left nameless", conversations.nameless_customers("zalo_oa", ACC) == [])
check("set_customer_name refuses an empty name", conversations.set_customer_name("zalo_oa", ACC, "1001", "  ") is False)
check("backfill without an account id does nothing", run(bot("").backfill_names()) == 0)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
