"""The inbox's quick row: messages or comment threads, and chats with a phone number (owner, 2026-11-24: "Làm cho anh
phần lọc tin nhắn, lọc bình luận, lọc số điện thoại riêng nhé", after a screenshot of a Facebook Page whose comment
threads and Messenger chats were mixed in one list).

    python tests/run.py inbox_quick_filters      (no network)

Pinned here:
  1. `kind=comment` keeps public comment threads: Facebook `cmt:` and Instagram `igc:` on a Page, every Threads chat;
     `kind=message` keeps everything else (Messenger and Instagram DMs, Zalo chats and groups). The prefixes count on a
     Page only, an odd value is ignored.
  2. `has_phone=1` keeps chats whose customer left a phone number, not an email; the old `has_contact=1` still means
     phone or email for older callers.
  3. The Python twins (`is_comment_chat`, `is_phone_contact`, `quick_match`) agree with the SQL row by row, and the
     customer profile rule built on the same comment rule did not change.
  4. GET /conversations takes both, combines them with `who` and the other filters, pages through them, and the first
     page returns `quick_counts`: each number is exactly what tapping that choice lists.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import itertools
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-inbox-quick-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)


def say(channel, account_id, chat, text, chat_type="private"):
    r = conversations.ghi_su_kien({"channel": channel, "account_id": account_id, "external_chat_id": chat,
                                   "chat_type": chat_type, "sender_type": "customer", "sender_id": "k" + chat,
                                   "sender_name": "Customer " + chat, "text": text})
    return r["conversation_id"]


dm_plain = say("messenger", "page1", "psid1", "Tư vấn giúp em với")
dm_phone = say("messenger", "page1", "psid2", "Số em 0912 345 678 nhé")
fb_cmt = say("messenger", "page1", "cmt:111_222", "Giá bao nhiêu shop?")
fb_cmt_phone = say("messenger", "page1", "cmt:111_333", "Gọi em 0987.654.321")
ig_cmt = say("messenger", "page1", "igc:555", "Còn hàng không?")
ig_dm_mail = say("messenger", "page1", "ig:777", "Mail em là khach@example.com")
th_cmt = say("threads", "th1", "th_reply_1", "Hay quá")
zalo_phone = say("zalo_personal", "zp1", "u9", "Anh gọi 0909 111 222 giúp em")
zalo_group = say("zalo_personal", "zp1", "g1", "Cả nhà ơi", chat_type="group")
# A chat id that only looks like a comment thread on a channel without comments stays a message.
look_alike = say("telegram", "tg1", "cmt:not-a-comment", "Xin chào")

COMMENTS = {fb_cmt, fb_cmt_phone, ig_cmt, th_cmt}
MESSAGES = {dm_plain, dm_phone, ig_dm_mail, zalo_phone, zalo_group, look_alike}
PHONES = {dm_phone, fb_cmt_phone, zalo_phone}
EVERY = COMMENTS | MESSAGES
check("(setup) ten conversations", len(EVERY) == 10, EVERY)


def ids(**kw):
    return {x["id"] for x in conversations.danh_sach(limit=100, **kw)}


# ---- 1. kind ------------------------------------------------------------------------------------------------------------
check("1. kind=comment: Facebook cmt:, Instagram igc: and a Threads chat", ids(kind="comment") == COMMENTS, ids(kind="comment"))
check("1. kind=message: Messenger and Instagram DMs, Zalo chat and group, a look-alike id on another channel",
      ids(kind="message") == MESSAGES, ids(kind="message"))
check("1. an odd kind is ignored, never empties the inbox", ids(kind="x' OR 1=1--") == EVERY and ids(kind="") == EVERY)

# ---- 2. phone -----------------------------------------------------------------------------------------------------------
check("2. has_phone keeps phone numbers only (an email alone does not count)", ids(has_phone=True) == PHONES, ids(has_phone=True))
check("2. has_contact still means phone or email", ids(has_contact=True) == PHONES | {ig_dm_mail}, ids(has_contact=True))
check("2. kind and phone combine", ids(kind="comment", has_phone=True) == {fb_cmt_phone}
      and ids(kind="message", has_phone=True) == {dm_phone, zalo_phone})
check("2. they combine with the other filters", ids(kind="comment", account_ids=["threads:th1"]) == {th_cmt}
      and ids(kind="message", chat_type="group") == {zalo_group})

# ---- 3. Python twins ----------------------------------------------------------------------------------------------------
light = conversations.state_rows()
check("3. state rows carry the contact for the counts", all("contact" in r for r in light) and len(light) == 10)
by_id = {r["id"]: r for r in light}
check("3. is_comment_chat matches the SQL on every row", {i for i, r in by_id.items() if conversations.is_comment_chat(r)} == COMMENTS)
check("3. is_phone_contact matches the SQL on every row",
      {i for i, r in by_id.items() if conversations.is_phone_contact(r.get("contact"))} == PHONES)
check("3. quick_match matches danh_sach for every choice", all(
    {i for i, r in by_id.items() if conversations.quick_match(r, k, p)} == ids(kind=k, has_phone=p)
    for k, p in itertools.product(["", "message", "comment"], [False, True])))
profile = {i for i, r in by_id.items() if conversations.is_profile_chat(r)}
check("3. the customer profile rule is unchanged: private chats that are not comment threads",
      profile == {dm_plain, dm_phone, ig_dm_mail, zalo_phone, look_alike}, profile)
with conversations._lock:
    sql_profile = {r[0] for r in conversations._conn().execute(
        "SELECT c.id FROM conversations c WHERE " + conversations._PROFILE_CHAT_SQL).fetchall()}
check("3. and its SQL twin says the same", sql_profile == profile, sql_profile)

# ---- 4. the endpoint ----------------------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)


def get(query):
    d = cl.get("/conversations?limit=50" + query).json()
    return {x["id"] for x in d.get("items", [])}, d


got, d = get("&kind=comment")
check("4. kind=comment through the API", got == COMMENTS, got)
check("4. total and who counts follow the kind", d.get("total") == 4
      and sum(d["who_counts"].get(w, 0) for w in ("you", "ai", "owner", "log")) == 4, d.get("who_counts"))
got, d = get("&kind=message&has_phone=1")
check("4. kind=message&has_phone=1 through the API", got == {dm_phone, zalo_phone} and d.get("total") == 2, got)
got, _ = get("&has_contact=1")
check("4. has_contact=1 still works for older callers", got == PHONES | {ig_dm_mail}, got)
got, _ = get("&kind=bogus&has_phone=0")
check("4. an odd kind is ignored by the API too", got == EVERY, got)

_, d = get("")
check("4. the first page returns quick_counts over every other filter",
      d.get("quick_counts") == {"message": 6, "comment": 4, "phone": 3}, d.get("quick_counts"))
_, d = get("&kind=comment")
check("4. Has phone counts within the kind picked, the kinds stay whole",
      d.get("quick_counts") == {"message": 6, "comment": 4, "phone": 1}, d.get("quick_counts"))
_, d = get("&has_phone=1")
check("4. with Has phone on, the kinds count phone chats only", d.get("quick_counts") == {"message": 2, "comment": 1, "phone": 3},
      d.get("quick_counts"))
page2 = cl.get("/conversations?limit=2&offset=2&kind=comment").json()
check("4. the second page keeps the kind and carries no counts", {x["id"] for x in page2["items"]} <= COMMENTS
      and len(page2["items"]) == 2 and "quick_counts" not in page2, page2)


# Each number is what tapping that choice lists, whoever handles the chats and whatever else is on. (`total` counts
# every "who", so the rows themselves are counted.)
def total(query):
    return len(cl.get("/conversations?limit=200" + query).json().get("items") or [])


bad = []
for who in ("", "you", "ai", "owner", "log"):
    for kind in ("", "message", "comment"):
        for phone in ("", "1"):
            base = "&who=" + who
            qc = cl.get("/conversations?limit=1" + base + "&kind=" + kind + "&has_phone=" + (phone or "0")).json()["quick_counts"]
            want = {"message": total(base + "&kind=message&has_phone=" + (phone or "0")),
                    "comment": total(base + "&kind=comment&has_phone=" + (phone or "0")),
                    "phone": total(base + "&kind=" + kind + "&has_phone=1")}
            if qc != want:
                bad.append((who, kind, phone, qc, want))
check("4. every quick count equals the list that choice would show (who x kind x phone)", not bad, bad)
_, d = get("&who=you")
check("4. counts follow the who view too", sum(d["quick_counts"][k] for k in ("message", "comment"))
      == sum(1 for _ in d["items"]), (d.get("quick_counts"), len(d["items"])))

for rel in ("server/conversations.py", "server/routes/conversations.py", "tests/python/test_inbox_quick_filters.py"):
    s = (ROOT / rel).read_text(encoding="utf-8")
    check(f"{rel} has no long dash", chr(0x2014) not in s and chr(0x2013) not in s)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
