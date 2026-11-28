"""End-to-end encrypted personal Zalo chats show a sentence, not ciphertext (`zalo_e2ee`).

    python tests/run.py zalo_e2ee      (no network)

Owner report 28/11/2026: after signing a Zalo account into Javis, one private chat showed lines like "AzMo6XoI..."
instead of the messages, old and new. The chat has Zalo's end-to-end encryption on; javis-zalo signs in like Zalo Web
and never gets the keys, so only the Zalo app can read it. This file guards:
1. The detector knows a Signal-protocol ciphertext (one copied from the report) and nothing ordinary.
2. The inbox event carries the sentence and an `e2ee` mark, a quote of such a message too.
3. Such a message is never handed to the bot (it used to be, and counted as the customer asking for A.I.).
4. Rows stored before the fix are relabelled once at start-up, the chat list's last line included.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import base64
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-e2ee-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
import zalo_e2ee  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# Copied from the owner's screenshot (a PreKeySignalMessage: 03, version 0x33, protobuf field 5).
REPORTED = ("AzMo6XoI2Qow1goSlQVA+XAu8TEhg5qqAYbJZXwzy0ODJJ4baChPvHACAUibBBohBeBsWEnwsulAeMsZXVEt5sMWVjwhpo+m1T594NEkmYx1"
            "lllzCiEF0FBcy5t+Bbb8s2yjY26JC3QlUoclgbu0u2zB6qAcQ10QAhgAIiCfX1GSQJkK400fu/rEO0gjhpxcWBZzs6cESVhGujBRPuuMxcgfEYIK")
# A SignalMessage without the type byte: version 0x33, then field 1 (ratchet key).
PLAIN_SIGNAL = base64.b64encode(bytes([0x33, 0x0A, 0x21]) + bytes(range(70))).decode()

# ============================================================
# 1. The detector
# ============================================================
check("the reported line is ciphertext", zalo_e2ee.is_ciphertext(REPORTED))
check("with spaces around it too", zalo_e2ee.is_ciphertext("  " + REPORTED + "\n"))
check("a Signal message without the type byte", zalo_e2ee.is_ciphertext(PLAIN_SIGNAL))
check("ordinary text is not", not zalo_e2ee.is_ciphertext("Chào shop, còn nước mắm 500ml không ạ?"))
check("a long word is not", not zalo_e2ee.is_ciphertext("a" * 120))
check("other base64 is not", not zalo_e2ee.is_ciphertext(base64.b64encode(b"hello world, this is a plain file" * 3).decode()))
check("a link is not", not zalo_e2ee.is_ciphertext("https://example.com/" + "x" * 80))
check("a short one is not", not zalo_e2ee.is_ciphertext(REPORTED[:40]))
check("empty is not", not zalo_e2ee.is_ciphertext("") and not zalo_e2ee.is_ciphertext(None))
check("the sentence has no long dash", "\u2014" not in zalo_e2ee.placeholder() and "\u2013" not in zalo_e2ee.placeholder())

# ============================================================
# 2. The inbox event
# ============================================================
CONN = {"id": "zalo-1", "label": "Kim Khí"}
NAMES = {"u1": {"name": "Minh Quý", "type": "dm"}}


def msg(text, mid="m1", **extra):
    return dict({"msgId": mid, "threadId": "u1", "threadType": "dm", "senderId": "u-khach", "senderName": "Minh Quý",
                 "isSelf": False, "text": text, "timestamp": 1_795_000_000_000, "type": "text"}, **extra)


ev = zc.chuan_hoa_tin(CONN, msg(REPORTED), NAMES)
check("the event shows the sentence", ev["text"] == zalo_e2ee.placeholder(), ev["text"][:40])
check("and is marked e2ee", (ev.get("metadata") or {}).get("e2ee") is True)
check("it is still the customer's message", ev["sender_type"] == "customer")
ev_ok = zc.chuan_hoa_tin(CONN, msg("Em lấy 2 chai nhé", mid="m2"), NAMES)
check("an ordinary message is untouched", ev_ok["text"] == "Em lấy 2 chai nhé" and "e2ee" not in ev_ok["metadata"])
ev_q = zc.chuan_hoa_tin(CONN, msg("Dạ vâng", mid="m3", replyTo={"senderId": "u-khach", "text": REPORTED, "msgId": "m1"}),
                        NAMES)
check("a quote of an encrypted message shows the sentence",
      ev_q["metadata"]["replyTo"]["text"] == zalo_e2ee.placeholder() and ev_q["text"] == "Dạ vâng")

# ============================================================
# 3. Never handed to the bot
# ============================================================
RAN = []
zc._chay = lambda tb, e: RAN.append(e)
zc._cho_cua = lambda tb, thread: 0
zc._BOTS["zalo-1"] = object()
zc._giao_cho_bot(CONN, ev)
check("the bot does not get the encrypted message", RAN == [])
zc._giao_cho_bot(CONN, ev_ok)
check("the bot still gets an ordinary one", len(RAN) == 1)
zc._BOTS.pop("zalo-1", None)

# ============================================================
# 4. Rows stored before the fix
# ============================================================
old = dict(ev_ok, text=REPORTED, external_message_id="old-1", metadata={})
conversations.ghi_su_kien(old)
conversations.ghi_su_kien(dict(ev_ok, external_chat_id="u2", external_message_id="ok-1", text="Shop ơi"))
other = dict(ev_ok, channel="telegram", account_id="tg-1", external_chat_id="t1", external_message_id="t-1",
             text=REPORTED)
conversations.ghi_su_kien(other)
# A failure half-way rolls everything back and leaves the shared connection usable (review of #1929).
real = zalo_e2ee.is_ciphertext
calls = {"n": 0}


def flaky(text):
    calls["n"] += 1
    if calls["n"] > 1:
        raise OSError("disk full")
    return real(text)


zalo_e2ee.is_ciphertext = flaky
broken = conversations.relabel_e2ee()
zalo_e2ee.is_ciphertext = real
db = conversations._conn()
check("a failed run changes nothing", broken["messages"] == 0 and db.execute(
    "SELECT text FROM messages WHERE external_message_id='old-1'").fetchone()["text"] == REPORTED)
check("and leaves no open transaction", not db.in_transaction)
check("the inbox still writes after it", conversations.ghi_su_kien(
    dict(ev_ok, external_chat_id="u3", external_message_id="after-1", text="Còn hàng không")).get("ok") is True)
first = conversations.relabel_e2ee()
check("one stored message relabelled", first["messages"] == 1 and first["chats"] == 1, first)
row = db.execute("SELECT text, metadata_json FROM messages WHERE external_message_id='old-1'").fetchone()
check("its text is the sentence", row["text"] == zalo_e2ee.placeholder())
check("and it is marked", '"e2ee": true' in row["metadata_json"], row["metadata_json"])
last = db.execute("SELECT last_message FROM conversations WHERE external_chat_id='u1'").fetchone()
check("the chat list's last line too", last["last_message"] == zalo_e2ee.placeholder(), last["last_message"][:40])
check("another channel is left alone",
      db.execute("SELECT text FROM messages WHERE external_message_id='t-1'").fetchone()["text"] == REPORTED)
check("an ordinary message is left alone",
      db.execute("SELECT text FROM messages WHERE external_message_id='ok-1'").fetchone()["text"] == "Shop ơi")
check("runs only once", conversations.relabel_e2ee().get("done_before") is True)

print()
if _fails:
    print(f"{len(_fails)} FAIL: {_fails}")
    sys.exit(1)
print("all ok")
