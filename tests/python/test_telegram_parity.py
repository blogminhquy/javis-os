"""Telegram parity audit (2026-11-20): what the Telegram gateway was missing next to Slack, WhatsApp and Messenger.

    python tests/run.py telegram_parity      (no network: Telegram's API is faked)

Guarded, in order of what a customer would notice first:
  1. In a forum group an answer goes back into the TOPIC it was asked in, and quotes the question in a group.
  2. An album (several photos at once) is answered in ONE turn, not one per photo.
  3. Location, venue, contact, sticker and poll reach the bot instead of being dropped.
  4. A 429 waits Telegram's `retry_after` and sends again; long answers split at paragraph breaks.
  5. An .mp4 goes out with sendVideo.
  6. A video saved by the gateway (`video_path`) is only watched when it sits inside the bot's own brain.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tgparity-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import telegram_bot as tb  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


class _Resp:
    def __init__(self, body, code=200):
        self._b, self.status_code, self.content, self.text = body, code, b"x", str(body)

    def json(self):
        return self._b


class FakeClient:
    """Records every Bot API call; answers ok with a message id. `fail_429` makes the first N calls 429."""
    def __init__(self, fail_429=0):
        self.calls = []
        self.fail_429 = fail_429

    async def post(self, url, json=None, data=None, files=None, **_):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json if json is not None else data, files))
        if self.fail_429 > 0:
            self.fail_429 -= 1
            return _Resp({"ok": False, "error_code": 429, "parameters": {"retry_after": 3}}, 429)
        return _Resp({"ok": True, "result": {"message_id": 77}})

    async def get(self, *a, **k):
        return _Resp({"ok": True, "result": {}})


# ============================================================
# 1. Forum topic and quote
# ============================================================
async def _topic_turn(human):
    async def answer(text, meta, progress):
        return {"text": "Dạ có ạ"}

    bot = tb.TelegramBot("tok", "", answer, giau_trang_thai=human)
    c = FakeClient()
    meta = {"chat_id": "-100", "chat_type": "supergroup", "message_id": 501, "thread_id": 42}
    bot._topic["-100"] = 99          # a newer message in ANOTHER topic arrived meanwhile
    await bot._handle_turn(c, "-100", "còn size M không?", meta)
    return c.calls

calls = run(_topic_turn(True))
sends = [c[1] for c in calls if c[0] == "sendMessage"]
acts = [c[1] for c in calls if c[0] == "sendChatAction"]
check("human mode: the answer goes into the topic it was asked in, not the newer one",
      sends and all(s.get("message_thread_id") == 42 for s in sends), sends)
check("human mode: the answer quotes the question in a group",
      sends and sends[0].get("reply_parameters", {}).get("message_id") == 501
      and sends[0]["reply_parameters"].get("allow_sending_without_reply") is True, sends)
check("typing shows in the same topic", acts and acts[0].get("message_thread_id") == 42, acts)

calls = run(_topic_turn(False))
sends = [c[1] for c in calls if c[0] == "sendMessage"]
check("owner mode: status message quotes the question, answer stays in the topic",
      len(sends) == 2 and sends[0].get("reply_parameters", {}).get("message_id") == 501
      and all(s.get("message_thread_id") == 42 for s in sends) and "reply_parameters" not in sends[1], sends)


async def _private_turn():
    async def answer(text, meta, progress):
        return {"text": "ok"}

    bot = tb.TelegramBot("tok", "", answer, giau_trang_thai=True)
    c = FakeClient()
    await bot._handle_turn(c, "55", "hi", {"chat_id": "55", "chat_type": "private", "message_id": 3})
    return [x[1] for x in c.calls if x[0] == "sendMessage"]

sends = run(_private_turn())
check("private chat: no quote, no topic", sends and "reply_parameters" not in sends[0]
      and "message_thread_id" not in sends[0], sends)

bot = tb.TelegramBot("tok", "", None)
m = bot._build_meta({"message_id": 1, "chat": {"id": -100, "type": "supergroup"}, "from": {"id": 5},
                     "message_thread_id": 42, "is_topic_message": True})
check("meta carries the topic of a topic message", m.get("thread_id") == 42, m)
m = bot._build_meta({"message_id": 1, "chat": {"id": -100, "type": "supergroup"}, "from": {"id": 5},
                     "message_thread_id": 9})
check("a reply thread in a plain supergroup is not a topic", m.get("thread_id") is None, m)


# ============================================================
# 2. Albums: one turn
# ============================================================
async def _album():
    bot = tb.TelegramBot("tok", "", None)
    got = []

    async def fake_ingest(client, msg):
        return f"[photo {msg['message_id']} downloaded]" + (("\n" + msg["caption"]) if msg.get("caption") else "")

    async def fake_dispatch(client, chat, text, meta=None):
        got.append((text, meta))

    bot._ingest_attachment = fake_ingest
    bot._dispatch = fake_dispatch
    old = tb.ALBUM_WAIT
    tb.ALBUM_WAIT = 0.05
    try:
        base = {"chat": {"id": 7, "type": "private"}, "from": {"id": 7}, "media_group_id": "g1"}
        bot._album_add(None, "7", dict(base, message_id=1, photo=[{"file_id": "a"}], caption="mẫu này còn không?"))
        bot._album_add(None, "7", dict(base, message_id=2, photo=[{"file_id": "b"}]))
        bot._album_add(None, "7", dict(base, message_id=3, photo=[{"file_id": "c"}]))
        await asyncio.sleep(0.2)
    finally:
        tb.ALBUM_WAIT = old
    return got

got = run(_album())
check("an album of 3 photos is ONE turn", len(got) == 1, got)
t = got[0][0] if got else ""
check("the turn carries every photo and the caption once",
      all(f"photo {i}" in t for i in (1, 2, 3)) and t.count("mẫu này còn không?") == 1, t)
check("meta of the part that carries the caption", got and got[0][1].get("message_id") == 1, got)


# ============================================================
# 3. Messages with no text and no file
# ============================================================
check("location", tb.other_text({"location": {"latitude": 10.7, "longitude": 106.6}}) == "[location: 10.7, 106.6]")
v = tb.other_text({"venue": {"location": {"latitude": 1, "longitude": 2}, "title": "Shop", "address": "1 Lê Lợi"}})
check("venue keeps title and address", "Shop - 1 Lê Lợi" in (v or ""), v)
c = tb.other_text({"contact": {"first_name": "Lan", "phone_number": "+8490111"}})
check("contact keeps name and phone", "Lan" in (c or "") and "+8490111" in c, c)
check("sticker says its emoji", "😂" in (tb.other_text({"sticker": {"emoji": "😂"}}) or ""))
p = tb.other_text({"poll": {"question": "Màu nào?", "options": [{"text": "Đỏ"}, {"text": "Xanh"}]}})
check("poll keeps question and options", "Màu nào?" in (p or "") and "Đỏ; Xanh" in p, p)
check("nothing known: still None", tb.other_text({"dice": {"emoji": "🎲"}}) is None)


async def _ingest_contact():
    bot = tb.TelegramBot("tok", "", None)
    return await bot._ingest_attachment(None, {"message_id": 1, "chat": {"id": 1},
                                               "contact": {"first_name": "Lan", "phone_number": "0901"}})

check("the gateway hands a contact on instead of dropping the turn", "0901" in (run(_ingest_contact()) or ""))


# ============================================================
# 4. 429 and chunking
# ============================================================
async def _retry():
    bot = tb.TelegramBot("tok", "", None)
    c = FakeClient(fail_429=1)
    waited = []
    real = asyncio.sleep

    async def fast(s):
        waited.append(s)
        await real(0)
    tb.asyncio.sleep = fast
    try:
        await bot._send(c, "1", "hello")
    finally:
        tb.asyncio.sleep = real
    return c.calls, waited

calls, waited = run(_retry())
check("429: waits retry_after and the SAME (Markdown) message goes again",
      waited == [3] and len(calls) == 2 and all(x[1].get("parse_mode") == "MarkdownV2" for x in calls), (calls, waited))
parts = tb._chunks(("Đoạn một **đậm**.\n\n" * 400))
check("long answers split under the limit", all(len(x) <= tb.MAX_CHUNK for x in parts) and len(parts) > 1)
check("split at paragraph breaks, never through **bold**", all(x.count("**") % 2 == 0 for x in parts))


# ============================================================
# 5. Video goes as video
# ============================================================
async def _video_send():
    d = Path(tempfile.mkdtemp(prefix="tgv-"))
    f = d / "clip.mp4"
    f.write_bytes(b"\x00" * 100)
    bot = tb.TelegramBot("tok", "1", None)
    c = FakeClient()
    real = tb.httpx.AsyncClient

    class _Ctx:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return c

        async def __aexit__(self, *a):
            return False
    tb.httpx.AsyncClient = _Ctx
    try:
        ok, err = await bot.send_file(str(f), "xem nè")
    finally:
        tb.httpx.AsyncClient = real
    return ok, [x[0] for x in c.calls]

ok, methods = run(_video_send())
check("an .mp4 goes out with sendVideo", ok and methods == ["sendVideo"], (ok, methods))


# ============================================================
# 6. A gateway-saved video is watched only inside the bot's brain
# ============================================================
import chatbot_runtime as cr  # noqa: E402
import video_vision as vv  # noqa: E402

brain = Path(tempfile.mkdtemp(prefix="tg-brain-"))
outside = Path(tempfile.mkdtemp(prefix="tg-out-")) / "x.mp4"
outside.write_bytes(b"0")
frames, note = run(cr.video_cho_bot({"chat_id": "1", "video_path": str(outside)}, brain, {}))
check("a video outside the bot's brain is refused, and the model is told it cannot see it",
      frames == [] and "KHÔNG xem được" in note, note)
res = run(vv.look_file(str(brain / "missing.mp4"), brain, "m1"))
check("look_file on a missing file explains, never raises", res["frames"] == [] and res["why"], res)


print()
if _fails:
    print(f"{len(_fails)} FAIL:")
    for f in _fails:
        print("  - " + f)
    sys.exit(1)
print("OK - test_telegram_parity: all passed")
