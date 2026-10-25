"""Bot inbox tags and the new filters (owner, 2026-10-25).

    python tests/run.py inbox_tags      (no network)

The owner asked for customer tags like Pancake's coloured chips, a filter for conversations where the customer left a
phone number or email, and (from the Pancake screenshots) "waiting longest" for chats needing a reply. This file pins
the server side:
  1. `find_contact` reads Vietnamese mobile numbers in every usual spelling and emails, and nothing else.
  2. Writing a CUSTOMER message records the contact on its conversation; a bot or owner message never does.
  3. An existing store (no `contact` column, no tag tables) is upgraded in place and scanned once, old data intact.
  4. Tags: create (name + colour from the palette), duplicate names refused ignoring case, rename, recolour, delete
     (comes off every conversation); put on / take off a conversation.
  5. `danh_sach` filters by tag and by has-contact, sorts "waiting longest", and every row carries its tags;
     `dem_bo_loc` counts has-contact.
  6. The routes, including GET /conversations/tags not being swallowed by /conversations/{conv_id}.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-inbox-tags-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

# ---- 1. finding a phone number or email in a message ----
cases = {
    "0912345678": "0912345678",
    "số em 0912 345 678 nha": "0912345678",
    "0912.345.678": "0912345678",
    "gọi 0912-345-678.": "0912345678",
    "+84 912345678": "0912345678",
    "84912345678": "0912345678",
    "(+84) 912 345 678": "0912345678",
    "mail em: Lan.Nguyen@Gmail.com nhé": "lan.nguyen@gmail.com",
    "0987654321 hoặc a@b.vn": "0987654321",
    "đơn 109123456789 giao chưa": "",          # digits glued to more digits: an order id, not a phone
    "id 1792912875": "",                       # timestamp
    "0912345": "",                             # too short
    "0212345678": "",                          # landline prefix, not a mobile
    "giá 350k ship 30k": "",
    "": "",
    None: "",
}
for text, want in cases.items():
    got = conversations.find_contact(text)
    check(f"find_contact({text!r}) == {want!r}", got == want, got)


def msg(chat, text, sender="customer", kind="private", title="", acc="zp1", ts=None):
    ev = {"channel": "zalo_personal", "account_id": acc, "account_name": "Nick", "external_chat_id": chat,
          "chat_type": kind, "chat_title": title, "sender_type": sender,
          "sender_id": ("u" + chat) if sender == "customer" else "", "sender_name": "Khách " + chat, "text": text}
    if ts:
        ev["created_at"] = ts
    r = conversations.ghi_su_kien(ev)
    assert r["ok"], r
    return r["conversation_id"]


# ---- 2. writing messages records the contact ----
a = msg("a", "chào shop", ts=1000)
check("no contact yet", conversations.chi_tiet(a)["contact"] == "")
msg("a", "Bot: số shop 0911111111 nhé", sender="ai", ts=1001)
check("a phone in a BOT message does not count", conversations.chi_tiet(a)["contact"] == "")
msg("a", "số em 0912 345 678", ts=1002)
check("a phone in the customer's message is recorded", conversations.chi_tiet(a)["contact"] == "0912345678")
msg("a", "ok cảm ơn", ts=1003)
check("a later message without one keeps it", conversations.chi_tiet(a)["contact"] == "0912345678")
b = msg("b", "email em là b@shop.vn", ts=1004)
c = msg("c", "hỏi giá", ts=1005)
g = msg("g", "ai gọi 0987654321 với", kind="group", title="Nhóm sỉ", ts=1006)
check("a group counts when a member leaves a number", conversations.chi_tiet(g)["contact"] == "0987654321")
d = msg("d", "xong rồi", ts=1007)
msg("d", "dạ shop đã gửi", sender="human", ts=1008)        # answered: not waiting

# ---- 3. an old store is upgraded in place ----
old = Path(_STATE) / "old-store.db"
db = sqlite3.connect(str(old))
old_schema = conversations._SCHEMA.split("CREATE TABLE IF NOT EXISTS inbox_tags")[0]
db.executescript(old_schema)
db.execute("INSERT INTO channel_accounts(id, channel, external_account_id, created_at, updated_at)"
           " VALUES('zalo_personal:z','zalo_personal','z',1,1)")
db.execute("INSERT INTO conversations(channel_account_id, external_chat_id, title, created_at, updated_at)"
           " VALUES('zalo_personal:z','c1','Old',1,1)")
db.execute("INSERT INTO conversations(channel_account_id, external_chat_id, title, created_at, updated_at)"
           " VALUES('zalo_personal:z','c2','Old 2',1,1)")
db.execute("INSERT INTO messages(conversation_id, sender_type, text, created_at) VALUES(1,'customer','sdt +84 912 000 111',1)")
db.execute("INSERT INTO messages(conversation_id, sender_type, text, created_at) VALUES(2,'ai','gọi 0912000222',1)")
db.commit()
db.close()
_orig = conversations.DB_PATH
conversations.DB_PATH = old
try:
    cx = conversations._conn()
    cols = {r[1] for r in cx.execute("PRAGMA table_info(conversations)").fetchall()}
    tables = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    rows = {r["title"]: r["contact"] for r in cx.execute("SELECT title, contact FROM conversations").fetchall()}
    check("old store gets the contact column and the tag tables",
          "contact" in cols and {"inbox_tags", "conversation_tags"} <= tables, (cols, tables))
    check("old customer messages are scanned once", rows.get("Old") == "0912000111", rows)
    check("an old BOT message is not a customer's contact", rows.get("Old 2") == "", rows)
    conversations.close()
    cx = conversations._conn()        # second open: nothing to add, nothing breaks
    check("reopening the upgraded store is a no-op", cx.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 2)
finally:
    conversations.close()
    conversations.DB_PATH = _orig

# ---- 4. tags ----
t1, err = conversations.create_tag("  Đã   gửi hàng ", "orange")
check("create a tag (spaces tidied)", t1 and t1["name"] == "Đã gửi hàng" and t1["color"] == "orange" and not err, (t1, err))
t2, _ = conversations.create_tag("Chăm", "nonsense")
check("an unknown colour falls back to grey", t2 and t2["color"] == "gray", t2)
check("duplicate name refused, ignoring case (Vietnamese too)", conversations.create_tag("ĐÃ GỬI HÀNG")[1] == "duplicate")
check("empty name refused", conversations.create_tag("   ")[1] == "empty")
check("names are capped", len(conversations.create_tag("x" * 99)[0]["name"]) == conversations.MAX_TAG_NAME)
check("list in creation order with counts", [t["name"] for t in conversations.list_tags()][:2] == ["Đã gửi hàng", "Chăm"]
      and all(t["count"] == 0 for t in conversations.list_tags()))
check("rename refuses another tag's name", conversations.update_tag(t2["id"], name="đã gửi hàng") == (False, "duplicate"))
check("rename to its own name in other case is fine", conversations.update_tag(t2["id"], name="CHĂM") == (True, ""))
check("recolour", conversations.update_tag(t2["id"], color="green") == (True, "")
      and [t for t in conversations.list_tags() if t["id"] == t2["id"]][0]["color"] == "green")
check("update a missing tag", conversations.update_tag(9999, name="x") == (False, "missing"))

on = conversations.set_conversation_tag(a, t1["id"], True)
check("put a tag on a conversation", [t["id"] for t in on] == [t1["id"]], on)
conversations.set_conversation_tag(a, t1["id"], True)
check("putting it on twice keeps one", len(conversations.chi_tiet(a)["tags"]) == 1)
conversations.set_conversation_tag(a, t2["id"], True)
conversations.set_conversation_tag(g, t1["id"], True)
check("tags come in the owner's order", [t["name"] for t in conversations.chi_tiet(a)["tags"]] == ["Đã gửi hàng", "CHĂM"])
check("missing conversation or tag: None", conversations.set_conversation_tag(99999, t1["id"]) is None
      and conversations.set_conversation_tag(a, 99999) is None)
check("counts follow", {t["name"]: t["count"] for t in conversations.list_tags()}.get("Đã gửi hàng") == 2)

# ---- 5. listing ----
rows = conversations.danh_sach(limit=50)
by = {r["id"]: r for r in rows}
check("every row carries its tags", by[a]["tags"] and by[c]["tags"] == [] and all("tags" in r for r in rows))
check("filter by tag", {r["id"] for r in conversations.danh_sach(tag=t1["id"])} == {a, g})
check("filter by has-contact", {r["id"] for r in conversations.danh_sach(has_contact=True)} == {a, b, g})
check("tag and has-contact combine", {r["id"] for r in conversations.danh_sach(tag=t1["id"], has_contact=True, chat_type="private")} == {a})
wait = [r["id"] for r in conversations.danh_sach(sort="waiting")]
check("waiting longest: unanswered customer messages first, oldest on top, answered after",
      wait[:4] == [a, b, c, g] and wait.index(d) > wait.index(g), wait)
nr = [r["id"] for r in conversations.danh_sach(status="need_reply", sort="waiting")]
check("need reply + waiting longest: private chats only, oldest first", nr == [a, b, c], nr)
check("default order is still newest first", [r["id"] for r in conversations.danh_sach()][0] == d)
check("facets count has-contact over the whole inbox", conversations.dem_bo_loc()["has_contact"] == 3)

check("delete a tag takes it off every conversation", conversations.delete_tag(t1["id"])
      and conversations.chi_tiet(a)["tags"] == [{"id": t2["id"], "name": "CHĂM", "color": "green"}]
      and conversations.danh_sach(tag=t1["id"]) == [])
check("delete a missing tag", not conversations.delete_tag(t1["id"]))

# ---- 6. routes ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.get("/conversations/tags")
check("GET /conversations/tags is the tag list, not a conversation id", r.status_code == 200 and "tags" in r.json()
      and r.json()["colors"][0] == "gray", r.text)
r = cl.post("/conversations/tags", data={"name": "Giao không thành công", "color": "red"})
tid = r.json().get("tag", {}).get("id")
check("POST creates", r.status_code == 200 and tid and any(t["id"] == tid for t in r.json()["tags"]), r.text)
r = cl.post("/conversations/tags", data={"name": "giao KHÔNG thành công"})
check("POST duplicate: 409 with a code", r.status_code == 409 and r.json()["code"] == "duplicate", r.text)
r = cl.post("/conversations/tags", data={"name": " "})
check("POST empty: 400", r.status_code == 400 and r.json()["code"] == "empty", r.text)
r = cl.post(f"/conversations/tags/{tid}", data={"color": "purple"})
check("POST /tags/{id} recolours and keeps the name", r.status_code == 200 and
      [t for t in r.json()["tags"] if t["id"] == tid][0] == {"id": tid, "name": "Giao không thành công", "color": "purple", "count": 0},
      r.text)
check("POST /tags/{id} missing: 404", cl.post("/conversations/tags/9999", data={"name": "x"}).status_code == 404)
r = cl.post(f"/conversations/{b}/tags", data={"tag_id": str(tid), "on": "1"})
check("put on through the API", r.status_code == 200 and [t["id"] for t in r.json()["tags"]] == [tid], r.text)
check("put on a missing conversation: 404", cl.post("/conversations/99999/tags", data={"tag_id": str(tid)}).status_code == 404)
lst = cl.get(f"/conversations?tag={tid}").json()
check("list by tag through the API, with the tag list and has-contact count",
      [x["id"] for x in lst["items"]] == [b] and lst["items"][0]["tags"][0]["name"] == "Giao không thành công"
      and any(t["id"] == tid and t["count"] == 1 for t in lst["tags"]) and lst["facets"]["has_contact"] == 3, lst.get("items"))
check("has_contact=1 through the API", {x["id"] for x in cl.get("/conversations?has_contact=1").json()["items"]} == {a, b, g})
check("sort=waiting through the API", [x["id"] for x in cl.get("/conversations?status=need_reply&sort=waiting").json()["items"]] == [a, b, c])
check("detail carries tags and contact", cl.get(f"/conversations/{b}").json()["conversation"]["contact"] == "b@shop.vn"
      and cl.get(f"/conversations/{b}").json()["conversation"]["tags"][0]["id"] == tid)
r = cl.post(f"/conversations/{b}/tags", data={"tag_id": str(tid), "on": "0"})
check("take off through the API", r.status_code == 200 and r.json()["tags"] == [], r.text)
r = cl.delete(f"/conversations/tags/{tid}")
check("DELETE removes the tag", r.status_code == 200 and all(t["id"] != tid for t in r.json()["tags"]), r.text)
check("DELETE a missing tag: 404", cl.delete(f"/conversations/tags/{tid}").status_code == 404)

# The CRM pack's customer tags (customers.tags_json) are a separate thing and keep working.
cust = conversations.chi_tiet(a)["customer_id"]
check("CRM customer tags untouched by inbox tags", conversations.dat_tag_khach(cust, ["VIP"]) == ["VIP"]
      and conversations.chi_tiet(a)["customer_tags"] == ["VIP"] and conversations.chi_tiet(a)["tags"][0]["name"] == "CHĂM")

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_inbox_tags: all pass")
