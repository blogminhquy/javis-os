"""Zalo OA photos the bot could not see (issue #1733, Javis 0.627.0, 22/11/2026).

    python tests/run.py zalo_oa_image_download

A Zalo OA bot answered "I can't see the image" for both photos a customer sent:

  1. `inbox/khach/zalo_oa_1795329121553`, 197 KB, NO extension, a real JPEG (FF D8 FF DB). Zalo's CDN labelled it
     `application/octet-stream` (or `image/jpg`) on an address with no extension, and the extension came only from a
     fixed Content-Type table. `vision_input.is_image_path` goes by the extension, so no brain looked at it.
  2. `zalo_oa_1795329342883.jpg`, 0 bytes: Zalo answered 200 with an empty body because the photo just sent was not
     ready yet. (#1777 already stopped saving empty files; this guards it and the short wait-and-retry added here.)

No network: the CDN is a fake client, and `zalo_oa_bot._sleep` is replaced so the waits are only recorded.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-oa-img-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import vision_input  # noqa: E402
import zalo_oa_bot as zo  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


JPEG = b"\xff\xd8\xff\xdb" + b"\x00\x43" + b"j" * 2048       # what the reported file started with
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 64
GIF = b"GIF89a" + b"g" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"w" * 64
PDF = b"%PDF-1.7\n" + b"d" * 64
USER = "2512523625412515"

slept = []


async def fake_sleep(s):
    slept.append(s)
zo._sleep = fake_sleep


class FakeResp:
    def __init__(self, content, status=200, ctype="application/octet-stream"):
        self.content, self.status_code, self.headers = content, status, {"content-type": ctype}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeCDN:
    """Answers from a script: each call takes the next (content, status, content-type); the last one repeats."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    async def get(self, url, headers=None, **kw):
        self.calls.append((url, bool(headers)))
        content, status, ctype = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return FakeResp(content, status, ctype)


# ============================================================
# 1. The extension comes from the bytes first, then the label, the name, and .jpg for a photo
# ============================================================
check("JPEG bytes labelled octet-stream on an address with no extension are a .jpg",
      zo.file_extension(JPEG, "application/octet-stream", "https://dl.zdn.vn/abc/1795329121553", image=True) == ".jpg")
check("same for a file Zalo did not call an image",
      zo.file_extension(JPEG, "application/octet-stream", "https://dl.zdn.vn/abc/x") == ".jpg")
check("image/jpg (not a real MIME type) is a .jpg", zo.file_extension(b"????", "image/jpg", "") == ".jpg")
check("PNG bytes", zo.file_extension(PNG, "application/octet-stream") == ".png")
check("GIF bytes", zo.file_extension(GIF, "") == ".gif")
check("WebP bytes", zo.file_extension(WEBP, "binary/octet-stream") == ".webp")
check("PDF bytes", zo.file_extension(PDF, "application/octet-stream", "https://dl.zdn.vn/f/x") == ".pdf")
check("the bytes win over a wrong label", zo.file_extension(PNG, "image/jpeg", "a.jpg") == ".png")
check("a file name still names a document", zo.file_extension(b"PK\x03\x04zz", "", "bao-gia.docx") == ".docx")
check("an unknown photo still gets .jpg",
      zo.file_extension(b"????", "application/octet-stream", "https://dl.zdn.vn/abc", image=True) == ".jpg")
check("an unknown non-photo gets no made-up extension",
      zo.file_extension(b"????", "application/octet-stream", "https://dl.zdn.vn/abc") == "")

# ============================================================
# 2. Report case 1: the photo is saved as .jpg and the vision path picks it up
# ============================================================
root = Path(tempfile.mkdtemp(prefix="zo-brain-"))
inbox = root / "inbox" / "khach"
bot = zo.ZaloOABot("", "", None, giau_trang_thai=True, download_dir=str(inbox))
url1 = "https://dl-zpc.zdn.vn/7a1b2c/1795329121553"
slept.clear()
cdn = FakeCDN((JPEG, 200, "application/octet-stream"))
t = run(bot._attachment_text(cdn, {"type": "image", "payload": {"url": url1}}, USER))
saved = sorted(inbox.glob("*"))
check("the octet-stream photo is saved once, with .jpg and its bytes",
      len(saved) == 1 and saved[0].suffix == ".jpg" and saved[0].read_bytes() == JPEG, (saved, t))
