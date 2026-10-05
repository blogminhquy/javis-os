"""Customer photos go INTO the chat turn and the bot's own model looks at them (0.79.0).

    python tests/run.py bot_anh_vao_chat      (no network: fake streams)

Owner decision (2026-10-05): no second model describes the photo for the bot (0.74.1 used ChatGPT, so without ChatGPT no brain had
eyes, even brains that see images natively). The photo is saved in the bot's brain (swept by media_gc) and sent as image input
with the turn to whatever model runs the bot. Pinned here:
  1. vision_input: load/shrink, the neutral OpenAI shape, conversion to Anthropic / Responses / Claude Code blocks, and stripping
     the gateway's "[... đã tải về: <path>]" line (a bot must never echo a server path to a stranger).
  2. engine: Anthropic and the ChatGPT plan receive their own image format; the schedule gate still reads the text.
  3. main: the bot turn carries the image to providers that can take it, the honest label to those that cannot, retries with
     text only when the model rejects images, and keeps history as plain text (no base64 resent on later turns).
  4. chatbot_runtime: a group photo sent untagged is remembered for the same person's next message that calls the bot.
  5. Telegram: replying to a photo while tagging the bot brings that photo along.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import base64
import io
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-anhchat-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image  # noqa: E402

import vision_input as vi  # noqa: E402
import engine  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them)[:300] + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


BRAIN = Path(tempfile.mkdtemp(prefix="brain-anhchat-"))
(BRAIN / "inbox" / "khach").mkdir(parents=True)
BIG = BRAIN / "inbox" / "khach" / "photo_1.png"
Image.new("RGBA", (3000, 2000), (255, 0, 0, 128)).save(BIG)
SMALL = BRAIN / "inbox" / "khach" / "photo_2.jpg"
Image.new("RGB", (400, 300), (0, 128, 0)).save(SMALL, "JPEG")
OUTSIDE = Path(tempfile.mkdtemp(prefix="outside-")) / "secret.jpg"
Image.new("RGB", (10, 10)).save(OUTSIDE, "JPEG")

# ---- 1. vision_input ---------------------------------------------------------------------------------------------------
mime, b64 = vi.load(BIG)
im = Image.open(io.BytesIO(base64.b64decode(b64)))
check("a big transparent PNG is shrunk to 1568 px and sent as JPEG on white", mime == "image/jpeg" and max(im.size) == vi.MAX_SIDE
      and im.mode == "RGB", (mime, im.size, im.mode))
mime2, b642 = vi.load(SMALL)
check("a small JPEG is sent as is", mime2 == "image/jpeg" and base64.b64decode(b642) == SMALL.read_bytes())
check("a missing or non-image file loads as None", vi.load(BRAIN / "nope.jpg") is None and vi.load(BRAIN) is None)
parts = vi.user_parts("áo này còn size M không?", [SMALL, BIG])
check("user_parts: the text first, then one image_url part per photo",
      parts[0] == {"type": "text", "text": "áo này còn size M không?"} and len(parts) == 3
      and parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"), parts and parts[0])
check("user_parts with nothing loadable returns None (caller keeps plain text)", vi.user_parts("x", [BRAIN / "nope.jpg"]) is None)
ant = vi.to_anthropic(parts)
check("Anthropic: images become base64 image blocks, placed BEFORE the text",
      [b["type"] for b in ant] == ["image", "image", "text"] and ant[0]["source"]["type"] == "base64"
      and ant[0]["source"]["media_type"] == "image/jpeg", [b["type"] for b in ant])
check("Anthropic: a plain string passes through", vi.to_anthropic("chào") == "chào")
resp = vi.to_responses(parts, "user")
check("Responses (ChatGPT plan): input_text + input_image items",
      [x["type"] for x in resp] == ["input_text", "input_image", "input_image"], resp and [x["type"] for x in resp])
msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": parts}]
plain, imgs = vi.split_last_images(msgs)
check("split_last_images: plain text messages + the images on the side",
      plain[1]["content"] == "áo này còn size M không?" and len(imgs) == 2 and imgs[0][0] == "image/jpeg")
check("content_text reads a parts list", vi.content_text(parts) == "áo này còn size M không?")
blocks = vi.anthropic_blocks("prompt", imgs)
check("Claude Code blocks: images first, then the prompt text", [b["type"] for b in blocks] == ["image", "image", "text"])

tg = f"[Người dùng gửi ảnh qua Telegram, gateway đã tải về: {SMALL}]\n@bot áo này còn không"
t, ps = vi.take_image_markers(tg, BRAIN)
check("the Telegram download line is REMOVED and the photo path returned", t == "@bot áo này còn không" and ps == [str(SMALL.resolve())],
      (t, ps))
t, ps = vi.take_image_markers(f"[Người dùng gửi file qua Telegram, gateway đã tải về: {BIG}]", BRAIN)
check("a logo sent as a FILE (png) counts as a photo too", ps == [str(BIG.resolve())] and t == "")
pdf = f"[Người dùng gửi file qua Telegram, gateway đã tải về: {BRAIN / 'bang-gia.pdf'}]"
check("a non-image file line stays in the text untouched", vi.take_image_markers(pdf, BRAIN) == (pdf, []))
t, ps = vi.take_image_markers(f"[Người dùng gửi ảnh qua Telegram, gateway đã tải về: {OUTSIDE}]", BRAIN)
check("a photo OUTSIDE the bot's brain is never taken", ps == [] and str(OUTSIDE) in t)
t, ps = vi.take_image_markers(f"[The user sent a file on Slack, downloaded to: {SMALL}]\nhi", BRAIN)
check("the English gateway line (Slack/WhatsApp) is understood too", ps == [str(SMALL.resolve())] and t == "hi", (t, ps))
t, ps = vi.take_image_markers(f"[Người dùng gửi một ảnh qua Zalo, đã tải về: {SMALL}]", BRAIN)
check("the Zalo Bot line is understood too", ps == [str(SMALL.resolve())])
check("which brains can take images",
      all(vi.supported(p) for p in ("openai", "openrouter", "gemini", "groq", "ollama", "anthropic-api", "openai-oauth",
                                    "anthropic-cli", ""))
      and not vi.supported("antigravity-cli") and not vi.supported("grok-cli"))

# ---- 2. engine ---------------------------------------------------------------------------------------------------------
ins, items = engine._codex_input([{"role": "system", "content": "S"}, {"role": "user", "content": parts}])
check("ChatGPT plan request carries input_image items", ins == "S"
      and [c["type"] for c in items[0]["content"]] == ["input_text", "input_image", "input_image"])
check("schedule gate still reads the text of a turn with a photo",
      engine._schedule_intent_text([{"role": "user", "content": parts}]) == "áo này còn size M không?")
esrc = (SERVER / "engine.py").read_text(encoding="utf-8")
check("both Anthropic paths (plain and tool loop) convert images", esrc.count("vision_input.to_anthropic(m.get(\"content\", \"\"))") == 2)
csrc = (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8")
check("Claude Code engine sends a list prompt as ONE user message of content blocks",
      "isinstance(prompt, list)" in csrc and '"content": blocks' in csrc)

# ---- 3. main: the bot turn ---------------------------------------------------------------------------------------------
import main  # noqa: E402
import chatbot_runtime as cr  # noqa: E402

SENT = []
SCRIPT = {"replies": []}


def fake_api_stream(prov, key, model, messages, reasoning="off"):
    SENT.append({"prov": prov, "messages": messages})
    rep = SCRIPT["replies"].pop(0) if SCRIPT["replies"] else "Dạ còn ạ"

    async def g():
        if rep:
            yield {"type": "text", "content": rep}
        else:
            yield {"type": "error", "content": "400 image input not supported"}
    return g()

main._api_stream = fake_api_stream


async def _noop(_s):
    return None


def turn(prov, images, text="áo này còn size M không?"):
    SENT.clear()
    sess = {}
    out = asyncio.run(main._bot_tra_loi(text, sess=sess, sysprompt="SYS", prov=prov, api_key="k", api_model="m",
                                        reasoning="off", progress=_noop, runtime_trace=None, brain=None, chat_id="c1",
                                        images=images))
    return out, sess


out, sess = turn("openai", [str(SMALL)])
last = SENT[0]["messages"][-1]["content"]
check("OpenAI-family brain: the last user message carries the photo as image_url",
      isinstance(last, list) and last[1]["type"] == "image_url" and out.get("text") == "Dạ còn ạ", last if not isinstance(last, list) else "")
hist = sess["bot"][0]["content"]
check("history keeps PLAIN text with a short note, never base64",
      isinstance(hist, str) and "base64" not in hist and "ảnh" in hist and hist.startswith("áo này"), hist)
turn("grok-cli", [str(SMALL)])
last = SENT[0]["messages"][-1]["content"]
check("a brain with no image channel (Grok Build) gets the honest label, no image", isinstance(last, str)
      and last.startswith(cr._KEM_ANH), last)
SCRIPT["replies"] = ["", "Dạ em chưa xem được ảnh ạ"]
out, _ = turn("groq", [str(SMALL)])
check("a model that rejects images: retried once with text only + the honest label",
      len(SENT) == 2 and isinstance(SENT[1]["messages"][-1]["content"], str)
      and SENT[1]["messages"][-1]["content"].startswith(cr._KEM_ANH) and out.get("text") == "Dạ em chưa xem được ảnh ạ", SENT)
turn("openai", [])
check("a turn without photos is sent exactly as before (plain string)", isinstance(SENT[0]["messages"][-1]["content"], str)
      and SENT[0]["messages"][-1]["content"] == "áo này còn size M không?")
kem = main._claude_kem_anh([{"role": "user", "content": vi.user_parts("hi", [str(SMALL)])}], "PROMPT")
check("Claude Code prompt: blocks with the photo when the turn has one", isinstance(kem, list) and kem[0]["type"] == "image"
      and kem[-1] == {"type": "text", "text": "PROMPT"})
check("Claude Code prompt: plain string when there is no photo", main._claude_kem_anh([{"role": "user", "content": "hi"}], "P") == "P")
sys_txt, prompt = main._claude_sub_tach([{"role": "system", "content": "S"}, {"role": "user", "content": vi.user_parts("hỏi", [str(SMALL)])}])
check("the one-prompt engines read only the text of a turn with a photo", sys_txt == "S" and "hỏi" in prompt and "base64" not in prompt)

# ---- 4. chatbot_runtime: the turn's photos, and the photo sent just before the tag -------------------------------------
cr._deps["brain_root"] = lambda b: str(BRAIN)
CFG = {"id": "bot9", "brain": "B"}
t, ps = asyncio.run(cr.anh_cho_bot(f"[Người dùng gửi ảnh qua Telegram, gateway đã tải về: {SMALL}]", {"chat_type": "private"}, CFG))
check("a photo with no caption: the photo + a neutral text, no server path", ps == [str(SMALL.resolve())] and t == cr.CHI_CO_ANH)
t, ps = asyncio.run(cr.anh_cho_bot("xem giúp em", {"image_path": str(SMALL)}, CFG))
check("image_path (a file a gateway saved) is used", ps == [str(SMALL.resolve())] and t == "xem giúp em")
t, ps = asyncio.run(cr.anh_cho_bot("xem", {"image_path": str(OUTSIDE)}, CFG))
check("image_path outside the bot's brain is ignored", ps == [])

G = {"chat_type": "group", "chat_id": "-100", "user_id": "u1"}
cr.nho_anh_khong_goi("bot9", G, f"[Người dùng gửi ảnh qua Telegram, gateway đã tải về: {SMALL}]", BRAIN)
m = cr.gan_anh_cho("bot9", dict(G, user_id="u2", mentioned=True), "@bot xem ảnh trên")
check("another person's tag does NOT get someone else's photo", "_anh_cho" not in m)
m = cr.gan_anh_cho("bot9", dict(G, mentioned=True), "@bot xem giúp ảnh trên")
t, ps = asyncio.run(cr.anh_cho_bot("@bot xem giúp ảnh trên", m, CFG))
check("the same person tags the bot right after: the bot sees that photo", ps == [str(SMALL.resolve())], (m, ps))
m = cr.gan_anh_cho("bot9", dict(G, mentioned=True), "@bot còn ảnh đó không")
check("the remembered photo is used once", "_anh_cho" not in m)
cr.nho_anh_khong_goi("bot9", G, f"[Người dùng gửi ảnh qua Telegram, gateway đã tải về: {SMALL}]", BRAIN)
k = ("bot9", "-100", "u1")
cr._ANH_CHO[k]["ts"] -= cr.ANH_CHO_GIAY + 1
check("a photo older than the window is not attached", "_anh_cho" not in cr.gan_anh_cho("bot9", dict(G, mentioned=True), "@bot ?"))
cr.nho_anh_khong_goi("bot9", dict(G, co_anh=True, image_url="https://f1.zdn.vn/a.jpg", message_id="z1"), "ảnh nè", BRAIN)
m = cr.gan_anh_cho("bot9", dict(G, mentioned=True), "@bot xem")
check("Zalo: the remembered photo is its link, downloaded only when the bot is called",
      m.get("_anh_cho_url") == "https://f1.zdn.vn/a.jpg" and m.get("_anh_cho_msg") == "z1")
rsrc = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("both the precheck (silent, untagged) and the answer path remember untagged group photos",
      rsrc.count("_nho_neu_khong_goi(bot_id, cfg, meta, text)") == 2)

# ---- 5. Telegram: reply to a photo + tag the bot -----------------------------------------------------------------------
import telegram_bot  # noqa: E402
tb = telegram_bot.TelegramBot.__new__(telegram_bot.TelegramBot)
tb.bot_username, tb.bot_id = "hamyseego_bot", 42
photo = [{"file_id": "s", "file_size": 10}, {"file_id": "big", "file_size": 999}]
grp = {"type": "supergroup", "id": -100}
r = tb._anh_cua_tin_duoc_tra_loi({"chat": grp, "text": "@hamyseego_bot xem giúp ảnh này",
                                  "reply_to_message": {"message_id": 7, "photo": photo}})
check("group: replying to a photo AND tagging the bot brings the photo", r and r["photo"] == photo and r["message_id"] == 7, r)
check("group: replying to a photo WITHOUT calling the bot downloads nothing",
      tb._anh_cua_tin_duoc_tra_loi({"chat": grp, "text": "đẹp quá", "reply_to_message": {"message_id": 7, "photo": photo}}) is None)
r = tb._anh_cua_tin_duoc_tra_loi({"chat": {"type": "private", "id": 5}, "text": "cái này giá bao nhiêu",
                                  "reply_to_message": {"message_id": 8, "document": {"file_id": "d", "mime_type": "image/png"}}})
check("private chat: replying to an image sent as a file brings it", r and r["document"]["file_id"] == "d")
check("replying to a PDF is not treated as a photo",
      tb._anh_cua_tin_duoc_tra_loi({"chat": {"type": "private"}, "text": "x",
                                    "reply_to_message": {"document": {"file_id": "p", "mime_type": "application/pdf"}}}) is None)

for f in (Path(__file__), SERVER / "vision_input.py"):
    check(f"no em dash in {f.name}", chr(0x2014) not in f.read_text(encoding="utf-8"))

print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("All bot_anh_vao_chat tests passed.")
