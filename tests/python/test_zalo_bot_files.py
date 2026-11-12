"""A file sent to a Zalo Bot is read, or the sender is told it did not arrive (never silence).

    python tests/run.py zalo_bot_files      (no network: the download is faked, the bot is real)

Owner report 2026-11-12: "the Zalo chatbot only receives text, not files". The gateway handled text, photos, stickers and
voice messages; every other event returned None and the message was dropped without a word. Zalo documents no file event:
a PDF, a spreadsheet or a video arrives as `message.unsupported.received`, and what that event carries is not published.
Guards:
  1. a link under any name a file could travel under is found (`find_file`), a bare `url` is not taken for a file;
  2. a file with a link is downloaded into the brain inbox and its text reaches the turn (PDF, Word, Excel, plain text),
     a photo sent as a file goes the photo way, a file without an extension is named from its first bytes;
  3. a message without a link still starts a turn, on a note saying the content never reached the bot;
  4. the owner's bot downloads nothing for a chat that is not allowed yet;
  5. the receive loop runs the turn for an unsupported message, and keeps a file whose caption came as `text`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import io
import tempfile
import zipfile
from pathlib import Path

import conversations
import vision_input
import zalo_attachments
import zalo_bot as zb

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="zalo-bot-files-"))
INBOX = TMP / "inbox" / "zalo"


def bot(**kw):
    return zb.ZaloBot("123:abc", "", kw.pop("answer_fn", None), download_dir=str(INBOX), **kw)


class NoNetwork:
    """The HTTP client of the gateway. A file goes through `zalo_attachments.fetch_file`, never through this client."""

    def __init__(self):
        self.calls = []

    async def get(self, url, timeout=None):
        self.calls.append(url)
        raise AssertionError("the gateway client must not be used for a file")


FETCHED = []


def fake_fetch(content: bytes, fail=""):
    async def fetch(info, inbox, max_bytes=0):
        FETCHED.append(info)
        if fail:
            return None, fail
        inbox = Path(inbox)
        inbox.mkdir(parents=True, exist_ok=True)
        dest = inbox / ("zalo_%02d_" % len(FETCHED) + zalo_attachments.safe_name(info.get("name") or "file"))
        dest.write_bytes(content)
        return dest, ""
    return fetch


REAL_FETCH = zalo_attachments.fetch_file


def ingest(b, ev, msg, content=b"", fail=""):
    zalo_attachments.fetch_file = fake_fetch(content, fail)
    try:
        return asyncio.run(b._ingest_attachment(NoNetwork(), ev, msg))
    finally:
        zalo_attachments.fetch_file = REAL_FETCH


def msg(**kw):
    return {"message_id": "m1", "chat": {"id": "c1", "chat_type": "PRIVATE"},
            "from": {"id": "c1", "display_name": "Ted", "is_bot": False}, **kw}


# ---- 1. find_file: the payload shape is not published, so several are accepted --------------------------------------

check("flat link and name", zb.find_file({"file_url": "https://f.zalo/x?t=1", "file_name": "Bao gia.pdf", "file_size": 2048})
      == {"url": "https://f.zalo/x?t=1", "name": "Bao gia.pdf", "size": 2048})
check("nested object", zb.find_file({"document": {"url": "https://f.zalo/a", "name": "a.docx", "size": "10"}})
      == {"url": "https://f.zalo/a", "name": "a.docx", "size": 10})
check("list of attachments: the first one", zb.find_file({"attachments": [{"href": "https://f.zalo/b.xlsx"}]})["url"]
      == "https://f.zalo/b.xlsx")
check("no name in the payload: the last part of the link", zb.find_file({"video_url": "https://f.zalo/v/clip%201.mp4?x=1"})
      ["name"] == "clip 1.mp4")
check("no name anywhere: 'file'", zb.find_file({"file_url": "https://f.zalo/"})["name"] == "file")
check("no link: empty", zb.find_file(msg()) == {} and zb.find_file(None) == {})
check("a bare `url` is not a file (it may be a shared web link)", zb.find_file({"url": "https://vnexpress.net/"}) == {})
check("a photo field is not a file (photos keep their own path)", zb.find_file({"photo_url": "https://f.zalo/p.jpg"}) == {})


# ---- 2. A file with a link is downloaded and read ---------------------------------------------------------------------

b = bot()
out = ingest(b, zb.SK_UNSUPPORTED, msg(file_url="https://f.zalo/x", file_name="gia.csv", caption="xem giúp bảng giá"),
             "ten,gia\nnuoc mam,45000\n".encode("utf-8"))
check("a text file: its content reaches the turn", "nuoc mam,45000" in out, out)
check("the gateway marker carries the saved path inside the inbox",
      "gateway đã tải về: " + str(INBOX) in out and "gia.csv" in out, out)
check("the caption stays the sender's words, after the file", out.rstrip().endswith("xem giúp bảng giá"), out[-80:])
check("the download gets the link, name and size", FETCHED[-1]["url"] == "https://f.zalo/x" and FETCHED[-1]["name"] == "gia.csv")
check("the inbox shows it as a file", conversations.loai_tin_tu_chu(out) == "file")

out = ingest(bot(), "message.file.received", msg(file={"url": "https://f.zalo/y", "file_name": "ghi chu.txt"}), b"hello")
check("an event name Zalo has not documented yet is read the same way", '"hello"' in out, out)

docx = io.BytesIO()
with zipfile.ZipFile(docx, "w") as z:
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("word/document.xml",
               '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r>'
               "<w:t>Hop dong thue nha</w:t></w:r></w:p></w:body></w:document>")
out = ingest(bot(), zb.SK_UNSUPPORTED, msg(file_url="https://f.zalo/d/8f3a"), docx.getvalue())
check("a Word file without an extension is named from its content and read", "Hop dong thue nha" in out
      and ".docx]" in out.split("\n", 1)[0], out[:300])

out = ingest(bot(), zb.SK_UNSUPPORTED, msg(file_url="https://f.zalo/d/9c1b"), b"\x89PNG\r\n\x1a\n" + b"0" * 32)
text, images = vision_input.take_image_markers(out, TMP)
check("a photo sent as a file goes the photo way (the bot can look at it)",
      len(images) == 1 and images[0].endswith(".png") and "đã tải về" not in text, out)

out = ingest(bot(), zb.SK_UNSUPPORTED, msg(file_url="https://f.zalo/z.pdf"), fail="file lớn hơn 20MB nên không tải")
check("a failed download says why and forbids a guess", "không tải về được" in out and "20MB" in out
      and "không đoán" in out.lower(), out)


# ---- 3. No link in the payload: the turn still runs, on an honest note -------------------------------------------------

b = bot()
n = len(FETCHED)
out = ingest(b, zb.SK_UNSUPPORTED, msg())
check("no link: the sender is told the content did not reach the bot", "KHÔNG chuyển nội dung" in out
      and "không nhận được" in out, out)
check("no link: nothing is downloaded", len(FETCHED) == n)
check("no link: warned on stderr once, not on every message", b._warned_no_file_link is True)
check("the inbox shows that note as a file, not as a photo", conversations.loai_tin_tu_chu(out) == "file",
      conversations.loai_tin_tu_chu(out))
check("an unknown event without a link gets the same note", "KHÔNG chuyển nội dung"
      in ingest(bot(), "message.location.received", msg()))
check("a text event without text is still nothing", ingest(bot(), zb.SK_TEXT, msg()) is None)
check("a sticker keeps its own line", "sticker" in ingest(bot(), zb.SK_STICKER, msg()).lower())


# ---- 4. The owner's bot downloads nothing for a chat that is not allowed yet -----------------------------------------

n = len(FETCHED)
gated = bot(download_ok_fn=lambda chat: chat == "allowed", stt_fn=None)
client = NoNetwork()
zalo_attachments.fetch_file = fake_fetch(b"x")
try:
    outs = [asyncio.run(gated._ingest_attachment(client, ev, msg(file_url="https://f.zalo/x.pdf",
                                                                 photo_url="https://f.zalo/p.jpg",
                                                                 voice_url="https://f.zalo/v.aac")))
            for ev in (zb.SK_UNSUPPORTED, zb.SK_ANH, zb.SK_VOICE)]
finally:
    zalo_attachments.fetch_file = REAL_FETCH
check("a chat not allowed yet: no file, photo or voice message is fetched", len(FETCHED) == n and not client.calls, outs)
check("...and the turn still gets a line, so the precheck can answer with the pairing code",
      all(o and "chưa được cho phép" in o for o in outs), outs)
out = ingest(bot(download_ok_fn=lambda chat: chat == "c1"), zb.SK_UNSUPPORTED,
             msg(file_url="https://f.zalo/x", file_name="a.txt"), b"ok")
check("an allowed chat is downloaded as usual", '"ok"' in out, out)
main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("main.py hands the owner's allow-list to the gateway", "download_ok_fn=_zalo_download_ok" in main_src)


# ---- 5. The receive loop: an unsupported message is answered, a caption in `text` does not hide the file -----------

class LoopBot(zb.ZaloBot):
    """The real loop, fed two rounds of updates, with `_dispatch` recording what would start a turn."""

    def __init__(self, updates):
        super().__init__("123:abc", "", None, download_dir=str(INBOX))
        self.updates = list(updates)
        self.turns = []

    async def _api(self, client, method, **payload):
        if method == "getMe":
            return {"ok": True, "result": {"id": "bot1", "account_name": "bot.x"}}
        if method != "getUpdates" or payload.get("timeout") == 1:
            return {"ok": True, "result": []}
        if not self.updates:
            self._stop = True
            return {"ok": True, "result": []}
        return {"ok": True, "result": self.updates.pop(0)}

    async def _dispatch(self, client, chat, text, meta=None):
        self.turns.append((chat, text))


lb = LoopBot([
    {"event_name": zb.SK_UNSUPPORTED, "message": msg(message_id="u1")},
    {"event_name": "message.file.received",
     "message": msg(message_id="u2", text="báo giá tháng 11", file_url="https://f.zalo/q", file_name="q.txt")},
    {"event_name": zb.SK_UNSUPPORTED, "message": msg(message_id="u3", text="chào shop")},
])
zalo_attachments.fetch_file = fake_fetch(b"gia 45000")
try:
    asyncio.run(lb._loop())
finally:
    zalo_attachments.fetch_file = REAL_FETCH
check("loop: three messages, three turns (the unsupported one is no longer dropped)", len(lb.turns) == 3, lb.turns)
check("loop: the unsupported message starts a turn on the honest note",
      lb.turns and "KHÔNG chuyển nội dung" in lb.turns[0][1], lb.turns[:1])
check("loop: a file whose caption came as `text` is still read, caption kept",
      len(lb.turns) > 1 and "gia 45000" in lb.turns[1][1] and lb.turns[1][1].rstrip().endswith("báo giá tháng 11"),
      lb.turns[1:2])
check("loop: an unsupported message that carries text is a plain text turn",
      len(lb.turns) > 2 and lb.turns[2][1] == "chào shop", lb.turns[2:3])

print()
if fails:
    print(f"{len(fails)} FAILED:", *fails, sep="\n  ")
    raise SystemExit(1)
print("all passed")
