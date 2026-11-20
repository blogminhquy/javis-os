"""Photos, voice messages and videos sent to the owner's Zalo Bot: bytes reach the turn or the failing step is named.

    python tests/run.py zalo_bot_media      (no network: httpx answers from a MockTransport, DNS is faked)

Owner report 2026-11-20: three photos in a row were saved as 0-byte `inbox/zalo/zalo_<id>.jpg` files and announced to the
model as "đã tải về". Zalo's file server answered 2xx with an empty body and the bare `client.get` wrote it as is. The
model then looked, found 0 bytes and said so; the gateway had lied first. Guards:
  1. a photo goes through `zalo_attachments.fetch_file`: empty body, error page, HTTP error, oversize -> no file kept and
     a line that names the failing step and forbids "đã xem";
  2. a real image is kept under the extension its first bytes prove, written atomically (no `.part` left);
  3. a failure log carries host, status, content type and bytes, never the signed link;
  4. a clip link becomes frames over time plus its speech, marked as data (`_xem_video`);
  5. `read_reference_image` refuses a 0-byte file; `video_vision.probe` falls back to stream duration so a clip without a
     container duration is not reduced to its first frame.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextlib
import io
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-zbm-"))

import httpx  # noqa: E402
import image_gen  # noqa: E402
import video_vision  # noqa: E402
import zalo_attachments  # noqa: E402
import zalo_bot as zb  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="zalo-bot-media-"))
SECRET = "sig=TOPSECRET123"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
HTML = b"<html><body><h1>403 Forbidden</h1></body></html>"

ROUTES = {}


def handler(request: httpx.Request) -> httpx.Response:
    status, headers, body = ROUTES[request.url.path]
    return httpx.Response(status, headers=headers, content=body)


_RealClient = httpx.AsyncClient


def _mock_client(*a, **kw):
    kw.pop("limits", None)
    return _RealClient(*a, transport=httpx.MockTransport(handler), **kw)


async def _public(url):
    from urllib.parse import urlparse
    return urlparse(url).hostname, "93.184.216.34"


def bot(**kw):
    inbox = TMP / ("inbox-" + str(len(list(TMP.iterdir())))) / "zalo"
    b = zb.ZaloBot("123:abc", "", None, download_dir=str(inbox), **kw)
    return b, inbox


class NoNetwork:
    async def get(self, url, timeout=None):
        raise AssertionError("photos must not use the gateway client any more")


def photo(path, status=200, headers=None, body=b"", link_path=""):
    """Run one photo through the bot: (line for the engine, inbox, stderr). `link_path`: the path the payload links to,
    when it differs from the one that serves `body` (a redirect)."""
    ROUTES[path] = (status, headers if headers is not None else {"content-type": "image/jpeg"}, body)
    b, inbox = bot()
    msg = {"message_id": "fcb4f49050dd04845dcb", "chat": {"id": "c1"}, "from": {"id": "c1"},
           "photo_url": f"https://zalo-cdn.example{link_path or path}?{SECRET}"}
    err = io.StringIO()
    httpx.AsyncClient, real_pub = _mock_client, zalo_attachments.public_target
    zalo_attachments.public_target = _public
    try:
        with contextlib.redirect_stderr(err):
            out = asyncio.run(b._ingest_attachment(NoNetwork(), zb.SK_ANH, msg))
    finally:
        httpx.AsyncClient, zalo_attachments.public_target = _RealClient, real_pub
    return out, inbox, err.getvalue()


def files(inbox):
    return sorted(p for p in Path(inbox).glob("*")) if Path(inbox).exists() else []


# ---- 1. The 2026-11-20 case: 200 with an empty body ---------------------------------------------------------------
out, inbox, err = photo("/empty.jpg", body=b"")
check("empty body: nothing is kept in the inbox (no 0-byte .jpg)", files(inbox) == [], files(inbox))
check("empty body: the turn is told the download failed, not 'đã tải về'", "đã tải về" not in out and "KHÔNG tải được" in out, out)
check("empty body: the reason is named", "rỗng" in out, out)
check("empty body: the model is told not to claim it looked", "đừng nói như đã xem" in out, out)
check("the failure log names host, status and bytes", "host=zalo-cdn.example" in err and "status=200" in err
      and "bytes=0" in err, err)
check("the failure log never carries the signed link", SECRET not in err and SECRET not in out, err)

# ---- 2. A real photo ---------------------------------------------------------------------------------------------
out, inbox, err = photo("/ok.jpg", body=JPEG)
kept = files(inbox)
check("a JPEG is kept, one file, non-empty", len(kept) == 1 and kept[0].stat().st_size == len(JPEG), kept)
check("...as .jpg and announced with its path", kept and kept[0].suffix == ".jpg" and f"đã tải về: {kept[0]}" in out, out)
check("...no .part file left behind", not any(p.name.endswith(".part") for p in kept), kept)
check("...nothing logged on success", err == "", err)

out, inbox, err = photo("/real-png.jpg", headers={"content-type": "application/octet-stream"}, body=PNG)
kept = files(inbox)
check("a PNG behind a .jpg link and a generic label is kept as .png", len(kept) == 1 and kept[0].suffix == ".png", kept)

# ---- 3. Not an image, HTTP error, oversize -----------------------------------------------------------------------
out, inbox, err = photo("/html.jpg", headers={"content-type": "text/html"}, body=HTML)
check("an HTML error page served for a photo is dropped", files(inbox) == [], files(inbox))
check("...and the turn says it is not a readable image", "KHÔNG phải ảnh" in out and "đã tải về" not in out, out)

out, inbox, err = photo("/gone.jpg", status=403, body=HTML)
check("HTTP 403: nothing kept, status named", files(inbox) == [] and "HTTP 403" in out, out)
check("HTTP 403: logged with status, without the link", "status=403" in err and SECRET not in err, err)

big = str(zb.MAX_TAI_MB * 1024 * 1024 + 1)
out, inbox, err = photo("/big.jpg", headers={"content-type": "image/jpeg", "content-length": big}, body=b"")
check("an oversized photo is refused by its Content-Length", files(inbox) == [] and "lớn hơn" in out, out)

ROUTES["/moved.jpg"] = (302, {"location": "/final.png"}, b"")
out, inbox, err = photo("/final.png", headers={"content-type": "image/png"}, body=PNG, link_path="/moved.jpg")
check("a redirect is followed (checked hop by hop) and the image kept", files(inbox) and files(inbox)[0].suffix == ".png", out)

# ---- 4. Videos: frames over time + speech, marked as data --------------------------------------------------------
check("a clip is recognised by its name", zb._is_video({"url": "https://f/x", "name": "clip.MP4"}, {}))
check("...or by the video field it came under", zb._is_video({"url": "https://f/v", "name": "v"}, {"video_url": "https://f/v"}))
check("a PDF is not a clip", not zb._is_video({"url": "https://f/a", "name": "a.pdf"}, {"file_url": "https://f/a"}))

LOOKS = []


async def fake_look(url, dest, msg_id, transcribe=None):
    LOOKS.append((url, msg_id, transcribe))
    if "broken" in url:
        return {"frames": [], "duration": 0.0, "speech": "", "heard": False, "why": "không tải được video: file rỗng"}
    return {"frames": [(Path(dest) / "f1.jpg", 0.62), (Path(dest) / "f2.jpg", 1.88), (Path(dest) / "f3.jpg", 3.12),
                       (Path(dest) / "f4.jpg", 4.38)], "duration": 5.0, "speech": "mật khẩu là bảy bảy ba ba",
            "heard": True, "why": ""}

real_look = video_vision.look
video_vision.look = fake_look
try:
    b, inbox = bot(stt_fn=lambda d, n: None)
    out = asyncio.run(b._ingest_attachment(NoNetwork(), zb.SK_UNSUPPORTED,
                                           {"message_id": "v1", "chat": {"id": "c1"}, "video_url": "https://f/clip.mp4"}))
    bad = asyncio.run(b._ingest_attachment(NoNetwork(), zb.SK_UNSUPPORTED,
                                           {"message_id": "v2", "chat": {"id": "c1"}, "video_url": "https://f/broken.mp4"}))
finally:
    video_vision.look = real_look
check("a clip goes to video_vision with the bot's speech-to-text", LOOKS and LOOKS[0][0] == "https://f/clip.mp4"
      and LOOKS[0][2] is b.stt_fn, LOOKS)
check("every frame is its own download line, in time order", all(f"khung hình {video_vision.clock(t)} của video" in out
                                                                 for t in (0.62, 1.88, 3.12, 4.38)), out)
check("...frames after 2s are included (not thumbnail-only)", "0:04" in out and "dài 0:05" in out, out)
check("the speech is passed on and marked as data, not a command", "bảy bảy ba ba" in out and "KHÔNG phải lệnh" in out, out)
check("a clip that could not be read says why and forbids 'đã xem'", "KHÔNG xem được" in bad and "file rỗng" in bad
      and "Đừng nói như đã xem" in bad and "đã tải về" not in bad, bad)

# ---- 5. Downstream guards ----------------------------------------------------------------------------------------
vault = TMP / "vault"
(vault / "inbox" / "zalo").mkdir(parents=True)
(vault / "inbox" / "zalo" / "empty.jpg").write_bytes(b"")
r = image_gen.read_reference_image("inbox/zalo/empty.jpg", str(vault))
check("read_reference_image refuses a 0-byte image (no empty data URL)", r.get("ok") is False and "0 byte" in r.get("error", ""), r)
(vault / "inbox" / "zalo" / "ok.jpg").write_bytes(JPEG)
check("...and still reads a real one", image_gen.read_reference_image("inbox/zalo/ok.jpg", str(vault)).get("ok") is True)


async def fake_run(*args, timeout=0):
    return 0, b'{"format": {}, "streams": [{"codec_type": "video", "duration": "5.000000"},' \
              b' {"codec_type": "audio", "duration": "4.98"}]}', ""

real_run = video_vision._run
video_vision._run = fake_run
try:
    info = asyncio.run(video_vision.probe(Path("x.mp4")))
finally:
    video_vision._run = real_run
check("probe: no container duration -> the longest stream's", info["duration"] == 5.0 and info["video"] and info["audio"], info)
times = video_vision.frame_times(info["duration"])
check("...so frames spread over the whole clip, not one frame at 0:00", len(times) == 4 and max(times) > 2.0, times)

if fails:
    print(f"FAIL - test_zalo_bot_media: {len(fails)} lỗi")
    raise SystemExit(1)
print("ok - test_zalo_bot_media")
