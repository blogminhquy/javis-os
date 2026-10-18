"""Background jobs send personal-Zalo messages through the server, as the bot (0.215.0).

    python tests/run.py zalo_job_send      (no network, fake Zalo send)

Real case 2026-10-18: a script job sent the weekly check-in through the Zalo CLI in a child process. The message came
back in the live feed as the account's own, with no echo to match it, so the read loop took it for the owner typing by
hand and the bot went quiet in that chat for ten minutes. `POST /zalo/job-send` (zalo_job_send.send) remembers the echo
before sending and logs the message in the Inbox as the bot's.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zjs-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
import zalo_job_send  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


ACCOUNTS = [{"id": "zalo-1", "label": "Toán Thầy Thành", "connector_id": "zalo"}]
SENT = []


async def fake_send(tk, chat_id, text, chat_type="private", mention=None):
    # The echo must already be remembered when the message leaves (the read loop may see it in the next tick).
    SENT.append(("text", tk["id"], chat_id, text, chat_type, bool(zc._DA_GUI.get((tk["id"], chat_id)))))
    return True, ""


async def fake_send_images(tk, chat_id, paths, chat_type="private"):
    SENT.append(("images", tk["id"], chat_id, list(paths), chat_type, bool(zc._DA_GUI_ANH.get((tk["id"], chat_id)))))
    return True, ""


zc._ket_noi = lambda: [dict(a) for a in ACCOUNTS]
zp.gui = fake_send
zp.gui_anh = fake_send_images
zalo_job_send.bot_for_account = lambda cid: {"id": "bot-x", "name": "Trợ lý Zalo MTM"} if cid == "zalo-1" else {}


def run(payload):
    return asyncio.run(zalo_job_send.send(payload))


def main():
    img_dir = tempfile.mkdtemp(prefix="javis-zjs-img-")
    img = os.path.join(img_dir, "lich-hoc.png")
    with open(img, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    text = "Dạ em chào anh/chị ạ, em là trợ lý lớp Toán thầy Thành. Em nhắn hỏi thăm tình hình học của bạn An ạ."
    r = run({"thread": "t1", "text": text, "label": "weekly"})
    check("a private text goes out", r.get("ok") and r["sent"]["text"], r)
    check("CANARY: the echo is remembered BEFORE the send", SENT and SENT[-1][5], SENT)
    check("CANARY: the read loop recognises it as the bot's own (no owner silence)",
          zc._la_tieng_vong("zalo-1", "t1", text))
    check("and only once", not zc._la_tieng_vong("zalo-1", "t1", text))
    conv = conversations.danh_sach(channel="zalo_personal")
    items = conv.get("items") if isinstance(conv, dict) else conv
    hit = [c for c in (items or []) if str(c.get("external_chat_id")) == "t1"]
    check("the Inbox has the chat", len(hit) == 1, items)
    msgs = conversations.tin_nhan(hit[0]["id"]) if hit else []
    check("CANARY: logged as the bot's message, not the owner's",
          msgs and msgs[-1].get("sender_type") == "ai" and msgs[-1].get("text") == text, msgs)
    check("filed under the bot on duty", hit and hit[0].get("bot_id") == "bot-x", hit)

    SENT.clear()
    r = run({"thread": "g1", "chat_type": "group", "images": [img], "text": "Lịch học lớp 12 ạ."})
    check("image plus text to a group", r.get("ok") and r["sent"] == {"images": 1, "text": True}, r)
    check("image first, then text", [s[0] for s in SENT] == ["images", "text"], SENT)
    check("group chat type is passed on", all(s[4] == "group" for s in SENT), SENT)
    check("image echo remembered before sending", SENT and SENT[0][5], SENT)
    check("the read loop recognises the image echo", zc._la_vong_anh("zalo-1", "g1"))

    SENT.clear()
    check("missing thread is refused", not run({"text": "x"}).get("ok"))
    check("nothing to send is refused", not run({"thread": "t2"}).get("ok"))
    check("relative image path is refused", not run({"thread": "t2", "images": ["x.png"]}).get("ok"))
    check("missing image file is refused", not run({"thread": "t2", "images": [img + ".nope"]}).get("ok"))
    check("non-image file is refused", not run({"thread": "t2", "images": [__file__]}).get("ok"))
    check("too many images is refused", not run({"thread": "t2", "images": [img] * 5}).get("ok"))
    check("nothing was sent by refused calls", SENT == [], SENT)

    ACCOUNTS.append({"id": "zalo-2", "label": "Khác", "connector_id": "zalo"})
    r = run({"thread": "t3", "text": "hi"})
    check("CANARY: two accounts and none named -> refuse rather than guess", not r.get("ok") and "zalo-1" in r["error"], r)
    r = run({"thread": "t3", "text": "hi", "account": "zalo-2"})
    check("a named account is used", r.get("ok") and SENT and SENT[-1][1] == "zalo-2", SENT)
    check("unknown account is refused", not run({"thread": "t3", "text": "hi", "account": "zalo-9"}).get("ok"))

    check("loopback hosts accepted", zalo_job_send.is_loopback("127.0.0.1") and zalo_job_send.is_loopback("::1"))
    check("other hosts refused", not zalo_job_send.is_loopback("172.18.0.5") and not zalo_job_send.is_loopback(""))

    if _fails:
        print(f"\n{len(_fails)} FAIL")
        sys.exit(1)
    print("\nALL OK")


if __name__ == "__main__":
    main()
