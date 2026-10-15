"""Per-chat exception on a personal Zalo bot, end to end (0.172.0).

    python tests/run.py zalo_ngoai_le      (no network, fake MCP)

The same bot answers a parent at its own level ("Read only") and the owner's mother at the level of her
exception ("Full power"), through the real read loop, Transport and bot runtime. Her exception also sets her own
wait (10 s) while everyone else keeps the channel default (`CHO_KHACH_IM`).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpngoaile-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402,F401
import channels  # noqa: E402,F401
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Zalo của tôi", "connector_id": "zalo"}
GUI, KHO_TIN, LUOT = [], [], []
_id = [0]


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": t, "name": t, "type": "user"} for t in ("u_me", "u_ph1")]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.start = lambda: True      # no background read loop racing the manual reads below


async def _engine(text, meta, progress, *, channel="", bot=None, **_):
    LUOT.append({"chat": (meta or {}).get("chat_id"), "text": text, "muc": (bot or {}).get("muc_quyen"),
                 "prompt": chatbot_runtime.build_bot_prompt(bot)})
    return {"text": "Dạ con đây ạ", "files": []}


chatbot_runtime.wire(answer=_engine, brain_root=lambda b: tempfile.mkdtemp(prefix="brain-"),
                     read_agent=lambda br, slug: ({"name": "Trợ lý", "role": "Trợ lý trung tâm"}, "Trả lời ngắn."))


def tin(thread, text, giay_truoc):
    _id[0] += 1
    return {"threadId": thread, "from": thread, "type": "text", "text": text, "id": f"m{_id[0]}",
            "ts": int((time.time() - giay_truoc) * 1000), "threadType": 0}


async def doc(*ds):
    KHO_TIN.extend(ds)
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.3)


async def xa(giay_sau):
    zc.xa_hang_cho("zalo-1", time.time() + giay_sau)
    await asyncio.sleep(0.3)


bid, err = chatbot_store.create_bot({"name": "Trợ lý Zalo", "agent_slug": "tro-ly", "brain": "b",
                                     "account_ids": ["zalo-1"]})
ok, loi = chatbot_store.update_bot(bid, {"xac_nhan_ngoai_le": True, "ngoai_le": json.dumps(
    [{"account_id": "zalo-1", "chat_id": "u_me", "ten": "Mẹ", "muc_quyen": "full", "cho_giay": 10}])})


async def chay():
    check("(setup) read-only bot on personal Zalo with one exception for her chat",
          bid and ok and chatbot_store.get_bot(bid)["muc_quyen"] == "suggest", (err, loi))
    st, e = chatbot_runtime.start_bot(bid)
    check("(setup) bot running", st and zc.co_bot("zalo-1"), e)
    check("default wait is the channel's", zc.CHO_KHACH_IM == 5)

    # A parent and the mother write at the same time; the parent was quiet 6 s, the mother too.
    await doc(tin("u_ph1", "Cho em hỏi lịch học", 6), tin("u_me", "Con ơi sửa giúp mẹ file này", 6))
    check("the parent (default 5 s wait, quiet 6 s) is answered right after the read",
          [x["chat"] for x in LUOT] == ["u_ph1"], LUOT)
    check("the mother (own 10 s wait, quiet 6 s) is still waiting", ("zalo-1", "u_me") in zc._GOM)
    check("a chat waiting on its own exception keeps the fast read", zc._nhip_cua("zalo-1") == zc.NHIP_NHANH)
    await xa(5)
    check("after 10 s of quiet she is answered once", [x["chat"] for x in LUOT] == ["u_ph1", "u_me"], LUOT)

    by = {x["chat"]: x for x in LUOT}
    check("CANARY: the parent's turn runs at the bot's level (Read only)", by["u_ph1"]["muc"] == "suggest", by)
    check("CANARY: her turn runs at her exception's level (Full power)", by["u_me"]["muc"] == "full", by)
    check("her prompt states the level; the parent's does not",
          "QUYỀN CỦA CUỘC CHAT NÀY" in by["u_me"]["prompt"] and "QUYỀN CỦA CUỘC CHAT NÀY" not in by["u_ph1"]["prompt"])
    pm = by["u_me"]["prompt"]
    check("CANARY: the exception line comes AFTER the personal-Zalo 'stay silent on family matters' paragraph, "
          "so her messages are not dropped as family chat",
          "Kênh này là Zalo CÁ NHÂN" in pm and pm.index("QUYỀN CỦA CUỘC CHAT NÀY") > pm.index("Kênh này là Zalo CÁ NHÂN")
          and "đừng im chỉ vì đó là chuyện riêng" in pm, pm[-500:])
    check("both got a reply in their own chat", sorted(g["threadId"] for g in GUI) == ["u_me", "u_ph1"], GUI)
    check("the bot record is still Read only", chatbot_store.get_bot(bid)["muc_quyen"] == "suggest")

    # Removing the exception takes effect on the next message, no restart.
    chatbot_store.update_bot(bid, {"ngoai_le": "[]"})
    LUOT.clear()
    await doc(tin("u_me", "Mẹ hỏi thêm", 6))
    check("exception removed: her chat falls back to the bot's level and the default wait",
          [(x["chat"], x["muc"]) for x in LUOT] == [("u_me", "suggest")], LUOT)
    chatbot_runtime.stop_bot(bid)


asyncio.run(chay())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
