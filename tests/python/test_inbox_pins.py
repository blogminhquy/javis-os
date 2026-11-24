"""Pinned messages inside a customer conversation (owner, 2026-11-24, Zalo screenshots).

    python tests/run.py inbox_pins      (no network)

Pins what the bar above the messages needs from the store and the routes:
  1. Pin puts a message on top; pinning another puts that one on top; "top" moves one up; unpin takes it out.
  2. A pin reads the message live (sender, type, text, media keys) and keeps a snapshot: once the message is gone
     from the store the pin still reads right and says `gone`.
  3. Limits: a message of another chat, a missing message or chat, more than MAX_PINS.
  4. Pinning is not new activity: `updated_at`, `last_message_at` and the list order stay.
  5. The list and the poll carry only `pin_ids`, never the snapshots.
  6. The group trim keeps pinned messages.
  7. Routes: GET/POST /conversations/<id>/pins, and `pins` riding on /messages.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-inbox-pins-")
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


def msg(chat, text, sender="customer", ts=None, chat_type="private", **extra):
    ev = {"channel": "zalo_personal", "account_id": "zp1", "account_name": "Nick", "external_chat_id": chat,
          "chat_type": chat_type, "sender_type": sender, "sender_id": ("u" + chat) if sender == "customer" else "",
          "sender_name": "Khách " + chat if sender == "customer" else "Minh Quý", "text": text}
    if ts:
        ev["created_at"] = ts
    ev.update(extra)
    r = conversations.ghi_su_kien(ev)
    assert r["ok"], r
    return r["conversation_id"], r["message_id"]


def ids_of(pins):
    return [p["message_id"] for p in pins]


cid, m1 = msg("a", "Mang cho bà 1 bộ quần áo màu đỏ ở giường", ts=1000)
_, m2 = msg("a", "teqja4-gohqow-Hogrug", sender="human", ts=1001)
_, m3 = msg("a", "", ts=1002, message_type="image", metadata={"image_url": "https://f1.zdn.vn/x.jpg"})
other, m_other = msg("b", "chat khác", ts=1003)
before = conversations.chi_tiet(cid)

# ---- 1. order ----
pins, err = conversations.set_message_pin(cid, m1, "pin")
check("pin one message", err == "" and ids_of(pins) == [m1], (err, pins))
pins, _ = conversations.set_message_pin(cid, m2, "pin")
pins, _ = conversations.set_message_pin(cid, m3, "pin")
check("the newest pin goes on top", ids_of(pins) == [m3, m2, m1], ids_of(pins))
pins, err = conversations.set_message_pin(cid, m1, "top")
check("'top' moves a pin up, the rest keep their order", err == "" and ids_of(pins) == [m1, m3, m2], ids_of(pins))
pins, _ = conversations.set_message_pin(cid, m2, "pin")
check("pinning a pinned message again moves it up, no duplicate", ids_of(pins) == [m2, m1, m3], ids_of(pins))
pins, err = conversations.set_message_pin(cid, m3, "unpin")
check("unpin takes it out", err == "" and ids_of(pins) == [m2, m1], ids_of(pins))
pins, err = conversations.set_message_pin(cid, m3, "unpin")
check("unpin of a message not pinned is harmless", err == "" and ids_of(pins) == [m2, m1])
pins, err = conversations.set_message_pin(cid, m3, "top")
check("'top' of a message not pinned: not_found", err == "not_found")
check("pins_of reads the same list", ids_of(conversations.pins_of(cid)) == [m2, m1])

# ---- 2. what a pin reads ----
conversations.set_message_pin(cid, m3, "pin")
p = {x["message_id"]: x for x in conversations.pins_of(cid)}
check("a text pin: sender, type, text", p[m1]["sender_type"] == "customer" and p[m1]["sender_name"] == "Khách a"
      and p[m1]["text"].startswith("Mang cho bà") and p[m1]["message_type"] == "text" and not p[m1]["gone"], p[m1])
check("an owner pin carries the owner's name", p[m2]["sender_type"] == "human" and p[m2]["sender_name"] == "Minh Quý", p[m2])
check("a photo pin carries its image link (the bar reads 'Photo')", p[m3]["message_type"] == "image"
      and p[m3]["metadata"].get("image_url") == "https://f1.zdn.vn/x.jpg", p[m3])
check("each pin has the time it was pinned", all(x["pinned_at"] > 0 for x in p.values()))
with conversations._lock:
    db = conversations._conn()
    db.execute("DELETE FROM messages WHERE id=?", (m1,))
    db.commit()
p = {x["message_id"]: x for x in conversations.pins_of(cid)}
check("a message gone from the store: the pin keeps its snapshot and says gone", p[m1]["gone"]
      and p[m1]["text"].startswith("Mang cho bà") and p[m1]["sender_name"] == "Khách a", p.get(m1))
check("unpin of a gone message works", ids_of(conversations.set_message_pin(cid, m1, "unpin")[0]) == [m3, m2])

# ---- 3. limits ----
check("a message of another chat cannot be pinned here", conversations.set_message_pin(cid, m_other, "pin")[1] == "not_found")
check("a missing message: not_found", conversations.set_message_pin(cid, 999999, "pin")[1] == "not_found")
check("a missing chat: not_found", conversations.set_message_pin(999999, m1, "pin")[1] == "not_found")
big, _ = msg("c", "đầu", ts=2000)
many = [msg("c", f"tin {i}", ts=2001 + i)[1] for i in range(conversations.MAX_PINS + 1)]
for mid in many[:conversations.MAX_PINS]:
    conversations.set_message_pin(big, mid, "pin")
pins, err = conversations.set_message_pin(big, many[-1], "pin")
check(f"more than {conversations.MAX_PINS} pins: too_many, nothing changes", err == "too_many"
      and len(conversations.pins_of(big)) == conversations.MAX_PINS, err)
pins, err = conversations.set_message_pin(big, many[0], "pin")
check("re-pinning one already pinned at the cap still works (moves it up)", err == "" and ids_of(pins)[0] == many[0], err)

# ---- 4. not new activity ----
after = conversations.chi_tiet(cid)
check("pinning leaves updated_at and the last message alone", after["updated_at"] == before["updated_at"]
      and after["last_message_at"] == before["last_message_at"], (before["updated_at"], after["updated_at"]))

# ---- 5. the list carries ids only ----
row = conversations.chi_tiet(cid)
check("the conversation carries pin_ids, not the snapshots", row.get("pin_ids") == [m3, m2]
      and "pins" not in row["metadata"], (row.get("pin_ids"), row["metadata"]))
lst = [x for x in conversations.danh_sach(limit=50) if x["id"] == cid][0]
check("so does a list row", "pins" not in (lst.get("metadata") or {}))
conversations.set_message_pin(cid, m3, "unpin")
conversations.set_message_pin(cid, m2, "unpin")
check("no pins left: the key is gone", "pin_ids" not in conversations.chi_tiet(cid))

# ---- 6. the group trim keeps pinned messages ----
g, g1 = msg("g", "tin nhóm cần ghim", chat_type="group", ts=3000)
gmsgs = [g1] + [msg("g", f"nhóm {i}", chat_type="group", ts=3001 + i)[1] for i in range(6)]
conversations.set_message_pin(g, g1, "pin")
with conversations._lock:
    db = conversations._conn()
    db.execute("BEGIN IMMEDIATE")
    gone = conversations._cat_nhom_mot_cuoc(db, g, giu=3)
    db.execute("COMMIT")
left = {m["id"] for m in conversations.tin_nhan(g, limit=50)}
check("the trim keeps the newest and the pinned one", g1 in left and set(gmsgs[-3:]) <= left and len(left) == 4, (gone, left))
check("the pin is not gone", not conversations.pins_of(g)[0]["gone"])

# ---- 7. routes ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.post(f"/conversations/{cid}/pins", data={"message_id": str(m2), "action": "pin"})
check("POST /pins pin", r.status_code == 200 and ids_of(r.json()["pins"]) == [m2], r.text)
r = cl.get(f"/conversations/{cid}/pins")
check("GET /pins", r.status_code == 200 and ids_of(r.json()["pins"]) == [m2] and r.json()["max"] == conversations.MAX_PINS, r.text)
d = cl.get(f"/conversations/{cid}/messages?limit=40").json()
check("the first page of messages brings the pins", ids_of(d["pins"]) == [m2], d.get("pins"))
d = cl.get(f"/conversations/{cid}/messages?after={m3}&limit=40").json()
check("so does the 5-second poll (a pin from another tab shows)", ids_of(d["pins"]) == [m2], d.get("pins"))
check("a chat with no pins: an empty list", cl.get(f"/conversations/{other}/messages").json()["pins"] == [])
r = cl.post(f"/conversations/{cid}/pins", data={"message_id": str(m2), "action": "drop"})
check("a bad action: 400", r.status_code == 400, r.status_code)
r = cl.post(f"/conversations/{cid}/pins", data={"message_id": "999999", "action": "pin"})
check("a missing message: 404", r.status_code == 404, r.status_code)
check("GET /pins of a missing chat: 404", cl.get("/conversations/999999/pins").status_code == 404)
r = cl.post(f"/conversations/{big}/pins", data={"message_id": str(many[-1]), "action": "pin"})
check("over the cap: 409 too_many", r.status_code == 409 and r.json()["error"] == "too_many", r.text)
r = cl.post(f"/conversations/{cid}/pins", data={"message_id": str(m2), "action": "unpin"})
check("POST /pins unpin", r.status_code == 200 and r.json()["pins"] == [], r.text)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_inbox_pins: all pass")
