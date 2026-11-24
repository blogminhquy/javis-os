"""The inbox + button: the owner sends an image or file to a customer (2026-11-24).

    python tests/run.py inbox_send_file      (no network: the channel sends are faked)

Guarded, in order of what would hurt most if it broke:

  1. The file goes out through the conversation's own channel and chat, with the typed words as its caption, and is
     recorded as the owner's message the chat can show (served back by /conversations/<id>/media).
  2. A failed send records nothing and leaves no file behind; the error reaches the owner.
  3. What a channel cannot carry is refused before any send: a file on an Instagram comment, a document on a
     Facebook comment, a channel without the file capability, an empty or too large file.
  4. Sending takes the chat over from its bot, as typing does.
  5. Every channel that says it sends files has a `send_file`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-inbox-file-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import channels  # noqa: E402
import conversations  # noqa: E402
import routes.conversations as rc  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


PAGE = "1234567890123"
TOKEN = "EAA" + "t" * 60
SENT = []
MODE = {"ok": True}


async def fake_send_file(kenh, tk, chat_id, path, caption="", chat_type="private"):
    SENT.append({"kenh": kenh, "id": tk.get("id"), "token": bool(tk.get("token")), "chat": chat_id,
                 "name": Path(path).name, "exists": Path(path).is_file(), "caption": caption})
    return (True, "") if MODE["ok"] else (False, "Meta refused")


orig_send_file = channels.send_file
channels.send_file = fake_send_file

aid, err = channel_accounts.create_account({"channel": "messenger", "token": f"{PAGE} {TOKEN} {'c' * 32}",
                                            "external_id": PAGE, "label": "Shop", "meta": {"bot_name": "Shop"}})
check("a Messenger account to work with", bool(aid), err)


def chat(ext, text="Cho em xem mẫu"):
    return conversations.ghi_su_kien({"channel": "messenger", "account_id": aid, "account_name": "Shop",
                                      "external_chat_id": ext, "chat_type": "private", "sender_type": "customer",
                                      "sender_id": "777", "sender_name": "Chị Lan", "text": text,
                                      "external_message_id": ext + "-1"})["conversation_id"]


cl = TestClient(main.app)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

# ============================================================
# 1. An image with a caption
# ============================================================
conv = chat("777")
r = cl.post(f"/conversations/{conv}/send-file", data={"text": "Mẫu này chị nhé"},
            files={"file": ("ao thun/../mau 1.png", PNG, "image/png")})
check("the image is sent", r.status_code == 200 and r.json().get("ok"), r.text)
s = SENT[-1] if SENT else {}
check("through the conversation's channel, account and chat, with the caption, from a file that exists",
      s.get("kenh") == "messenger" and s.get("id") == aid and s.get("token") and s.get("chat") == "777"
      and s.get("exists") and s.get("caption") == "Mẫu này chị nhé", s)
check("the file keeps its own name, never a path", s.get("name", "").endswith("_mau 1.png"), s)
msgs = conversations.tin_nhan(conv, limit=10)
mine = [m for m in msgs if m["sender_type"] == "human"]
md = (mine[-1]["metadata"] if mine else {}).get("sent_file") or {}
check("recorded as the owner's image, caption as its text",
      len(mine) == 1 and mine[0]["message_type"] == "image" and mine[0]["text"] == "Mẫu này chị nhé"
      and md.get("name") == "mau 1.png" and md.get("size") == len(PNG), mine)
g = cl.get(f"/conversations/{conv}/media", params={"p": md.get("p", "")})
check("the chat can show it", g.status_code == 200 and g.content == PNG, g.status_code)
g = cl.get(f"/conversations/{chat('888')}/media", params={"p": md.get("p", "")})
check("another conversation cannot read it", g.status_code == 404, g.status_code)

r = cl.post(f"/conversations/{conv}/send-file", files={"file": ("bao-gia.pdf", b"%PDF-1.4 x", "application/pdf")})
mine = [m for m in conversations.tin_nhan(conv, limit=10) if m["sender_type"] == "human"]
check("a document with no caption is a file message named after it",
      r.status_code == 200 and mine[-1]["message_type"] == "file" and mine[-1]["text"] == "[bao-gia.pdf]"
      and SENT[-1]["caption"] == "", (r.text, mine[-1]))

# ============================================================
# 2. A failed send
# ============================================================
MODE["ok"] = False
before = len(conversations.tin_nhan(conv, limit=50))
files_before = set(rc._sent_dir(conv).iterdir())
r = cl.post(f"/conversations/{conv}/send-file", files={"file": ("x.png", PNG, "image/png")})
check("a failed send says why", r.status_code == 400 and "Meta refused" in r.json().get("error", ""), r.text)
check("and records nothing, keeps no file", len(conversations.tin_nhan(conv, limit=50)) == before
      and set(rc._sent_dir(conv).iterdir()) == files_before)
MODE["ok"] = True

# ============================================================
# 3. Refused before any send
# ============================================================
n = len(SENT)
r1 = cl.post(f"/conversations/{chat('igc:c1')}/send-file", files={"file": ("a.png", PNG, "image/png")})
r2 = cl.post(f"/conversations/{chat('cmt:555_1')}/send-file", files={"file": ("a.pdf", b"%PDF", "application/pdf")})
r3 = cl.post(f"/conversations/{conv}/send-file", files={"file": ("a.png", b"", "image/png")})
old_max = rc.MAX_SENT_FILE
rc.MAX_SENT_FILE = 10
r4 = cl.post(f"/conversations/{conv}/send-file", files={"file": ("a.png", PNG, "image/png")})
rc.MAX_SENT_FILE = old_max
check("an Instagram comment, a document on a Facebook comment, an empty file and a too large one are refused",
      [r1.json().get("code"), r2.json().get("code"), r3.json().get("code"), r4.json().get("code")]
      == ["comment_text_only", "comment_text_only", "empty", "too_big"] and len(SENT) == n,
      [r1.text, r2.text, r3.text, r4.text])
r = cl.post(f"/conversations/{chat('cmt:555_2')}/send-file", files={"file": ("a.jpg", PNG, "image/jpeg")})
check("an image on a Facebook comment goes", r.status_code == 200 and SENT[-1]["chat"] == "cmt:555_2", r.text)
r = cl.post("/conversations/999999/send-file", files={"file": ("a.png", PNG, "image/png")})
check("an unknown conversation is 404", r.status_code == 404)

channels.send_file = orig_send_file
ok, why = asyncio.run(channels.send_file("threads", {"id": "x"}, "1", "/tmp/a.png"))
check("a channel without the file capability says so", not ok and "Threads" in why, why)
channels.send_file = fake_send_file

# ============================================================
# 4. Takes the chat over from its bot
# ============================================================
bconv = conversations.ghi_su_kien({"channel": "messenger", "account_id": aid, "bot_id": "b1", "external_chat_id": "999",
                                   "sender_type": "customer", "sender_id": "999", "text": "hi",
                                   "external_message_id": "999-1"})["conversation_id"]
r = cl.post(f"/conversations/{bconv}/send-file", files={"file": ("a.png", PNG, "image/png")})
check("sending takes the chat over", r.json().get("tiep_quan") is True
      and (conversations.chi_tiet(bconv) or {}).get("mode") == "human", r.text)

# ============================================================
# 5. Every channel that sends files can do it from the inbox
# ============================================================
missing = [s.id for s in channels.danh_sach() if s.nl("gui_file") and s.nl("tra_loi_tu_javis")
           and not hasattr(channels.module(s.id), "send_file")]
check("every channel that sends files and answers from the inbox has send_file", not missing, missing)

channels.send_file = orig_send_file
if _fails:
    print(f"\nFAIL - test_inbox_send_file: {len(_fails)} failed")
    sys.exit(1)
print("\nOK - test_inbox_send_file: all pass")
