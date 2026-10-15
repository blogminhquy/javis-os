"""Personal Zalo, private chat: a photo without caption reaches the bot, and stays attached to the next text turns.

    python tests/run.py zalo_anh_rieng      (no network, fake MCP)

Real case 2026-10-15: a teacher sent a photo of a solution, then "check xem đúng chưa". The bot asked who they were;
by the time that was answered the photo was in an earlier message, so the bot said it "could not read the photo".
The teacher sent the photo again without a caption, and that one was dropped outright: in a private chat a photo
with no text never reached the bot (only groups remembered caption-less photos).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpar-")
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
LUOT = []


async def fake_goi(conn, tool, args):
    return {"success": True} if tool == "zalo_send_message" else {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = fake_goi
zc.start = lambda: True


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em xem rồi ạ.", "files": []}


def ev(thread, text="", photo="", nhom=False, i=[0]):
    i[0] += 1
    md = {"image_url": photo} if photo else {}
    return {"chat_type": "group" if nhom else "private", "message_type": "image" if photo else "text",
            "text": text or (photo if photo else ""), "external_chat_id": thread, "sender_id": "u9" if nhom else thread,
            "sender_name": "Thầy Hoàng", "created_at": time.time(), "metadata": md,
            "external_message_id": f"p{i[0]}", "sender_type": "customer"}


async def chay():
    tb = zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: {"id": "bot-x", "reply_when": "mention"})
    tb.start()
    url = "https://photo-stal-30.zdn.vn/no/jpg/abc/bai-lam.jpg"

    await tb.xu_ly(ev("t1", photo=url))
    check("CANARY: private photo without caption reaches the bot (was dropped before)", len(LUOT) == 1, LUOT)
    t, m = LUOT[0] if LUOT else ("", {})
    check("the turn carries the photo so the bot can look at it", m.get("co_anh") and m.get("image_url") == url, m)
    check("and a line saying it came without text", "không kèm lời nhắn" in t, t)

    LUOT.clear()
    await tb.xu_ly(ev("t1", text="Check xem đúng chưa"))
    t, m = LUOT[0] if LUOT else ("", {})
    check("CANARY: the next text turn still sees that photo", m.get("co_anh") and m.get("image_url") == url and m.get("anh_truoc"), m)
    check("with a line saying the photo is from an earlier message", "Kèm ảnh khách gửi lúc" in t and t.startswith("Check xem đúng chưa"), t)

    LUOT.clear()
    await tb.xu_ly(ev("t1", text="Nguyễn Duy Hoàng, giáo viên lớp 2K12"))
    check("a turn later (answering who they are) still has the photo", LUOT and LUOT[0][1].get("image_url") == url, LUOT)

    # 0.172.0: a message that QUOTES a different photo gets the quoted one, not the latest remembered photo.
    LUOT.clear()
    goc_quote = zc.anh_duoc_quote
    zc.anh_duoc_quote = lambda conn, thread, md: "https://zalo.example/anh-khac.jpg"
    try:
        await tb.xu_ly(ev("t1", text="Còn ảnh này thì sao"))
    finally:
        zc.anh_duoc_quote = goc_quote
    m = LUOT[0][1] if LUOT else {}
    check("CANARY: a quoted photo wins over the remembered one",
          m.get("image_url") == "https://zalo.example/anh-khac.jpg" and m.get("anh_quote") and not m.get("anh_truoc"), m)

    LUOT.clear()
    k = ("zalo-1", "t1")
    zc._ANH_RIENG[k] = (time.time() - zc.ANH_RIENG_GIAY - 1, url)
    await tb.xu_ly(ev("t1", text="Cảm ơn ạ"))
    check("after ANH_RIENG_GIAY the old photo is no longer attached", LUOT and not LUOT[0][1].get("co_anh"), LUOT)

    LUOT.clear()
    await tb.xu_ly(ev("t2", text="Cho em hỏi lịch học"))
    check("another chat never gets this chat's photo", LUOT and not LUOT[0][1].get("co_anh"), LUOT)

    LUOT.clear()
    await tb.xu_ly(ev("g1", photo=url, nhom=True))
    check("group photo without caption: unchanged, not answered", not LUOT, LUOT)

    LUOT.clear()
    e = ev("t3")
    e["message_type"] = "image"
    await tb.xu_ly(e)
    check("private 'image' with no link at all: still not answered (nothing to show)", not LUOT, LUOT)
    tb.stop()

    check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())


asyncio.run(chay())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
