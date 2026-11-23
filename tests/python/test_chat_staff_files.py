"""The bot reads the files in a Zalo OA / Fanpage chat: what a STAFF member sends from the app, and a customer's document.

    python tests/run.py chat_staff_files      (NO network)

Owner report 18/11/2026: "a staff member sends the customer a photo or a PDF quote in the OA, can the bot read it?" It
could not. The transports dropped every message the OA/Page sent (`oa_send_*`, Messenger `is_echo`), so the inbox never
showed it and the bot did not know it existed; and a bot on the default level has no tool, so even a customer's PDF was
only a server path to it. Now:
  1. the bot's own sends are remembered, so their echo is skipped (`chat_files.is_own_echo`);
  2. a staff member's message reaches `event_fn("staff_sent")` with the files downloaded;
  3. the runtime files it in the inbox as `human`, with what the file says, and the bot's history carries that content;
  4. a customer's document is replaced by its text in the turn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-staff-files-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chat_files  # noqa: E402
import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402
import messenger_bot  # noqa: E402
import zalo_oa_bot as zo  # noqa: E402

fails = []


def check(name, cond, more=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(more) + "]") if more and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


ROOT_DIR = Path(tempfile.mkdtemp(prefix="javis-staff-brain-"))
INBOX = ROOT_DIR / "inbox" / "khach"
INBOX.mkdir(parents=True)


def make_docx(path: Path, text: str) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>" + text +
                   "</w:t></w:r></w:p></w:body></w:document>")
    return path


# ============================================================
# 1. Echo registry
# ============================================================
chat_files.forget_all()
chat_files.remember_sent("zalo_oa", "u1", "Dạ chai 500ml giá 85.000đ ạ.")
check("the bot's text comes back as its own echo", chat_files.is_own_echo("zalo_oa", "u1", "Dạ chai 500ml  giá 85.000đ ạ."))
check("a match is used up: the same words again are a person's", not chat_files.is_own_echo("zalo_oa", "u1", "Dạ chai 500ml giá 85.000đ ạ."))
check("another chat never matches", (chat_files.remember_sent("zalo_oa", "u1", "ok"), not chat_files.is_own_echo("zalo_oa", "u2", "ok"))[1])
chat_files.remember_sent("messenger", "p1", kind="file")
check("a file the bot sent matches a file echo, not an image", not chat_files.is_own_echo("messenger", "p1", kind="image")
      and chat_files.is_own_echo("messenger", "p1", kind="file"))
chat_files.remember_id("zalo_oa", "mid-9")
check("a remembered message id matches", chat_files.is_own_echo("zalo_oa", "zz", message_id="mid-9"))
check("staff words never sent by the bot are not an echo", not chat_files.is_own_echo("zalo_oa", "u1", "Em gửi anh báo giá"))

# ============================================================
# 2. Reading files
# ============================================================
docx = make_docx(INBOX / "bao-gia.docx", "Bao gia: Nuoc mam 500ml 85.000d")
ok, txt = run(chat_files.read_file(docx))
check("a Word file is read", ok and "85.000d" in txt, (ok, txt))
(INBOX / "ghi-chu.txt").write_text("Phi ship 30k", encoding="utf-8")
ok, txt = run(chat_files.read_file(INBOX / "ghi-chu.txt"))
check("a text file is read", ok and "30k" in txt, (ok, txt))
img = INBOX / "anh.jpg"
img.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
ok, txt = run(chat_files.read_file(img))
check("a photo without eyes says so, never guesses", not ok and txt, (ok, txt))
seen = {}


async def eyes(paths, caption, chat_id):
    seen["paths"], seen["chat"] = paths, chat_id
    return "Bảng giá: Nước mắm 500ml 85.000đ", "test/eyes", ""
ok, txt = run(chat_files.read_file(img, eyes, "u1"))
check("a photo is read by the borrowed eyes", ok and "85.000đ" in txt and seen.get("chat") == "u1", (ok, txt))
(INBOX / "x.zip").write_bytes(b"PK")
ok, txt = run(chat_files.read_file(INBOX / "x.zip"))
check("an unknown file type is named, not read", not ok and ".zip" in txt, txt)
big = INBOX / "big.txt"
big.write_text("a" * (chat_files.FILE_TEXT_CHARS + 500), encoding="utf-8")
ok, txt = run(chat_files.read_file(big))
check("a long file is cut", ok and len(txt) < chat_files.FILE_TEXT_CHARS + 100 and "characters cut" in txt, len(txt))

# A customer's document is replaced by what it says; photos and files outside the brain are left alone.
line = f"[Người dùng gửi file qua Zalo OA, đã tải về: {docx}]\nGiá này còn không?"
out = run(chat_files.inline_documents(line, ROOT_DIR))
check("a customer's document becomes its text in the turn", "85.000d" in out and str(docx) not in out
      and "Giá này còn không?" in out, out)
outside = Path(tempfile.mkdtemp()) / "khac.docx"
make_docx(outside, "bi mat")
line2 = f"[Người dùng gửi file qua Zalo OA, đã tải về: {outside}]"
check("a file outside the bot's brain is never read", run(chat_files.inline_documents(line2, ROOT_DIR)) == line2)
line3 = f"[Người dùng gửi ảnh qua Zalo OA, đã tải về: {img}]"
check("photos are left to the vision path", run(chat_files.inline_documents(line3, ROOT_DIR, eyes)) == line3)

# ============================================================
# 3. Zalo OA: oa_send_* -> staff path
# ============================================================
OA, USER = "579745863508352884", "2512523625412515"


def oa_bot():
    events = []

    async def ev_fn(kind, tt):
        events.append((kind, tt))
    b = zo.ZaloOABot('{"oa_id": "%s"}' % OA, "", None, giau_trang_thai=True, account_id="acc-oa",
                     event_fn=ev_fn, download_dir=str(INBOX))

    async def dl(client, url, fallbacks=()):
        return b"%PDF-1.4 fake", "application/pdf"
    b._download = dl
    b._client = object()
    return b, events


chat_files.forget_all()
b, events = oa_bot()
chat_files.remember_sent(zo.CHANNEL, USER, "Dạ em chào chị")
run(b._on_staff({"event_name": "oa_send_text", "oa_id": OA, "sender": {"id": OA}, "recipient": {"id": USER},
                 "message": {"msg_id": "o1", "text": "Dạ em chào chị"}}))
check("Zalo OA: the echo of the bot's own text is dropped", events == [], events)
run(b._on_staff({"event_name": "oa_send_file", "oa_id": OA, "sender": {"id": OA}, "recipient": {"id": USER},
                 "message": {"msg_id": "o2", "attachments": [{"type": "file", "payload": {
                     "url": "https://f.zalo.me/bao-gia.pdf", "name": "bao-gia.pdf"}}]}}))
check("Zalo OA: a staff member's PDF reaches the bot, downloaded into the brain",
      len(events) == 1 and events[0][0] == "staff_sent" and events[0][1]["chat_id"] == USER
      and events[0][1]["files"][0]["name"] == "bao-gia.pdf" and Path(events[0][1]["files"][0]["path"]).is_file()
      and events[0][1]["account_id"] == "acc-oa", events)
run(b._on_staff({"event_name": "oa_send_file", "oa_id": OA, "sender": {"id": OA}, "recipient": {"id": USER},
                 "message": {"msg_id": "o2", "attachments": []}}))
check("Zalo OA: a retried event is not filed twice", len(events) == 1, events)
chat_files.remember_sent(zo.CHANNEL, USER, kind="image")
run(b._on_staff({"event_name": "oa_send_image", "oa_id": OA, "sender": {"id": OA}, "recipient": {"id": USER},
                 "message": {"msg_id": "o3", "text": "chú thích", "attachments": [{"type": "image", "payload": {
                     "url": "https://f.zalo.me/a.jpg"}}]}}))
check("Zalo OA: the echo of the bot's own photo is dropped", len(events) == 1, events)
check("Zalo OA: the OA of an oa_send_* event is its sender", zo._oa_of({"event_name": "oa_send_text", "sender": {"id": OA},
                                                                        "recipient": {"id": USER}}) == OA)

# ============================================================
# 4. Messenger: is_echo -> staff path
# ============================================================
PAGE, PSID = "1234567890123", "24987361234567890"
mev = []


async def mev_fn(kind, tt):
    mev.append((kind, tt))
mb = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": "EAA" + "x" * 60, "app_secret": "a" * 32}, "", None,
                                giau_trang_thai=True, event_fn=mev_fn, download_dir=str(INBOX))


async def mdl(client, url):
    return b"\xff\xd8\xff\xe0jpeg", "image/jpeg"
mb._download = mdl
mb._client = object()
run(mb._on_staff({"sender": {"id": PAGE}, "recipient": {"id": PSID},
                  "message": {"mid": "e1", "is_echo": True, "text": "Dạ", "metadata": messenger_bot.ECHO_TAG}}))
check("Messenger: an echo tagged by the bot is dropped", mev == [], mev)
run(mb._on_staff({"sender": {"id": PAGE}, "recipient": {"id": PSID},
                  "message": {"mid": "e2", "is_echo": True, "attachments": [
                      {"type": "image", "payload": {"url": "https://scontent.xx/bang-gia.jpg?x=1"}}]}}))
check("Messenger: a staff member's photo reaches the bot", len(mev) == 1 and mev[0][1]["chat_id"] == PSID
      and mev[0][1]["files"][0]["kind"] == "image" and mev[0][1]["files"][0]["name"] == "bang-gia.jpg", mev)

# ============================================================
# 5. Runtime: filed as human with what the file says; the history carries it
# ============================================================
BOT = {"id": "bot_s", "name": "Shop bot", "brain": "brain-bot", "channel": "zalo_oa", "accounts": []}
chatbot_runtime.chatbot_store.get_bot = lambda bid: dict(BOT) if bid == "bot_s" else None
chatbot_runtime._deps["describe"] = eyes
pdfless = make_docx(INBOX / "bao-gia-2.docx", "Bao gia thang 11: Nuoc mam 1 lit 150.000d")
conversations.ghi_su_kien({"channel": "zalo_oa", "account_id": "acc-oa", "bot_id": "bot_s", "external_chat_id": USER,
                           "sender_type": "customer", "sender_name": "Lan", "text": "Cho em xin báo giá",
                           "external_message_id": "c1"})
n = run(chatbot_runtime.record_staff_message("bot_s", {
    "chat_id": USER, "account_id": "acc-oa", "message_id": "o9", "text": "Em gửi chị báo giá ạ", "platform": "zalo_oa",
    "files": [{"path": str(pdfless), "kind": "file", "name": "bao-gia-2.docx"}]}))
rows = conversations.tin_gan_day("zalo_oa", "acc-oa", USER, 10)
staff = [r for r in rows if r["sender_type"] == "human"]
check("the staff file is one human row in the inbox", n == 1 and len(staff) == 1, (n, rows))
check("the inbox row shows the file and the staff member's words",
      staff and "đã tải về:" in staff[0]["text"] and "Em gửi chị báo giá ạ" in staff[0]["text"]
      and staff[0]["message_type"] == "file", staff)
again = run(chatbot_runtime.record_staff_message("bot_s", {
    "chat_id": USER, "account_id": "acc-oa", "message_id": "o9", "text": "Em gửi chị báo giá ạ", "platform": "zalo_oa",
    "files": [{"path": str(pdfless), "kind": "file", "name": "bao-gia-2.docx"}]}))
check("the same message id is not filed twice", again == 0, again)
run(chatbot_runtime.record_staff_message("bot_s", {"chat_id": USER, "account_id": "acc-oa", "message_id": "o10",
                                                "platform": "zalo_oa", "files": [{"path": str(img), "kind": "image"}]}))
conversations.ghi_su_kien({"channel": "zalo_oa", "account_id": "acc-oa", "bot_id": "bot_s", "external_chat_id": USER,
                           "sender_type": "customer", "sender_name": "Lan", "text": "Nước mắm 1 lít giá bao nhiêu?",
                           "external_message_id": "c2"})
h = chatbot_runtime.private_history(BOT, {"chat_id": USER, "account_id": "acc-oa", "message_id": "c2"}, 30)
said = "\n".join(x["content"] for x in h if x["role"] == "assistant")
check("the bot's history carries what the staff file says", "150.000d" in said, h)
check("the bot's history carries what the staff photo shows", "85.000đ" in said, h)
check("no server path reaches the bot's history", str(INBOX) not in said, said)

print()
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("OK - test_chat_staff_files: all pass")
