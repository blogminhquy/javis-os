"""Meta connection (0.446.0): message a commenter privately, and disconnect a Page.

    python tests/run.py meta_private_reply      (no network: Graph calls are faked)

Guarded, in order of what would hurt most if it broke:

  1. A private message goes to Meta as a Private Reply (`recipient.comment_id`), never as a public comment and
     never to a made-up Messenger id.
  2. It answers the newest customer comment that has not had one yet; Meta allows one per comment, so once every
     comment in the thread had one the route refuses with `already_sent` instead of calling Meta.
  3. It is recorded twice: in the comment thread (marked with the comment it answered) and in the Messenger chat it
     opens, keyed by the id Meta returns, so the commenter's answer lands in that chat.
  4. Only a Facebook comment thread can send one; an ordinary chat is refused.
  5. Removing a Messenger account tells Meta to stop sending the Page's events, and the Page is removed even when
     Meta does not answer. Other channels never call Meta.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-meta-priv-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import conversations  # noqa: E402
import messenger_bot  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


PAGE = "1234567890123"
SECRET = "c" * 32
TOKEN = "EAA" + "t" * 60

SENT = []          # payloads that reached Graph
MODE = {"graph": "ok"}


async def fake_post_json(self, client, path, payload):
    SENT.append((path, payload))
    if MODE["graph"] == "used":
        return {"ok": False, "code": 10900, "error": messenger_bot._explain_error(10900)}
    return {"ok": True, "recipient_id": "PSID-77", "message_id": "m_priv_1"}


messenger_bot.MessengerBot._post_json = fake_post_json

aid, err = channel_accounts.create_account({"channel": "messenger", "token": f"{PAGE} {TOKEN} {SECRET}",
                                            "external_id": PAGE, "label": "Shop", "meta": {"bot_name": "Shop"}})
check("a Messenger account to work with", bool(aid), err)


def comment(cid, text, chat="cmt:555_100"):
    r = conversations.ghi_su_kien({"channel": "messenger", "account_id": aid, "account_name": "Shop",
                                   "external_chat_id": chat, "chat_type": "private", "chat_title": "Bình luận: Áo",
                                   "sender_type": "customer", "sender_id": "777", "sender_name": "Chị Lan",
                                   "text": text, "external_message_id": cid})
    return r["conversation_id"]


cl = TestClient(main.app)

# ============================================================
# 1-3. Private reply
# ============================================================
conv = comment("555_100", "Giá bao nhiêu shop?")
comment("555_101", "Còn size M không?")
r = cl.post(f"/conversations/{conv}/private-reply", data={"text": "Chào chị, em gửi giá ạ"})
j = r.json()
check("sent", r.status_code == 200 and j.get("ok"), j)
check("one Graph call, a Private Reply to the newest comment",
      len(SENT) == 1 and SENT[0][0] == f"{PAGE}/messages"
      and SENT[0][1].get("recipient") == {"comment_id": "555_101"}, SENT)
check("the text goes as a Messenger message, not a comment",
      SENT[0][1].get("message") == {"text": "Chào chị, em gửi giá ạ"} and "/comments" not in SENT[0][0], SENT)
msgs = conversations.tin_nhan(conv)
mine = [m for m in msgs if m.get("sender_type") == "human"]
check("recorded in the comment thread, marked with the comment it answered",
      len(mine) == 1 and mine[0]["metadata"].get("private_reply_to") == "555_101", mine)
dm = conversations.conversation_id_of("messenger", aid, "PSID-77")
check("the Messenger chat it opens is in the inbox, keyed by the id Meta returned",
      dm and j.get("dm_conversation_id") == dm, (dm, j.get("dm_conversation_id")))
dmc = conversations.chi_tiet(dm) or {}
check("that chat is named after the commenter", dmc.get("title") == "Chị Lan", dmc.get("title"))
check("and holds the message", [m["text"] for m in conversations.tin_nhan(dm)] == ["Chào chị, em gửi giá ạ"])

SENT.clear()
r = cl.post(f"/conversations/{conv}/private-reply", data={"text": "Thêm một tin"})
check("the next one answers the older comment that had none yet",
      r.status_code == 200 and SENT and SENT[0][1]["recipient"] == {"comment_id": "555_100"}, (r.json(), SENT))

SENT.clear()
r = cl.post(f"/conversations/{conv}/private-reply", data={"text": "Lần ba"})
check("every comment had one: refused as already_sent, Meta not called",
      r.status_code == 409 and r.json().get("code") == "already_sent" and not SENT, (r.status_code, r.json(), SENT))

conv2 = comment("555_200", "Ship Hà Nội không?", chat="cmt:555_200")
MODE["graph"] = "used"
r = cl.post(f"/conversations/{conv2}/private-reply", data={"text": "Có ạ"})
check("Meta's refusal is explained in words",
      r.status_code == 400 and "10900" in (r.json().get("error") or ""), r.json())
check("nothing recorded when Meta refused",
      not [m for m in conversations.tin_nhan(conv2) if m.get("sender_type") == "human"])
MODE["graph"] = "ok"

# ============================================================
# 4. Only a comment thread
# ============================================================
dm_conv = comment("mid.1", "Chào shop", chat="PSID-88")
SENT.clear()
r = cl.post(f"/conversations/{dm_conv}/private-reply", data={"text": "x"})
check("an ordinary chat is refused", r.status_code == 400 and r.json().get("code") == "not_comment" and not SENT, r.json())

# ============================================================
# 5. Disconnect
# ============================================================
UNSUB = []


async def fake_unsub(client, page_id, token):
    UNSUB.append((page_id, token))
    return {"ok": MODE["graph"] == "ok"}


messenger_bot.unsubscribe_page = fake_unsub
r = cl.post(f"/channels/accounts/{aid}/delete", data={"go_khoi_bot": "1"})
j = r.json()
check("removing the Page tells Meta to stop sending its events",
      j.get("ok") and UNSUB == [(PAGE, TOKEN)] and j.get("meta_unsubscribed") is True, (j, UNSUB))
check("the account is gone", channel_accounts.get_account(aid) is None)
check("past conversations stay", conversations.chi_tiet(conv) is not None)

aid2, _ = channel_accounts.create_account({"channel": "messenger", "token": f"999 {TOKEN} {SECRET}",
                                           "external_id": "999", "label": "Shop 2"})
MODE["graph"] = "down"
UNSUB.clear()
j = cl.post(f"/channels/accounts/{aid2}/delete", data={"go_khoi_bot": "1"}).json()
check("Meta not answering does not keep the Page", j.get("ok") and j.get("meta_unsubscribed") is False
      and channel_accounts.get_account(aid2) is None, j)

aid3, _ = channel_accounts.create_account({"channel": "telegram", "token": "123:abc", "label": "TG"})
UNSUB.clear()
j = cl.post(f"/channels/accounts/{aid3}/delete", data={"go_khoi_bot": "1"}).json()
check("another channel never calls Meta", j.get("ok") and not UNSUB and "meta_unsubscribed" not in j, j)

print()
if _fails:
    print(f"ĐỎ: {len(_fails)}: " + "; ".join(_fails))
    sys.exit(1)
print("OK - test_meta_private_reply: all pass")
