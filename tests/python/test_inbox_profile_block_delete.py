"""Inbox row actions that reach the platform (0.447.0): view profile, block, delete.

    python tests/run.py inbox_profile_block_delete      (no network: Graph and the Zalo CLI are faked)

Guarded, in order of what would hurt most if it broke:

  1. Delete never loses a record of something still online: when the platform refuses (a comment Facebook will
     not delete, a Zalo conversation the CLI cannot delete), nothing is deleted in Javis either.
  2. A comment thread deletes the TOP-LEVEL comment on its platform; a Zalo chat is deleted on Zalo with the right
     thread type; a Messenger or Instagram direct message is only removed from Javis (Meta has no delete API).
  3. Block: Messenger through the Page's block list with the PSID, Zalo through `friend block`; the chat is then
     taken over so the bot stays quiet. Instagram, comments and other channels are refused, never half done.
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
    if path.endswith("/blocked"):
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
      and ca.capabilities({"channel": "zalo_personal", "external_chat_id": "g", "chat_type": "group"}) == ["delete_remote"]
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
GRAPH.clear()
for chat in (ig, conv("messenger", aid, "cmt:1_2")):
    check("Instagram and comment threads cannot be blocked, Meta is not called",
          cl.post(f"/conversations/{chat}/block").status_code == 400 and not GRAPH, GRAPH)
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

print()
if _fails:
    print(f"ĐỎ: {len(_fails)}: " + "; ".join(_fails))
    sys.exit(1)
print("OK - test_inbox_profile_block_delete: all pass")
