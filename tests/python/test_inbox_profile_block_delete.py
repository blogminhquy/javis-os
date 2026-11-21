"""Inbox row actions that reach the platform (0.447.0): view profile, block, delete.

    python tests/run.py inbox_profile_block_delete      (no network: Graph and the Zalo CLI are faked)

Guarded, in order of what would hurt most if it broke:

  1. Delete never loses a record of something still online: when the platform refuses (a comment Facebook will
     not delete, a Zalo conversation the CLI cannot delete), nothing is deleted in Javis either.
  2. A comment thread deletes the TOP-LEVEL comment on its platform; a Zalo chat is deleted on Zalo with the right
     thread type; a Messenger or Instagram direct message is only removed from Javis (Meta has no delete API).
  3. Block: Messenger through the Page's block list with the PSID, Zalo through `friend block`; the chat is then
     taken over so the bot stays quiet and hidden. Every other channel (2026-11-20, owner: "chặn thì ở các kênh
     luôn") is blocked in Javis only: no platform call, and new messages neither count as unread nor unhide the chat.
     Unblock lifts the platform block and gives the chat back its reply mode.
  6. Leave a Zalo group (2026-11-20, owner: "nút rời nhóm ở zalo"): `group leave` with the group id, then the chat
     is removed from Javis (owner, 2026-11-21); a refused leave changes nothing; other chats are refused.
  4. Profile: Messenger name and picture (no profile link, said in words), Instagram with its instagram.com link,
     Zalo from `friend info`.
  5. The table the dashboard reads matches what the server does.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-inbox-pbd-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import conversation_actions as ca  # noqa: E402
import conversations  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


PAGE = "1234567890123"
TOKEN = "EAA" + "t" * 60
SECRET = "c" * 32
GRAPH = []
CLI = []
MODE = {"graph": "ok", "cli": "ok"}


async def fake_graph(method, path, token, params=None, client=None):
    GRAPH.append((method, path, dict(params or {})))
    if MODE["graph"] == "fail":
        return {"error": {"code": 200, "message": "Permissions error"}}
    if method == "GET" and "username" not in (params or {}).get("fields", ""):
        return {"name": "Lan Nguyễn", "profile_pic": "https://pic/x.jpg"}
    if method == "GET":
        return {"name": "Lan", "username": "lan.nguyen", "profile_pic": "https://pic/ig.jpg"}
    if method == "POST" and path.endswith("/blocked"):
        return {json.loads(params["psid"])[0]: True}
    return {"success": True}


async def fake_cli(conn, command, positionals=None, options=None, timeout=0):
    CLI.append((list(command), list(positionals or []), list(options or [])))
    if MODE["cli"] == "fail":
        return False, None, "Zalo từ chối"
    if command == ["friend", "info"]:
        uid = positionals[0]
        return True, {"changed_profiles": {uid: {"displayName": "Anh Tuấn", "zaloName": "tuan.z", "avatar": "https://a/z.jpg",
                                                 "phoneNumber": "0912345678"}}}, ""
    return True, {}, ""


ca._graph = fake_graph
zalo_cli.run_cli = fake_cli
zc.ket_noi_theo_id = lambda cid: {"id": cid, "env": {"HOME": "/tmp/zhome"}}
zalo_cli.home_of = lambda conn: "/tmp/zhome" if conn else ""

aid, err = channel_accounts.create_account({"channel": "messenger", "token": f"{PAGE} {TOKEN} {SECRET}",
                                            "external_id": PAGE, "label": "Shop"})
check("a Messenger account", bool(aid), err)


def conv(channel, account, chat, chat_type="private", name="Lan", text="Chào shop"):
    return conversations.ghi_su_kien({"channel": channel, "account_id": account, "external_chat_id": chat,
                                      "chat_type": chat_type, "sender_type": "customer", "sender_id": chat,
                                      "sender_name": name, "text": text})["conversation_id"]


cl = TestClient(main.app)

# ============================================================
# 5. The table
# ============================================================
check("capabilities by kind of chat",
      ca.capabilities({"channel": "messenger", "external_chat_id": "1"}) == ["block", "profile"]
      and ca.capabilities({"channel": "messenger", "external_chat_id": "ig:1"}) == ["profile"]
      and ca.capabilities({"channel": "messenger", "external_chat_id": "cmt:1"}) == ["delete_remote"]
      and ca.capabilities({"channel": "messenger", "external_chat_id": "igc:1"}) == ["delete_remote"]
      and ca.capabilities({"channel": "zalo_personal", "external_chat_id": "5"}) == ["block", "delete_remote", "profile"]
      and ca.capabilities({"channel": "zalo_personal", "external_chat_id": "g", "chat_type": "group"}) == ["delete_remote", "leave"]
      and ca.capabilities({"channel": "telegram", "external_chat_id": "5"}) == [])

# ============================================================
# 4. Profile
# ============================================================
dm = conv("messenger", aid, "555")
r = cl.get(f"/conversations/{dm}/profile").json()
check("Messenger profile: name and picture, no link, said in words",
      r.get("ok") and r["name"] == "Lan Nguyễn" and r["picture"] == "https://pic/x.jpg" and not r["url"] and r["note"]
      and GRAPH[-1][:2] == ("GET", "555"), (r, GRAPH[-1:]))
ig = conv("messenger", aid, "ig:777")
r = cl.get(f"/conversations/{ig}/profile").json()
check("Instagram profile: the bare id is asked, with an instagram.com link",
      r.get("ok") and GRAPH[-1][1] == "777" and r["username"] == "lan.nguyen"
      and r["url"] == "https://www.instagram.com/lan.nguyen", (r, GRAPH[-1:]))
zp = conv("zalo_personal", "zconn1", "9001", name="Tuấn")
r = cl.get(f"/conversations/{zp}/profile").json()
check("Zalo profile from friend info: name, Zalo name, avatar, phone",
      r.get("ok") and r["name"] == "Anh Tuấn" and r["username"] == "tuan.z" and r["phone"] == "0912345678"
      and CLI[-1][:2] == (["friend", "info"], ["9001"]), (r, CLI[-1:]))
tg = conv("telegram", "tg1", "42")
check("a channel without profiles is refused", cl.get(f"/conversations/{tg}/profile").status_code == 400)

# ============================================================
# 3. Block
# ============================================================
GRAPH.clear()
r = cl.post(f"/conversations/{dm}/block").json()
check("Messenger block: the Page's block list with the PSID",
      r.get("ok") and GRAPH == [("POST", f"{PAGE}/blocked", {"psid": json.dumps(["555"])})], (r, GRAPH))
d = conversations.chi_tiet(dm)
check("a blocked chat is taken over (the bot stays quiet) and marked", d["mode"] == "human" and d["metadata"].get("blocked"), d)
CLI.clear()
r = cl.post(f"/conversations/{zp}/block").json()
check("Zalo block: friend block with the user id", r.get("ok") and CLI == [(["friend", "block"], ["9001"], [])], (r, CLI))
d = conversations.chi_tiet(zp)
check("a blocked chat is hidden from the inbox", d["hidden"] == 1 and d["metadata"].get("blocked"), d)
GRAPH.clear()
CLI.clear()
for chat in (ig, conv("messenger", aid, "cmt:1_2"), conv("telegram", "tg9", "4242")):
    r = cl.post(f"/conversations/{chat}/block").json()
    d = conversations.chi_tiet(chat)
    check("no block API (Instagram, comments, Telegram): blocked in Javis only, no platform call",
          r.get("ok") and r.get("remote") is False and not GRAPH and not CLI and d["mode"] == "human"
          and d["metadata"].get("blocked") and d["hidden"] == 1, (r, GRAPH, CLI, d))
tgb = conversations.conversation_id_of("telegram", "tg9", "4242")
before = conversations.chi_tiet(tgb)["unread_count"]
conv("telegram", "tg9", "4242", text="mua không")
d = conversations.chi_tiet(tgb)
check("a new message from a blocked chat is stored but stays hidden and unread-free",
      d["hidden"] == 1 and d["unread_count"] == before and d["last_message"] == "mua không", d)
botc = conv("telegram", "tg9", "4343")
conversations.dat_che_do(botc, "ai")
cl.post(f"/conversations/{botc}/block")
r = cl.post(f"/conversations/{botc}/unblock").json()
d = conversations.chi_tiet(botc)
check("Unblock in Javis: the bot answers again, the chat is back, the mark is gone",
      r.get("ok") and d["mode"] == "ai" and d["hidden"] == 0 and not d["metadata"].get("blocked"), (r, d))
GRAPH.clear()
r = cl.post(f"/conversations/{dm}/unblock").json()
check("Unblock on Messenger: the Page's block list, DELETE with the PSID",
      r.get("ok") and r.get("remote") and GRAPH == [("DELETE", f"{PAGE}/blocked", {"psid": "555"})], (r, GRAPH))
CLI.clear()
r = cl.post(f"/conversations/{zp}/unblock").json()
check("Unblock on Zalo: friend unblock with the user id", r.get("ok") and CLI == [(["friend", "unblock"], ["9001"], [])], (r, CLI))
MODE["graph"] = "fail"
dm2 = conv("messenger", aid, "556")
r = cl.post(f"/conversations/{dm2}/block")
check("a refused block says why and changes nothing",
      r.status_code == 400 and r.json().get("error") and conversations.chi_tiet(dm2)["mode"] != "human", r.json())
MODE["graph"] = "ok"

# ============================================================
# 1-2. Delete
# ============================================================
fbc = conv("messenger", aid, "cmt:10_20")
GRAPH.clear()
r = cl.post(f"/conversations/{fbc}/delete").json()
check("Facebook comment thread: the top-level comment is deleted on Facebook, then the chat in Javis",
      r.get("ok") and r.get("remote") and GRAPH == [("DELETE", "10_20", {})] and conversations.chi_tiet(fbc) is None, (r, GRAPH))
igc = conv("messenger", aid, "igc:179")
GRAPH.clear()
cl.post(f"/conversations/{igc}/delete")
check("Instagram comment thread: the comment is deleted on Instagram", GRAPH == [("DELETE", "179", {})], GRAPH)
GRAPH.clear()
r = cl.post(f"/conversations/{dm2}/delete").json()
check("Messenger direct message: removed from Javis only, Meta not called",
      r.get("ok") and r.get("remote") is False and not GRAPH and conversations.chi_tiet(dm2) is None, (r, GRAPH))
check("its messages are gone too", conversations.tin_nhan(dm2) == [])
CLI.clear()
cl.post(f"/conversations/{zp}/delete")
check("Zalo one-to-one chat: deleted on Zalo as a user thread", CLI == [(["conv", "delete"], ["9001"], ["-t", "0"])], CLI)
zg = conv("zalo_personal", "zconn1", "g77", chat_type="group")
CLI.clear()
cl.post(f"/conversations/{zg}/delete")
check("Zalo group: deleted on Zalo as a group thread", CLI == [(["conv", "delete"], ["g77"], ["-t", "1"])], CLI)

MODE["graph"] = "fail"
fbc2 = conv("messenger", aid, "cmt:11_21")
r = cl.post(f"/conversations/{fbc2}/delete")
check("Facebook refuses: nothing deleted in Javis either", r.status_code == 400 and conversations.chi_tiet(fbc2) is not None,
      r.json())
MODE["graph"] = "ok"
MODE["cli"] = "fail"
zp2 = conv("zalo_personal", "zconn1", "9002")
r = cl.post(f"/conversations/{zp2}/delete")
check("Zalo refuses: nothing deleted in Javis either", r.status_code == 400 and conversations.chi_tiet(zp2) is not None,
      r.json())
MODE["cli"] = "ok"
r = cl.post(f"/conversations/{tg}/delete").json()
check("any other channel: removed from Javis", r.get("ok") and conversations.chi_tiet(tg) is None, r)

# ============================================================
# 6. Leave a Zalo group
# ============================================================
zg2 = conv("zalo_personal", "zconn1", "g88", chat_type="group", name="Nhóm khách sỉ")
MODE["cli"] = "fail"
r = cl.post(f"/conversations/{zg2}/leave")
d = conversations.chi_tiet(zg2)
check("Zalo refuses to let the account leave: nothing changes in Javis",
      r.status_code == 400 and d is not None and not d["metadata"].get("left") and d["hidden"] == 0, (r.json(), d))
MODE["cli"] = "ok"
CLI.clear()
r = cl.post(f"/conversations/{zg2}/leave").json()
# Owner, 2026-11-21: leaving a group also removes its chat from Javis's database (it used to stay, marked and hidden).
check("Leave group: group leave with the group id, then the chat and its messages are gone from Javis",
      r.get("ok") and r.get("deleted") and CLI == [(["group", "leave"], ["g88"], [])]
      and conversations.chi_tiet(zg2) is None and not conversations.tin_nhan(zg2), (r, CLI))
# The "X left the group" notice Zalo posts right after, and any old message handed over again, do not reopen it.
r2 = conversations.ghi_su_kien({"channel": "zalo_personal", "account_id": "zconn1", "external_chat_id": "g88",
                               "chat_type": "group", "sender_type": "customer", "sender_id": "u1", "sender_name": "Lan",
                               "text": "Javis Vũ đã rời nhóm", "external_message_id": "leave-notice"})
check("a left group is not reopened by the notice that follows the leave",
      r2.get("ok") and r2.get("trung") and r2.get("deleted")
      and not [c for c in conversations.danh_sach(limit=200) if c.get("external_chat_id") == "g88"], r2)
CLI.clear()

# ============================================================
# 7. A deleted chat stays deleted (owner, 2026-11-21: "ấn vào xoá thì nó không xoá khỏi màn hình hội thoại")
# ============================================================
# The Zalo read loop re-reads its whole buffer after a restart and tells an old message from a new one only by its row
# in the inbox, which the delete removed: the chat came back a few seconds or a restart later.
import time as _time  # noqa: E402
old_ev = {"channel": "telegram", "account_id": "tg9", "external_chat_id": "7701", "chat_type": "private",
          "sender_type": "customer", "sender_id": "7701", "sender_name": "Minh", "text": "tin cũ",
          "external_message_id": "m-old", "created_at": _time.time() - 60}
gone = conversations.ghi_su_kien(dict(old_ev))["conversation_id"]
check("delete it", cl.post(f"/conversations/{gone}/delete").json().get("ok") and conversations.chi_tiet(gone) is None)
r2 = conversations.ghi_su_kien(dict(old_ev))
r3 = conversations.ghi_su_kien(dict(old_ev, external_message_id="m-old-2", created_at=_time.time() - 30))
check("its old messages handed over again write nothing and open no conversation",
      all(x.get("ok") and x.get("trung") and x.get("deleted") for x in (r2, r3))
      and not [c for c in conversations.danh_sach(limit=200) if c.get("external_chat_id") == "7701"], (r2, r3))
r4 = conversations.ghi_su_kien(dict(old_ev, external_message_id="m-new", text="tin mới", created_at=_time.time() + 5))
d4 = conversations.chi_tiet(r4.get("conversation_id") or 0) or {}
check("a message sent after the delete opens the chat again, with only that message",
      r4.get("ok") and not r4.get("trung") and d4.get("message_count") == 1 and r4["conversation_id"] != gone, (r4, d4))
r5 = conversations.ghi_su_kien(dict(old_ev))
check("and from then on the chat is a normal one (the mark is gone)", r5.get("ok") and not r5.get("deleted"), r5)

for other in (conv("zalo_personal", "zconn1", "9003"), conv("telegram", "tg9", "-1001", chat_type="group")):
    check("only a Zalo group can be left", cl.post(f"/conversations/{other}/leave").status_code == 400 and not CLI, CLI)

print()
if _fails:
    print(f"ĐỎ: {len(_fails)}: " + "; ".join(_fails))
    sys.exit(1)
print("OK - test_inbox_profile_block_delete: all pass")
