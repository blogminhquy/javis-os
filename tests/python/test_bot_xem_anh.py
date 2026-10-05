"""The Zalo customer bot SEES the photo it is tagged on (0.74.1).

    python tests/run.py bot_xem_anh      (NO network: httpx MockTransport, fake ChatGPT)

The owner (2026-10-04) tagged the bot "Javis Vũ" on a photo in a group ("@Javis Vũ đây em") and it answered that it could only read the
caption. Two breaks, both pinned here:
  1. THE LINK WAS DROPPED. The MCP normalizes a photo as `attachment: {url: content.href, ...}` (zalo-agent-cli 1.6.2), and
     `chuan_hoa_tin` kept only a few metadata keys, so the link never reached the inbox or the bot.
  2. NO EYES. The bot was told "this message has a photo you cannot see". Now the photo is saved into the bot's brain and ChatGPT on the
     owner's plan describes it; every failure (no link, ChatGPT not signed in, bad link, error) falls back to the old honest label.
The download keeps the same rails as everywhere a chat link is fetched: https on a hostname, every redirect hop checked BEFORE it is
requested, a size cap, image content only.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bxa-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import chatbot_runtime as cr  # noqa: E402
import image_vision as iv  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


JPEG = b"\xff\xd8\xff\xe0" + b"x" * 200
URL = "https://f21-zpc.zdn.vn/jpg/7316/abc.jpg"

# ============================================================
# 1. The link survives normalization (real MCP shape)
# ============================================================
conn = {"id": "zalo-1", "label": "Javis Vũ"}
ten = {"G1": {"name": "Zoom | Javis OS", "type": "group"}}
anh = {"id": "m1", "threadId": "G1", "threadType": "group", "senderId": "777", "senderName": "Minh Quý", "type": "chat.photo",
       "text": "@Javis Vũ đây em", "timestamp": int(time.time() * 1000),
       "attachment": {"type": "chat.photo", "url": URL, "description": "@Javis Vũ đây em"}}
ev = zc.chuan_hoa_tin(conn, anh, ten)
check("photo with caption: the link is kept in metadata", ev["message_type"] == "image" and ev["metadata"].get("image_url") == URL, ev)
tron = zc.chuan_hoa_tin(conn, {k: v for k, v in anh.items() if k != "attachment"} | {"id": "m2", "text": URL}, ten)
check("bare photo (link as text, no attachment): the link is still found", tron["metadata"].get("image_url") == URL, tron["metadata"])
chu = zc.chuan_hoa_tin(conn, {"id": "m3", "threadId": "G1", "type": "webchat", "text": "xem https://x.vn/a.jpg nhé",
                              "timestamp": anh["timestamp"]}, ten)
check("a text message never gets an image link", "image_url" not in chu["metadata"], chu["metadata"])
http = zc.chuan_hoa_tin(conn, anh | {"id": "m4", "attachment": {"url": "http://f21.zdn.vn/a.jpg"}, "text": "cap"}, ten)
check("a plain http link is not kept", "image_url" not in http["metadata"], http["metadata"])

# ============================================================
# 2. The link reaches the bot (Transport.xu_ly, private chat)
# ============================================================
GOT = []


async def answer_fn(text, meta, progress):
    GOT.append((text, dict(meta)))
    return {"im_lang": True}

t = zp.Transport("zalo-1", [], answer_fn)
zc.chu_vua_nhan_tay = lambda conn_id, thread: False
priv = zc.chuan_hoa_tin(conn, anh | {"threadId": "U9", "threadType": "dm"}, {"U9": {"name": "Quý", "type": "user"}})
asyncio.run(t.xu_ly(priv))
check("the bot is called with the caption, co_anh and the link", GOT and GOT[0][0] == "@Javis Vũ đây em"
      and GOT[0][1].get("co_anh") is True and GOT[0][1].get("image_url") == URL, GOT)

conv = {"id": 1, "channel_account_id": "zalo_personal:zalo-1", "external_chat_id": "G1", "chat_type": "group", "title": "Zoom",
        "channel": "zalo_personal"}
mm = cr.manual_meta(conv, {"sender_id": "777", "sender_name": "Quý", "external_message_id": "m1", "created_at": 1.0,
                           "message_type": "image", "metadata": {"image_url": URL}})
check("owner's 'reply for me' from the inbox carries the link too", mm.get("co_anh") is True and mm.get("image_url") == URL, mm)

# ============================================================
# 3. The photo goes INTO the chat (0.81.0): saved in the bot's brain, returned as a path for the bot's own model.
#    No ChatGPT describing it any more; every failure falls back to the honest label.
# ============================================================
brain = Path(tempfile.mkdtemp(prefix="javis-bxa-brain-"))
cr._deps["brain_root"] = lambda b: str(brain)
CFG = {"id": "bot1", "brain": "Bot Brain"}
HTTP = []


def cdn(request):
    HTTP.append(str(request.url))
    u = str(request.url)
    if "redirect" in u:
        return httpx.Response(302, headers={"location": "https://127.0.0.1/steal.jpg"})
    if "big" in u:
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"x" * (iv.image_gen.MAX_REF_BYTES + 10))
    if "html" in u:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>")
    if "gone" in u:
        return httpx.Response(404)
    return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)


mt = httpx.MockTransport(cdn)
iv.httpx = types.SimpleNamespace(AsyncClient=lambda **kw: httpx.AsyncClient(transport=mt, **kw), Timeout=httpx.Timeout)
DESCRIBED = []


async def must_not_describe(*a, **k):
    DESCRIBED.append(a)
    return {"ok": True, "text": "x"}

iv.describe_images = must_not_describe
META = {"co_anh": True, "image_url": URL, "chat_id": "G1", "message_id": "m1"}
LABEL = cr._KEM_ANH


def see(meta, text="[Minh Quý] @Javis Vũ đây em"):
    HTTP.clear()
    return asyncio.run(cr.anh_cho_bot(text, meta, CFG))


out, paths = see(META)
saved = list((brain / "attachments" / "zalo" / "G1").glob("m1.*"))
check("the photo is saved into the bot's brain under attachments/zalo/<chat>", len(saved) == 1 and saved[0].read_bytes() == JPEG, saved)
check("the photo path is returned for the bot's own model, the caption kept as the text",
      paths == [str(saved[0].resolve())] and out == "[Minh Quý] @Javis Vũ đây em", (out, paths))
check("no second model describes the photo (ChatGPT is not called)", DESCRIBED == [])
see(META)
check("the same message is not downloaded twice", HTTP == [], HTTP)

check("a text message is untouched", see({"chat_id": "G1"}, "xin chào") == ("xin chào", []))
o, ps = see({"co_anh": True, "chat_id": "G1", "message_id": "m9"})
check("no link: the honest label, no photo", o.startswith(LABEL) and ps == [])
for tag in ("redirect", "big", "html", "gone"):
    o, ps = see(META | {"message_id": "b-" + tag, "image_url": f"https://f9.zdn.vn/{tag}.jpg"})
    check(f"bad link ({tag}): the honest label, nothing saved, no internal request",
          o.startswith(LABEL) and ps == [] and not list((brain / "attachments" / "zalo" / "G1").glob(f"b-{tag}.*"))
          and not any("127.0.0.1" in u for u in HTTP), HTTP)
o, ps = see(META | {"message_id": "h1", "image_url": "http://f9.zdn.vn/a.jpg"})
check("http link refused before any request", o.startswith(LABEL) and HTTP == [] and ps == [])
see(META | {"chat_id": "../../etc", "message_id": "..\\x"})
check("chat and message ids cannot climb out of attachments/zalo",
      all(p.resolve().is_relative_to((brain / "attachments" / "zalo").resolve()) for p in brain.rglob("*.jpg")))

# ============================================================
# 4. Both reply paths put the photo into the turn
# ============================================================
src = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("the live reply and the inbox 'reply for me' both attach the photos to the turn",
      src.count("= await anh_cho_bot(text_engine,") == 2 and 'cfg["_anh"]' in src and "text_engine = gan_nhan_anh(" not in src)
for f in (Path(__file__), SERVER / "image_vision.py"):
    check(f"no em dash in {f.name}", chr(0x2014) not in f.read_text(encoding="utf-8"))

if fails:
    print("\nFAIL - test_bot_xem_anh: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_bot_xem_anh: tất cả pass")
