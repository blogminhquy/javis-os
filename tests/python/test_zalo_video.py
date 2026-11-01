"""Personal Zalo: a video a customer sends reaches the bot as frames (plus its speech), never silently dropped.

    python tests/run.py zalo_video      (no network: the download is replaced by a local clip made with ffmpeg)

Field report 2026-11-01 (a phone-repair shop): a customer sent a video of the faulty machine and the bot answered
"em chưa xem được video" twice, so the customer had to call. The video message was dropped when the turn was merged
(`gop_tin` skipped every type but text, photo and file) and no brain takes a video as input anyway.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zvid-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import conversations  # noqa: E402,F401
import chatbot_runtime as cr  # noqa: E402
import video_vision as vv  # noqa: E402
import zalo_attachments  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


URL = "https://video-stal-6.dlmd.me/no/2c9e5b735641831fda50/2aOboR9Xeb9PE31B4QUW0oFTIZOZMexfPdDQaG2a"

# ============================================================
# 1. The feed message -> inbox event keeps the clip's link
# ============================================================
CONN = {"id": "zalo-1", "label": "Trinh Trần GSM", "connector_id": "zalo"}
raw = {"id": "m1", "threadId": "t1", "threadType": "dm", "senderId": "t1", "senderName": "Hoàng Lâm Vũ",
       "text": URL, "timestamp": int(time.time() * 1000), "type": "chat.video.msg",
       "attachment": {"type": "chat.video.msg", "url": URL, "description": ""}}
e = zc.chuan_hoa_tin(CONN, raw, {"t1": {"name": "Hoàng Lâm Vũ", "type": "dm"}})
check("a javis-zalo video message is a 'video' event", e and e["message_type"] == "video", e)
check("CANARY: its link is kept in metadata.video_url", e and e["metadata"].get("video_url") == URL, e)


# ============================================================
# 2. Merged private turns carry the video
# ============================================================
def ev(kind, text="", url="", i=[0]):
    i[0] += 1
    md = {"video_url": url} if url else {}
    return {"chat_type": "private", "message_type": kind, "text": text or url, "external_chat_id": "t1",
            "sender_id": "t1", "sender_name": "Hoàng Lâm Vũ", "created_at": time.time(), "metadata": md,
            "external_message_id": f"v{i[0]}", "sender_type": "customer", "account_id": "zalo-1"}


g = zc.gop_tin([ev("video", url=URL), ev("text", "Em lắp nó vào r"), ev("text", "Nma nó vẫn thế này")])
check("CANARY: video + texts -> a text turn that still carries the video",
      g["message_type"] == "text" and g["metadata"].get("video_url") == URL, g)
check("the video's link is not read as the customer's words", URL not in g["text"] and "Em lắp nó vào r" in g["text"], g)
check("the video's message id rides along", g["metadata"].get("video_msg") == "v1", g)
g = zc.gop_tin([ev("video", url=URL)])
check("a video alone -> a 'video' turn", g["message_type"] == "video" and g["metadata"].get("video_url") == URL, g)

# ============================================================
# 3. video_vision on a real clip (ffmpeg makes it; the download is local)
# ============================================================
tmp = Path(tempfile.mkdtemp(prefix="javis-zvid-clip-"))
clip = tmp / "clip.mp4"
HAS_FFMPEG = vv.available()
if HAS_FFMPEG:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)], check=True)
FETCHES = []


async def fake_fetch(info, inbox, max_bytes=0):
    FETCHES.append((info.get("url"), max_bytes))
    if info.get("url") != URL:
        return None, "máy chủ file trả HTTP 404 (link có thể đã hết hạn)"
    Path(inbox).mkdir(parents=True, exist_ok=True)
    dest = Path(inbox) / ("zalo_x_" + info["name"])
    shutil.copy(clip, dest)
    return dest, ""


HEARD = []


async def fake_stt(data, name):
    HEARD.append((len(data), name))
    return {"ok": True, "text": "nó cứ kêu tạch tạch rồi tắt"}


zalo_attachments.fetch_file = fake_fetch
brain = tmp / "brain"
brain.mkdir()
cr._deps["brain_root"] = lambda b: str(brain)
cr._deps["transcribe"] = fake_stt
CFG = {"id": "bot-x", "brain": "b"}

if HAS_FFMPEG:
    res = asyncio.run(vv.look(URL, brain / "attachments" / "zalo" / "t1", "v1", fake_stt))
    check("CANARY: 4 frames are cut from the clip", len(res["frames"]) == vv.FRAMES and not res["why"], res)
    check("frames are real jpg files in the brain", all(Path(p).exists() and Path(p).read_bytes()[:3] == b"\xff\xd8\xff"
                                                       for p, _t in res["frames"]), res)
    check("frames are spread over the clip, in order", [t for _p, t in res["frames"]] == sorted(t for _p, t in res["frames"])
          and res["frames"][-1][1] > 3, res["frames"])
    check("the clip itself is deleted after cutting", not list((brain / "attachments" / "zalo" / "t1").glob("*.mp4")))
    check("the video download uses the larger video cap", FETCHES and FETCHES[0][1] == vv.MAX_VIDEO_BYTES, FETCHES)
    check("the sound went to speech-to-text", HEARD and HEARD[0][0] > 0, HEARD)
    n = vv.note(res)
    check("the note says these are frames, with the length and the speech",
          "khung hình" in n and "0:06" in n and "tạch tạch" in n and "không xem được video trực tiếp" in n, n)
    asyncio.run(vv.look(URL, brain / "attachments" / "zalo" / "t1", "v1", fake_stt))
    check("the same link again is served from the cache (no second download)", len(FETCHES) == 1, FETCHES)

    # The bot's turn: frames become the turn's images, the note goes in front of the customer's words.
    text, paths = asyncio.run(cr.anh_cho_bot("Nma nó vẫn thế này", {"chat_id": "t1", "video_url": URL,
                                                                     "message_id": "v1"}, CFG))
    check("CANARY: anh_cho_bot hands the frames to the bot", len(paths) == vv.FRAMES and all(Path(p).exists() for p in paths),
          paths)
    check("and the customer's words follow the note", text.startswith("(khách gửi kèm một video") and
          text.endswith("Nma nó vẫn thế này"), text)
    text, paths = asyncio.run(cr.anh_cho_bot("Anh xem hỗ trợ em với ạ", {"chat_id": "t1", "video_url": URL,
                                                                         "video_truoc": "12:45"}, CFG))
    check("a follow-up turn says the video was sent earlier", "lúc 12:45" in text and len(paths) == vv.FRAMES, text)
else:
    print("skip ffmpeg part: ffmpeg is not installed here")

bad = "https://video-stal-6.dlmd.me/no/expired"
text, paths = asyncio.run(cr.anh_cho_bot("Xem giúp em", {"chat_id": "t1", "video_url": bad, "message_id": "v9"}, CFG))
check("CANARY: a video that cannot be fetched -> no images and an honest note", not paths and "KHÔNG xem được" in text
      and "Đừng nói như đã xem" in text and text.endswith("Xem giúp em"), text)
check("the reason is kept for the bot log", "video" in str(CFG.get("_anh_loi") or ""), CFG)
check("no ffmpeg -> honest note too", "ffmpeg" in vv.note({"frames": [], "why": "máy chủ Javis chưa cài ffmpeg"}))

# ============================================================
# 4. The live bot answers a private video, and shows it again with the next text
# ============================================================
LUOT = []


async def fake_goi(conn, tool, args):
    return {"success": True} if tool == "zalo_send_message" else {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = fake_goi
zc.start = lambda: True


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em xem rồi ạ.", "files": []}


async def chay():
    tb = zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: {"id": "bot-x", "reply_when": "mention"})
    tb.start()
    await tb.xu_ly(ev("video", url=URL))
    check("CANARY: a private video alone reaches the bot (was dropped before)", len(LUOT) == 1, LUOT)
    t, m = LUOT[0] if LUOT else ("", {})
    check("the turn carries the video link", m.get("video_url") == URL, m)
    check("with a line saying it came without text, not the raw link", "video" in t and URL not in t, t)

    LUOT.clear()
    await tb.xu_ly(ev("text", "Anh xem hỗ trợ em với ạ"))
    t, m = LUOT[0] if LUOT else ("", {})
    check("CANARY: the next text turn still sees that video", m.get("video_url") == URL and m.get("video_truoc"), m)

    LUOT.clear()
    zc._VIDEO_RIENG[("zalo-1", "t1")] = (time.time() - zc.ANH_RIENG_GIAY - 1, URL, "v1")
    await tb.xu_ly(ev("text", "Cảm ơn ạ"))
    check("after ANH_RIENG_GIAY the old video is no longer attached", LUOT and not LUOT[0][1].get("video_url"), LUOT)

    LUOT.clear()
    g_ev = ev("video", url=URL)
    g_ev.update(chat_type="group", external_chat_id="g1", sender_id="u9")
    await tb.xu_ly(g_ev)
    check("a bare video in a group: unchanged, not answered", not LUOT, LUOT)
    tb.stop()


asyncio.run(chay())

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("main.py wires speech-to-text for videos", "transcribe=_stt_nghe," in src)
for f in (Path(__file__), ROOT / "server" / "video_vision.py"):
    check(f"no em dash in {f.name}", chr(0x2014) not in f.read_text(encoding="utf-8"))

shutil.rmtree(tmp, ignore_errors=True)
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
