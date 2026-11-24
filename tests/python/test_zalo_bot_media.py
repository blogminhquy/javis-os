"""Photos and voice messages sent to a Zalo Bot: real bytes reach the turn, or the failing step is named.

    python tests/run.py zalo_bot_media      (no network: httpx answers from a MockTransport)

Owner report 2026-11-20 (PR #1642 by Dau Quang Cong): three photos in a row were saved as 0-byte `inbox/zalo/zalo_<id>.jpg`
files and announced to the model as "đã tải về". Zalo's file server answered 202, or 200 with an empty body, while the
photo was not ready yet, and the bare `client.get` wrote whatever came back. Guards:
  0. photos and voice messages stay on the gateway's own client, which honours HTTPS_PROXY (owner, 2026-11-24: a server
     that reaches the internet only through a proxy must not lose photos), never the direct pinned-IP `fetch_file`;
  1. an empty or 202 answer is asked again (plain, then browser headers, short waits), like Zalo OA (#1733);
  2. nothing is written or announced as downloaded unless it is a real image; a real one is named by its first bytes
     and written whole (no `.part` left);
  3. an error page or empty body never reaches speech-to-text, and the note names the failing step;
  4. a failure log carries host, status, content type and bytes, never the signed link;
  5. `fetch_file` (documents, videos, personal Zalo) waits out a 202 too, bounded by Retry-After and its time budget;
  6. `read_reference_image` refuses a 0-byte file; `video_vision.probe` falls back to the stream duration, then the
     packet count, so a clip without a container duration is not reduced to its first frame.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextlib
import io
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-zbm-"))

import conversations  # noqa: E402
import httpx  # noqa: E402
import image_gen  # noqa: E402
import stt  # noqa: E402
import video_vision  # noqa: E402
import vision_input  # noqa: E402
import zalo_attachments  # noqa: E402
import zalo_bot as zb  # noqa: E402
import zalo_oa_bot  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="zalo-bot-media-"))
SECRET = "sig=TOPSECRET123"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
OGG = b"OggS\x00\x02" + b"\x00" * 64
HTML = b"<html><body><h1>403 Forbidden</h1></body></html>"

ROUTES = {}
SEEN = []          # (path, headers) of every request the fake CDN got
SLEPT = []


def handler(request: httpx.Request) -> httpx.Response:
    SEEN.append((request.url.path, dict(request.headers)))
    route = ROUTES[request.url.path]
    if callable(route):
        return route(request)
    if isinstance(route, list):          # a sequence of answers, one per request (202 then 200...)
        route = route.pop(0) if len(route) > 1 else route[0]
    status, headers, body = route
    return httpx.Response(status, headers=headers, content=body)


async def fake_sleep(s):
    SLEPT.append(s)
zb._sleep = fake_sleep


async def direct_is_forbidden(*a, **kw):
    raise AssertionError("photos and voice messages must not use the direct pinned-IP downloader")


def bot(**kw):
    inbox = TMP / ("inbox-" + str(len(list(TMP.iterdir())))) / "zalo"
    return zb.ZaloBot("123:abc", "", None, download_dir=str(inbox), **kw), inbox


def send(ev, field, path, status=200, headers=None, body=b"", link_path="", **bot_kw):
    """Run one message whose `field` links to `path` through the bot, on a gateway client whose transport is the fake
    CDN: (line for the engine, inbox, stderr)."""
    if path not in ROUTES or not isinstance(ROUTES[path], list) and not callable(ROUTES[path]):
        ROUTES[path] = (status, headers if headers is not None else {"content-type": "image/jpeg"}, body)
    b, inbox = bot(**bot_kw)
    msg = {"message_id": "fcb4f49050dd04845dcb", "chat": {"id": "c1"}, "from": {"id": "c1"},
           field: f"https://zalo-cdn.example{link_path or path}?{SECRET}"}
    err = io.StringIO()
    real_fetch, real_pub = zalo_attachments.fetch_file, zalo_attachments.public_target
    zalo_attachments.fetch_file = zalo_attachments.public_target = direct_is_forbidden

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await b._ingest_attachment(client, ev, msg)
    try:
        with contextlib.redirect_stderr(err):
            out = asyncio.run(go())
    finally:
        zalo_attachments.fetch_file, zalo_attachments.public_target = real_fetch, real_pub
    return out, inbox, err.getvalue()


def photo(path, status=200, headers=None, body=b"", link_path=""):
    return send(zb.SK_ANH, "photo_url", path, status, headers, body, link_path)


def files(inbox):
    return sorted(p for p in Path(inbox).glob("*")) if Path(inbox).exists() else []


# ---- 0. The owner's constraint: the gateway's proxy-honouring client, never the direct downloader --------------------
src = (ROOT / "server" / "zalo_bot.py").read_text(encoding="utf-8")
check("zalo_bot never builds a client that ignores HTTPS_PROXY", "trust_env=False" not in src)
fm = src.split("async def fetch_media(", 1)[1].split("\ndef ", 1)[0] + src.split("async def _media_tries(", 1)[1].split(
    "\nasync def ", 1)[0]
check("fetch_media downloads on the client it is given, not through zalo_attachments",
      "client.get(" in fm and "zalo_attachments" not in fm and "fetch_file" not in fm)
SEEN.clear()
out, inbox, err = photo("/via-gateway.jpg", body=JPEG)
check("a photo is fetched by the gateway client (the direct downloader would have raised)",
      [p for p, _h in SEEN] == ["/via-gateway.jpg"] and "đã tải về" in out, (SEEN, out))

# ---- 1. The 2026-11-20 case: 200 with an empty body, every time ------------------------------------------------------
SEEN.clear()
SLEPT.clear()
out, inbox, err = photo("/empty.jpg", body=b"")
check("empty body: nothing is kept in the inbox (no 0-byte .jpg)", files(inbox) == [], files(inbox))
check("empty body: the turn is told the download failed, not 'đã tải về'",
      "đã tải về" not in out and "could NOT download" in out and "not ready" in out, out)
check("empty body: the model is told not to claim it looked", "do not claim to have seen it" in out, out)
check("empty body: asked plainly then with browser headers, after each short wait (like Zalo OA)",
      len(SEEN) == 2 * (1 + len(zb.MEDIA_RETRY_WAITS)) and SLEPT == list(zb.MEDIA_RETRY_WAITS)
      and sum(SLEPT) <= 5, (len(SEEN), SLEPT))
check("...the second try of each pass looks like the Zalo web app",
      SEEN[1][1].get("referer") == zalo_oa_bot.BROWSER_HEADERS["Referer"] and "referer" not in SEEN[0][1], SEEN[:2])
check("the failure log names host, status and bytes", "host=zalo-cdn.example" in err and "status=200" in err
      and "bytes=0" in err, err)
check("the failure log never carries the signed link", SECRET not in err and SECRET not in out, err)
check("the inbox still shows the failed photo as a photo", conversations.loai_tin_tu_chu(out) == "image", out)

# ---- 2. A real photo ------------------------------------------------------------------------------------------------
out, inbox, err = photo("/ok.jpg", body=JPEG)
kept = files(inbox)
check("a JPEG is kept, one file, non-empty", len(kept) == 1 and kept[0].stat().st_size == len(JPEG), kept)
check("...as zalo_<id>.jpg and announced with its path",
      kept and kept[0].name == "zalo_fcb4f49050dd04845dcb.jpg" and f"đã tải về: {kept[0]}" in out, out)
check("...no .part file left behind", not any(p.name.endswith(".part") for p in kept), kept)
check("...nothing logged on success", err == "", err)
check("...and the bot's vision path picks it up", len(vision_input.take_image_markers(out, inbox.parent)[1]) == 1, out)

out, inbox, err = photo("/real-png.jpg", headers={"content-type": "application/octet-stream"}, body=PNG)
kept = files(inbox)
check("a PNG behind a .jpg link and a generic label is kept as .png", len(kept) == 1 and kept[0].suffix == ".png", kept)

ROUTES["/moved.jpg"] = (302, {"location": "/final.png"}, b"")
out, inbox, err = photo("/final.png", headers={"content-type": "image/png"}, body=PNG, link_path="/moved.jpg")
check("a redirect is followed and the image kept", files(inbox) and files(inbox)[0].suffix == ".png", out)

# ---- 3. Not an image, HTTP error, oversize, network error -----------------------------------------------------------
out, inbox, err = photo("/html.jpg", headers={"content-type": "text/html"}, body=HTML)
check("an HTML error page served for a photo is not kept", files(inbox) == [], files(inbox))
check("...and the turn says it is not a readable image", "NOT a readable image" in out and "đã tải về" not in out, out)
check("...logged without the link", "dropped" in err and SECRET not in err, err)

out, inbox, err = photo("/gone.jpg", status=403, body=HTML)
check("HTTP 403: nothing kept, status named", files(inbox) == [] and "HTTP 403" in out, out)
check("HTTP 403: logged with status, without the link", "status=403" in err and SECRET not in err, err)

real_cap = zb.MAX_TAI_MB
zb.MAX_TAI_MB = 1
try:
    out, inbox, err = photo("/big.jpg", body=JPEG + b"\x00" * (1024 * 1024))
finally:
    zb.MAX_TAI_MB = real_cap
check("an oversized photo is refused and not kept", files(inbox) == [] and "lớn hơn 1MB" in out, out)


def refused(request):
    raise httpx.ConnectError(f"connection refused for {request.url}")


ROUTES["/down.jpg"] = refused
out, inbox, err = photo("/down.jpg")
check("a network error is named by its kind, never with the link httpx quotes",
      "network error (ConnectError)" in out and SECRET not in out and SECRET not in err and files(inbox) == [], out)

# ---- 3a. The real cause (owner live test 2026-11-20): photo-stal-*.zdn.vn answers 202 + empty body at first --------
ACCEPTED = (202, {"content-length": "0"}, b"")
SLEPT.clear()
ROUTES["/late.jpg"] = [ACCEPTED, ACCEPTED, (200, {"content-type": "image/jpeg"}, JPEG)]
out, inbox, err = photo("/late.jpg")
kept = files(inbox)
check("202, 202, then 200: the photo is fetched and kept non-empty as .jpg",
      len(kept) == 1 and kept[0].stat().st_size == len(JPEG) and kept[0].suffix == ".jpg" and "đã tải về" in out, (kept, out))
check("...after one short wait", SLEPT == [zb.MEDIA_RETRY_WAITS[0]], SLEPT)
ROUTES["/accepted-body.jpg"] = [(202, {"content-type": "application/json"}, b'{"status":"processing"}'),
                                (200, {"content-type": "image/jpeg"}, JPEG)]
out, inbox, err = photo("/accepted-body.jpg")
check("a 202 is never the file, even with a body", len(files(inbox)) == 1 and files(inbox)[0].stat().st_size == len(JPEG), out)
ROUTES["/never.jpg"] = [ACCEPTED]
out, inbox, err = photo("/never.jpg")
check("202 that never ends: nothing kept, the turn says the file was not ready",
      files(inbox) == [] and "HTTP 202" in out and "not ready" in out and "đã tải về" not in out, out)
check("...logged as status=202 bytes=0, without the link", "status=202" in err and "bytes=0" in err and SECRET not in err, err)

real_budget = zb.MEDIA_BUDGET_SECONDS
zb.MEDIA_BUDGET_SECONDS = 0.2


async def hang(request):
    await asyncio.sleep(2)
    return httpx.Response(200, content=JPEG)


ROUTES["/hang.jpg"] = hang
try:
    out, inbox, err = photo("/hang.jpg")
finally:
    zb.MEDIA_BUDGET_SECONDS = real_budget
check("the whole download, retries included, stays inside its time budget",
      "no file within 0.2 seconds" in out and files(inbox) == [], out)

# ---- 3b. Voice messages: error bodies never reach speech-to-text ----------------------------------------------------
HEARD = []


async def stt_ok(data, name):
    HEARD.append(data)
    return {"ok": True, "text": "doanh thu hôm nay"}


out, inbox, err = send(zb.SK_VOICE, "voice_url", "/expired.aac", headers={"content-type": "text/plain"},
                       body=b"Expired", stt_fn=stt_ok)
check("a text/plain error body for a voice message never reaches speech-to-text",
      HEARD == [] and "error page instead of the recording" in out and stt.MARK_THOAI not in out, out)
check("...logged with its type, without the link", "type=text/plain" in err and SECRET not in err, err)
check("...and the inbox still shows it as a voice message", conversations.loai_tin_tu_chu(out) == "audio", out)

out, inbox, err = send(zb.SK_VOICE, "voice_url", "/json.aac", headers={"content-type": "application/octet-stream"},
                       body=b'  {"error": -201, "message": "expired"}', stt_fn=stt_ok)
check("a JSON error behind a binary label is refused too", HEARD == [] and "error page" in out, out)

SLEPT.clear()
ROUTES["/late.ogg"] = [ACCEPTED, (200, {"content-type": "audio/ogg"}, OGG)]
out, inbox, err = send(zb.SK_VOICE, "voice_url", "/late.ogg", stt_fn=stt_ok)
check("a voice message that is ready on the second try is heard", HEARD == [OGG] and out.startswith(stt.MARK_THOAI)
      and "doanh thu hôm nay" in out, (HEARD, out))
check("...and no recording file is left in the inbox", files(inbox) == [], files(inbox))

HEARD.clear()
out, inbox, err = send(zb.SK_VOICE, "voice_url", "/empty.ogg", headers={"content-type": "audio/ogg"}, body=b"",
                       stt_fn=stt_ok)
check("an empty voice body names the download step, not the listening step",
      HEARD == [] and "could NOT download the recording" in out and "nghe hỏng" not in out, out)

# ---- 4. fetch_file (documents, videos, personal Zalo) waits out a 202 too -------------------------------------------
_RealClient = httpx.AsyncClient


def _mock_client(*a, **kw):
    kw.pop("limits", None)
    return _RealClient(*a, transport=httpx.MockTransport(handler), **kw)


async def _public(url):
    from urllib.parse import urlparse
    return urlparse(url).hostname, "93.184.216.34"


real_backoff = zalo_attachments.ACCEPTED_BACKOFF
zalo_attachments.ACCEPTED_BACKOFF = (0.01, 0.01, 0.01, 0.01)
httpx.AsyncClient, real_pub = _mock_client, zalo_attachments.public_target
zalo_attachments.public_target = _public
try:
    ROUTES["/quote.txt"] = [ACCEPTED, ACCEPTED, (200, {"content-type": "text/plain"}, b"gia 45000")]
    b, inbox = bot()
    doc = asyncio.run(b._ingest_attachment(None, zb.SK_UNSUPPORTED, {
        "message_id": "d1", "chat": {"id": "c1"}, "file_url": f"https://zalo-cdn.example/quote.txt?{SECRET}",
        "file_name": "quote.txt"}))
    ROUTES["/never.pdf"] = [ACCEPTED]
    saved, why = asyncio.run(zalo_attachments.fetch_file({"url": f"https://zalo-cdn.example/never.pdf?{SECRET}",
                                                          "name": "never.pdf"}, TMP / "never"))
    ROUTES["/late.mp4"] = [(202, {"retry-after": "0"}, b""), (200, {"content-type": "video/mp4"}, b"\x00\x00\x00\x18ftypmp42")]
    clip, clip_why = asyncio.run(zalo_attachments.fetch_file({"url": "https://zalo-cdn.example/late.mp4", "name": "c.mp4"},
                                                             TMP / "clip"))
finally:
    httpx.AsyncClient, zalo_attachments.public_target = _RealClient, real_pub
    zalo_attachments.ACCEPTED_BACKOFF = real_backoff
check("a document answered 202, 202, then 200 is read", '"gia 45000"' in doc, doc)
check("a file that stays 202 is refused as not ready, no file left",
      saved is None and "HTTP 202" in why and "not ready" in why and not any((TMP / "never").glob("*")), why)
check("...and the reason never quotes the link", SECRET not in why, why)
check("a video after a 202 is saved whole", clip is not None and clip.stat().st_size > 0 and clip_why == "", clip_why)
check("Retry-After: numeric is honoured and clamped to [0.5, 5]", zalo_attachments.retry_after("2", 0.8) == 2.0
      and zalo_attachments.retry_after("0", 0.8) == 0.5 and zalo_attachments.retry_after("120", 0.8) == 5.0)
check("Retry-After: missing or a date falls back to the backoff step", zalo_attachments.retry_after(None, 0.8) == 0.8
      and zalo_attachments.retry_after("Wed, 21 Oct 2015 07:28:00 GMT", 1.5) == 1.5)
check("the whole 202 backoff stays inside the download time budget, even at the longest Retry-After",
      sum(real_backoff) < zalo_attachments.TIMEOUT / 2 and len(real_backoff) * 5.0 < zalo_attachments.TIMEOUT / 2)

# ---- 5. Downstream guards -------------------------------------------------------------------------------------------
vault = TMP / "vault"
(vault / "inbox" / "zalo").mkdir(parents=True)
(vault / "inbox" / "zalo" / "empty.jpg").write_bytes(b"")
r = image_gen.read_reference_image("inbox/zalo/empty.jpg", str(vault))
check("read_reference_image refuses a 0-byte image (no empty data URL)",
      r.get("ok") is False and ("0 byte" in r.get("error", "") or "0 bytes" in r.get("error", "")), r)
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

PROBES = []


async def fake_run_counted(*args, timeout=0):
    PROBES.append(args)
    if "-count_packets" in args:
        return 0, b'{"streams": [{"nb_read_packets": "125", "avg_frame_rate": "25/1", "r_frame_rate": "25/1"}]}', ""
    return 0, b'{"format": {}, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}', ""

video_vision._run = fake_run_counted
try:
    info = asyncio.run(video_vision.probe(Path("x.webm")))
finally:
    video_vision._run = real_run
check("probe: neither container nor stream duration -> packets / frame rate", info["duration"] == 5.0, info)
check("...the packet count runs only as that last resort", len(PROBES) == 2 and "-count_packets" in PROBES[1], PROBES)


async def fake_run_container(*args, timeout=0):
    PROBES.append(args)
    return 0, b'{"format": {"duration": "7.5"}, "streams": [{"codec_type": "video", "duration": "N/A"}]}', ""

PROBES.clear()
video_vision._run = fake_run_container
try:
    info = asyncio.run(video_vision.probe(Path("x.mp4")))
finally:
    video_vision._run = real_run
check("probe: a container duration still wins, with one ffprobe call", info["duration"] == 7.5 and len(PROBES) == 1, info)
check("a broken frame rate gives 0, never a crash", video_vision._rate("0/0") == 0.0 and video_vision._rate("x") == 0.0
      and video_vision._rate("30000/1001") > 29.9)

if fails:
    print(f"FAIL - test_zalo_bot_media: {len(fails)} failed")
    raise SystemExit(1)
print("ok - test_zalo_bot_media")
