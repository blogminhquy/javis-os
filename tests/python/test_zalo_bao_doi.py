"""Personal Zalo: a slow turn sends one "give me a moment" message first (Transport._tra_loi).

    python tests/run.py zalo_bao_doi      (no network, fake MCP)

The MTM owner asked (2026-10-15): when someone would have to wait long, send them a message first ("wait a moment,
I am looking into it, I will get back to you") so they know the bot is working. Real case: a teacher sent a photo
of a solution to check and the bot stayed silent for almost a minute. The Agent cannot do this itself (one turn
yields one message, after it has finished thinking), so the channel does it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpbd-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import conversations  # noqa: E402,F401
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Toán Thầy Thành", "connector_id": "zalo"}
GUI = []
STATE = {"delay": 0.0, "reply": "Đúng rồi, hai nghiệm là x = 2 và x = 3."}


async def fake_goi(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(str(args.get("message") or args.get("text") or ""))
        return {"success": True}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = fake_goi
zc.start = lambda: True


async def _answer(text, meta, progress):
    await asyncio.sleep(STATE["delay"])
    if STATE["reply"] is None:
        return {"im_lang": True}
    return {"text": STATE["reply"], "files": []}


def ev(text, thread="u1", nhom=False, i=[0]):
    i[0] += 1
    return {"chat_type": "group" if nhom else "private", "message_type": "text", "text": text,
            "external_chat_id": thread, "sender_id": "u9" if nhom else thread, "sender_name": "Khách",
            "created_at": time.time(), "metadata": {}, "external_message_id": f"m{i[0]}", "sender_type": "customer"}


async def chay():
    zc.BAO_DOI_GIAY = 0.3
    tb = zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: {"id": "bot-x", "reply_when": "always", "ngon_ngu": "vi"})
    tb.start()

    GUI.clear()
    STATE["delay"] = 0.0
    await tb.xu_ly(ev("Check giúp em bài này"))
    check("fast turn: only the answer, no holding message", GUI == [STATE["reply"]], GUI)

    GUI.clear()
    STATE["delay"] = 0.8
    await tb.xu_ly(ev("Check giúp em bài này"))
    check("CANARY: slow turn: one holding message first, then the answer",
          len(GUI) == 2 and "đợi em một xíu" in GUI[0] and GUI[1] == STATE["reply"], GUI)

    GUI.clear()
    STATE["reply"] = None
    await tb.xu_ly(ev("ok"))
    check("slow turn that ends silent: the holding message is the only one (known trade-off)", len(GUI) <= 1, GUI)
    STATE["reply"] = "Đúng rồi, hai nghiệm là x = 2 và x = 3."

    GUI.clear()
    zc.BAO_DOI_GIAY = 0
    await tb.xu_ly(ev("Check giúp em bài này"))
    check("BAO_DOI_GIAY = 0: no holding message", GUI == [STATE["reply"]], GUI)
    zc.BAO_DOI_GIAY = 0.3
    tb.stop()

    # English bot
    tb = zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: {"id": "bot-x", "ngon_ngu": "en"})
    check("holding message follows the bot's reply language", tb._cau_bao_doi().startswith("Got it"))

    # _tra_loi directly: group message that does not call the bot gets no holding message
    tb.start()
    GUI.clear()
    out = await tb._tra_loi("Cả nhà ơi", {"chat_id": "g1"}, "g1", "group", False)
    check("untagged group turn: no holding message (the bot may still choose silence)", GUI == [] and out, (GUI, out))
    GUI.clear()
    out = await tb._tra_loi("@bot check bài", {"chat_id": "g1"}, "g1", "group", True)
    check("tagged group turn: holding message, then the answer is returned", len(GUI) == 1 and out.get("text"), (GUI, out))

    # bot switched off while waiting: no holding message
    GUI.clear()
    task = asyncio.ensure_future(tb._tra_loi("bài", {"chat_id": "u2"}, "u2", "private", True))
    await asyncio.sleep(0.05)
    tb.stop()
    await task
    check("bot switched off during the wait: no holding message", GUI == [], GUI)

    src = (SERVER / "zalo_personal_channel.py").read_text(encoding="utf-8")
    check("default wait is 20 s", "BAO_DOI_GIAY = 20" in src)
    check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())


asyncio.run(chay())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