_rest, paths = vision_input.take_image_markers(t, root)
check("the bot text marks it as an image the vision path takes", paths == [str(saved[0].resolve())], (t, paths))
check("a photo that came at once costs no wait", slept == [], slept)

slept.clear()
t = run(bot._attachment_text(FakeCDN((b"\xff\xd8\xff\xe0" + b"q" * 32, 200, "image/jpg")),
                             {"type": "image", "payload": {"url": "https://dl-zpc.zdn.vn/7a1b2c/2"}}, USER))
_rest, paths = vision_input.take_image_markers(t, root)
check("image/jpg is saved as .jpg and seen", len(paths) == 1 and paths[0].endswith(".jpg"), (t, paths))

# ============================================================
# 3. Report case 2: an empty answer is waited out briefly and never saved as a file
# ============================================================
for f in inbox.glob("*"):
    f.unlink()
slept.clear()
cdn = FakeCDN((b"", 200, "image/jpeg"), (b"", 200, "image/jpeg"), (JPEG, 200, "image/jpeg"))
t = run(bot._attachment_text(cdn, {"type": "image", "payload": {"url": "https://dl-zpc.zdn.vn/7a1b2c/3"}}, USER))
saved = sorted(inbox.glob("*"))
check("a photo that is empty at first is fetched again after a short wait and saved",
      len(saved) == 1 and saved[0].stat().st_size == len(JPEG) and str(saved[0]) in t, (saved, t, cdn.calls))
check("one wait was enough", slept == [zo.EMPTY_RETRY_WAITS[0]], slept)

for f in inbox.glob("*"):
    f.unlink()
slept.clear()
url2 = "https://dl-zpc.zdn.vn/7a1b2c/1795329342883.jpg"
cdn = FakeCDN((b"", 200, "image/jpeg"))
t = run(bot._attachment_text(cdn, {"type": "image", "payload": {"url": url2, "thumbnail": url2 + "?thumb=1"}}, USER))
check("a photo that stays empty writes no file at all", list(inbox.glob("*")) == [], list(inbox.glob("*")))
check("the bot is told plainly the file was empty and to ask for it again, with Zalo's address",
      url2 in t and ("send it again" in t or "gửi lại" in t) and "downloaded to" not in t and "đã tải về" not in t, t)
check("nothing in that text passes for a downloaded image", vision_input.take_image_markers(t, root)[1] == [], t)
check("each retry waited once, and the waits stay short",
      slept == list(zo.EMPTY_RETRY_WAITS) and sum(slept) <= 5, slept)
check("every pass tried the photo and its thumbnail, plainly and as a browser",
      len(cdn.calls) == 4 * (1 + len(zo.EMPTY_RETRY_WAITS))
      and {u for u, _ in cdn.calls} == {url2, url2 + "?thumb=1"}, cdn.calls)

slept.clear()
t = run(bot._attachment_text(FakeCDN((b"gone", 404, "text/html")),
                             {"type": "image", "payload": {"url": "https://dl-zpc.zdn.vn/7a1b2c/4"}}, USER))
check("a 404 is not waited on and is reported as a failed download",
      slept == [] and "404" in t and list(inbox.glob("*")) == [], (slept, t))

# ============================================================
# 4. Photos staff send from the OA app go through the same naming
# ============================================================
got = []


async def event_fn(kind, data):
    got.append((kind, data))
staff_dir = root / "inbox" / "staff"
staff = zo.ZaloOABot("", "", None, giau_trang_thai=True, download_dir=str(staff_dir), event_fn=event_fn)
staff.oa_id = "579745863508352884"
staff._client = FakeCDN((JPEG, 200, "application/octet-stream"))
run(staff._on_staff({"event_name": "oa_send_image", "recipient": {"id": USER}, "message": {
    "msg_id": "staff-img-1733", "attachments": [{"type": "image", "payload": {"url": "https://dl-zpc.zdn.vn/s/9"}}]}}))
files = (got[0][1].get("files") if got else None) or []
check("a staff photo labelled octet-stream is filed as a .jpg image",
      len(files) == 1 and files[0]["kind"] == "image" and files[0]["path"].endswith(".jpg")
      and Path(files[0]["path"]).read_bytes() == JPEG, got)

try:
    staff._save(USER, b"", "image/jpeg", "a.jpg", "zalo_oa", True)
    raised = False
except zo.EmptyDownload:
    raised = True
check("_save never writes a 0-byte file", raised and not any(p.stat().st_size == 0 for p in staff_dir.glob("*")))

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
