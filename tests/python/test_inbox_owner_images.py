"""The owner sends images from the computer into a chat: `/conversations/{id}/reply-images` (2026-11-23).

    python tests/run.py inbox_owner_images

Personal Zalo only. The images are saved in the chat's brain (`attachments/sent/`), sent through the account's Zalo
session (`channels.zalo_personal.gui_anh`, stubbed here), recorded as the owner's image messages the inbox can show,
and their echo is remembered so the read loop does not record them a second time.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-owner-img-")
_BRAINS = tempfile.mkdtemp(prefix="javis-owner-img-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS
BRAIN = os.path.join(_BRAINS, "brain")
os.makedirs(BRAIN, exist_ok=True)

from fastapi.testclient import TestClient   # noqa: E402
import chatbot_store                        # noqa: E402
import channels.zalo_personal as zp         # noqa: E402
import conversations                        # noqa: E402
import main                                 # noqa: E402
import zalo_personal_channel as zc          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


sent_calls = []


async def fake_send_images(tk, chat_id, paths, chat_type="private"):
    sent_calls.append({"account": tk.get("id"), "chat": chat_id, "paths": list(paths), "type": chat_type})
    return True, ""


async def fake_send_text(*a, **kw):
    return True, ""


zp.gui_anh = fake_send_images
import channels                             # noqa: E402
_real_gui = channels.gui
channels.gui = fake_send_text

cl = TestClient(main.app, base_url="http://localhost")
bid, err = chatbot_store.create_bot({"name": "Shop bot", "agent_slug": "cskh", "brain": BRAIN, "token": "zconn1"})
check("bot created", bool(bid) and not err, err)
r = conversations.ghi_su_kien({
    "channel": "zalo_personal", "account_id": "zconn1", "account_name": "Shop", "bot_id": bid,
    "external_chat_id": "u123", "chat_type": "private", "sender_type": "customer", "sender_id": "u123",
    "sender_name": "Lan", "message_type": "text", "text": "Gửi em ảnh mẫu với"})
CID = r.get("conversation_id")
check("customer message recorded", r.get("ok") and CID, r)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
g = cl.post(f"/conversations/{CID}/reply-images", files=[("files", ("mau ao.png", PNG, "image/png")),
                                                          ("files", ("image.jpg", b"\xff\xd8\xff" + b"1" * 40, "image/jpeg"))],
            data={"text": ""})
check("two images sent", g.status_code == 200 and g.json().get("ok") and g.json().get("sent_images") == 2, g.text[:300])
check("sent through the chat's own Zalo account and thread",
      len(sent_calls) == 1 and sent_calls[0]["account"] == "zconn1" and sent_calls[0]["chat"] == "u123", sent_calls)
paths = sent_calls[0]["paths"] if sent_calls else []
sent_dir = os.path.realpath(os.path.join(BRAIN, "attachments", "sent"))
check("images saved in the bot's brain under attachments/sent",
      len(paths) == 2 and all(os.path.realpath(os.path.dirname(p)) == sent_dir and os.path.isfile(p) for p in paths), paths)
check("the file name is cleaned", paths and "mau-ao" in os.path.basename(paths[0]), paths)
check("echo remembered: the read loop will skip both images",
      zc._la_vong_anh("zconn1", "u123") and zc._la_vong_anh("zconn1", "u123") and not zc._la_vong_anh("zconn1", "u123"))

msgs = conversations.tin_nhan(CID, limit=20)
mine = [m for m in msgs if m.get("sender_type") == "human" and m.get("message_type") == "image"]
check("recorded as two image messages from the owner", len(mine) == 2, [m.get("text") for m in msgs])
check("each record points at its saved file", mine and all("downloaded to:" in m["text"] for m in mine))
check("the chat is taken over from its bot", (conversations.chi_tiet(CID) or {}).get("mode") == "human")
if paths:
    m = cl.get(f"/conversations/{CID}/media", params={"p": paths[0]})
    check("the inbox can show the sent image", m.status_code == 200 and m.content.startswith(b"\x89PNG"), m.status_code)

# With words: the images go first, then the words as a normal reply.
sent_calls.clear()
g = cl.post(f"/conversations/{CID}/reply-images", files=[("files", ("a.webp", b"RIFF0000WEBP", "image/webp"))],
            data={"text": "Mẫu này còn size M ạ"})
check("image plus message sent", g.status_code == 200 and g.json().get("ok") and not g.json().get("warning"), g.text[:300])
last = conversations.tin_nhan(CID, limit=50)[-1]
check("the message follows the image", last.get("message_type") == "text" and last.get("text") == "Mẫu này còn size M ạ", last)

# Refusals.
g = cl.post(f"/conversations/{CID}/reply-images", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
check("a non-image is refused", g.status_code == 400 and g.json().get("code") == "bad_type", g.text[:200])
g = cl.post(f"/conversations/{CID}/reply-images",
            files=[("files", (f"{i}.png", PNG, "image/png")) for i in range(11)])
check("more than 10 images refused", g.status_code == 400 and g.json().get("code") == "too_many", g.text[:200])
t = conversations.ghi_su_kien({
    "channel": "telegram", "account_id": "1", "account_name": "Bot", "external_chat_id": "777", "chat_type": "private",
    "sender_type": "customer", "sender_id": "777", "sender_name": "An", "message_type": "text", "text": "hi"})
g = cl.post(f"/conversations/{t.get('conversation_id')}/reply-images", files=[("files", ("a.png", PNG, "image/png"))])
check("a channel that cannot send images says so", g.status_code == 400 and g.json().get("code") == "unsupported", g.text[:200])
check("unknown chat: 404", cl.post("/conversations/999999/reply-images",
                                   files=[("files", ("a.png", PNG, "image/png"))]).status_code == 404)

channels.gui = _real_gui
print()
if _fails:
    print(f"RED {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("All green.")
