"""Personal Zalo: accept friend requests and keep the introduction they carry (0.149.0, server/zalo_friend_intake.py).

    python tests/run.py zalo_ket_ban      (no network, fake CLI and MCP)

The MTM owner asked (2026-10-15): when the bot accepts a friend request it must read the message sent with it and keep
it; someone who already introduced themselves is not asked again, someone who did not is asked. The message only exists
while the request is pending, so before this nobody ever saw it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpkb-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_friend_intake as fi  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Toán Thầy Thành", "connector_id": "zalo", "env": {"HOME": "/state/zalo-a"}}
CLI = []            # every CLI call: (command, positionals, home)
LUOT = []           # every bot turn (text, meta)
GUI = []
STATE = {"requests": [], "accept_fail": set()}


def req(uid, name, message, t, kind=2):
    return {"dataInfo": {"userId": uid, "displayName": name, "recommType": kind, "recommTime": t,
                         "recommInfo": {"message": message}}}


async def fake_run_cli(conn, command, positionals=None, options=None, timeout=120):
    CLI.append((list(command), list(positionals or []), conn.get("home")))
    if command == ["friend", "recommendations"]:
        return True, {"recommItems": list(STATE["requests"])}, ""
    if command == ["friend", "accept"]:
        uid = (positionals or [""])[0]
        if uid in STATE["accept_fail"]:
            return False, None, "Zalo từ chối"
        STATE["requests"] = [r for r in STATE["requests"] if r["dataInfo"]["userId"] != uid]
        return True, {"ok": True}, ""
    return False, None, "unexpected"


async def fake_goi(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": []}
    if tool == "zalo_get_messages":
        return {"messages": [], "nextCursor": "c" + str(time.time())}
    return {}


zalo_cli.run_cli = fake_run_cli
fi.ACCEPT_GAP = 0
zc._ket_noi = lambda: [dict(CONN)]
zc._goi = fake_goi
zc.start = lambda: True


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em đã nhận được thông tin rồi ạ.", "files": []}


def lam_bot(cfg):
    return zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: cfg)


async def xa():
    zc.xa_hang_cho("zalo-1", time.time() + 30)
    await asyncio.sleep(0.3)


def tin_hop_thu(uid):
    ds = conversations.danh_sach(limit=50)
    for c in (ds.get("items") if isinstance(ds, dict) else ds) or []:
        if c.get("external_chat_id") == uid:
            return [m.get("text") for m in conversations.tin_nhan(c["id"], limit=20) or []]
    return None


async def chay():
    # ---- settings -------------------------------------------------------------------------------------
    bid, err = chatbot_store.create_bot({"name": "Bot", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal"})
    check("new bot: intake OFF by default (accepting friends acts under the owner's name)",
          not err and chatbot_store.get_bot(bid).get("nhan_ket_ban") is False, err)
    chatbot_store.update_bot(bid, {"nhan_ket_ban": "1"})
    check("switch on from the form", chatbot_store.get_bot(bid)["nhan_ket_ban"] is True)
    chatbot_store.update_bot(bid, {"nhan_ket_ban": "0"})
    check("switch off again", chatbot_store.get_bot(bid)["nhan_ket_ban"] is False)
    check("Transport reads the live setting", lam_bot({"nhan_ket_ban": True}).nhan_ket_ban()
          and not lam_bot({}).nhan_ket_ban() and lam_bot({"nhan_ket_ban": "1"}).nhan_ket_ban())

    # ---- parsing ----------------------------------------------------------------------------------------
    rs = fi.received_requests({"recommItems": [req("u2", "B", "", 20), req("u9", "Gợi ý", "", 5, kind=1), req("u1", "A", "hi", 10)]})
    check("only received requests (type 2), oldest first; Zalo suggestions (type 1) ignored",
          [r["uid"] for r in rs] == ["u1", "u2"] and rs[0]["message"] == "hi", rs)

    # ---- off: nothing happens ----------------------------------------------------------------------
    tb = lam_bot({"nhan_ket_ban": False})
    tb.start()
    STATE["requests"] = [req("p1", "Hương Lan", "Chị là Lan, mẹ bạn Minh An lớp 2K10 XPT", 100)]
    await zc._nhan_loi_moi(dict(CONN))
    check("intake off: no CLI call, nothing accepted", not CLI, CLI)
    tb.stop()

    # ---- on: accept, record, hand to the bot -------------------------------------------------------------
    tb = lam_bot({"nhan_ket_ban": True})
    tb.start()
    STATE["requests"] = [req("p1", "Hương Lan", "Chị là Lan, mẹ bạn Minh An lớp 2K10 XPT", 100),
                         req("p2", "Đàm Huệ", "", 200)]
    fi._last_check.clear()
    await zc._nhan_loi_moi(dict(CONN))
    acc = [c[1][0] for c in CLI if c[0] == ["friend", "accept"]]
    check("both requests accepted, in the session of the right connection",
          acc == ["p1", "p2"] and all(c[2] == "/state/zalo-a" for c in CLI), CLI)
    h1 = tin_hop_thu("p1")
    check("CANARY: the introduction is saved in the inbox as the person's first message",
          h1 and any("Chị là Lan, mẹ bạn Minh An lớp 2K10 XPT" in (t or "") for t in h1), h1)
    h2 = tin_hop_thu("p2")
    check("no message: the inbox says so (the bot will ask)", h2 and any("không kèm lời nhắn" in (t or "") for t in h2), h2)
    await xa()
    texts = [x[0] for x in LUOT]
    check("CANARY: the bot receives the introduction (so it does not ask again)",
          any("mẹ bạn Minh An lớp 2K10 XPT" in t for t in texts), texts)
    check("and the empty one too (so it asks for what is missing)", any("không kèm lời nhắn" in t for t in texts), texts)
    check("each person gets one turn", len(LUOT) == 2, LUOT)

    # ---- throttling and repeats -------------------------------------------------------------------------
    n = len(CLI)
    await zc._nhan_loi_moi(dict(CONN))
    check("not due yet: no new Zalo call within POLL_SECONDS", len(CLI) == n)
    LUOT.clear()
    ev = fi.intro_event(dict(CONN), {"uid": "p1", "name": "Hương Lan", "message": "x", "time": 100})
    kq = conversations.ghi_su_kien(ev)
    check("same request written again is a duplicate (fixed message id), never twice", kq.get("trung") is True, kq)

    # ---- accept fails: nothing written, tried again later ----------------------------------------------
    STATE["requests"] = [req("p3", "Phụ huynh C", "Mẹ bạn Hà lớp 2K11", 300)]
    STATE["accept_fail"] = {"p3"}
    fi._last_check.clear()
    await zc._nhan_loi_moi(dict(CONN))
    check("accept refused: nothing recorded, nothing handed to the bot", tin_hop_thu("p3") is None and not LUOT)
    STATE["accept_fail"] = set()
    fi._last_check.clear()
    await zc._nhan_loi_moi(dict(CONN))
    check("next round succeeds", tin_hop_thu("p3") is not None)

    # ---- a burst is spread over rounds ---------------------------------------------------------------
    STATE["requests"] = [req(f"q{i}", f"N{i}", "", 400 + i) for i in range(fi.MAX_PER_ROUND + 3)]
    fi._last_check.clear()
    kq = await fi.run_once(dict(CONN))
    check("at most MAX_PER_ROUND accepted per round, the rest wait", kq["accepted"] == fi.MAX_PER_ROUND and kq["pending"] == fi.MAX_PER_ROUND + 3, kq)
    tb.stop()

    # ---- Zalo unreadable --------------------------------------------------------------------------------
    async def broken(conn, command, positionals=None, options=None, timeout=120):
        return False, None, "Not logged in"
    zalo_cli.run_cli = broken
    kq = await fi.run_once(dict(CONN))
    check("Zalo cannot be read: an error is returned, nothing raised", kq.get("error") == "Not logged in", kq)
    zalo_cli.run_cli = fake_run_cli

    js = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
    check("bot form has the switch and sends nhan_ket_ban", 'id="cbNhanKetBan"' in js and "nhan_ket_ban:" in js)
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    check("POST /chatbots takes nhan_ket_ban", 'nhan_ket_ban: str = Form("")' in src)
    check("no em dash", all(chr(0x2014) not in p.read_text(encoding="utf-8")
                            for p in (SERVER / "zalo_friend_intake.py", ROOT / "tests" / "python" / "test_zalo_ket_ban.py")))


asyncio.run(chay())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
