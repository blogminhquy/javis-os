"""Images inserted into a note: they land in images/ and the media sweeper must NOT delete them.

    python tests/run.py note_images      (no network)

The owner asked for images in notes (2026-09-11). The deadly part is not the upload but how LONG
the image LIVES:

`media_gc.media_dirs()` treats `attachments/` and `inbox/` as a CACHE AREA and by default deletes
every file older than 30 days, or when the area grows past 300MB. Its premise is "anything in
there may vanish and the brain stays whole" - a premise that is WRONG for a note's image, because
something points at it. Put note images in attachments/ and a month later the note shows only a
grey "image is gone" box, without a single warning. So note images live in `images/`, out of the
sweeper's reach.

This file locks both: the logical folder `images` exists and works, and the sweeper does not touch
it even when the files are old. It also locks that the images folder stores raster formats only.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-note-images-"))

import media_gc  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS: " if cond else "FAIL: ") + name + (("  | " + str(extra)) if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


# ── 1. The logical folder `images` ───────────────────────────────────────────────────
import main as _main  # noqa: E402

check("there is a logical folder 'images' the client can name", "images" in _main._THU_MUC_LOGIC)
check("'sources' and 'attachments' are still there",
      "sources" in _main._THU_MUC_LOGIC and "attachments" in _main._THU_MUC_LOGIC)

# ── 2. One real upload: the image lands in the right place ──────────────────────────
from fastapi.testclient import TestClient  # noqa: E402

brain = tempfile.mkdtemp(prefix="brain-img-")
c = TestClient(_main.app, base_url="http://127.0.0.1")
r = c.post("/files/upload", data={"brain": brain, "folder": "images"},
           files={"file": ("2026-09-11-15-04-22.webp", b"RIFFxxxxWEBPVP8 ", "image/webp")}).json()
check("upload returns ok with the path it used", r.get("ok") and r.get("path"), r)
check("the returned path is inside images/", r.get("path", "").startswith("images/"), r)
check("the file really is inside images/",
      os.path.isfile(os.path.join(brain, "images", "2026-09-11-15-04-22.webp")),
      os.listdir(brain))
check("CANARY: does NOT create attachments/ (note images do not share the cache area)",
      not os.path.isdir(os.path.join(brain, "attachments")), os.listdir(brain))

# Two images pasted in the same second: the server must split the names, not overwrite the first.
r2 = c.post("/files/upload", data={"brain": brain, "folder": "images"},
            files={"file": ("2026-09-11-15-04-22.webp", b"RIFFyyyyWEBPVP8 ", "image/webp")}).json()
check("CANARY: two images in the same second get distinct names, no overwrite",
      r2.get("path") != r.get("path") and len(os.listdir(os.path.join(brain, "images"))) == 2,
      r2)

# SVG can carry script and note images render inline: the images folder takes raster only.
r_svg = c.post("/files/upload", data={"brain": brain, "folder": "images"},
               files={"file": ("evil.svg", b"<svg onload='alert(1)'/>", "image/svg+xml")})
check("CANARY: an .svg upload to images/ is rejected with 400", r_svg.status_code == 400, r_svg.text)
check("the rejected .svg is not written to disk",
      not any(n.endswith(".svg") for n in os.listdir(os.path.join(brain, "images"))),
      os.listdir(os.path.join(brain, "images")))
r_noext = c.post("/files/upload", data={"brain": brain, "folder": "images"},
                 files={"file": ("blob", b"xxxx", "application/octet-stream")})
check("a file with no image extension is rejected too", r_noext.status_code == 400, r_noext.text)
r_att = c.post("/files/upload", data={"brain": brain, "folder": "attachments"},
               files={"file": ("doc.svg", b"<svg/>", "image/svg+xml")})
check("other logical folders keep their old rules", r_att.status_code == 200, r_att.text)
shutil.rmtree(os.path.join(brain, "attachments"), ignore_errors=True)

# A brain with a folder named like "06 - Images" must REUSE it, not create a second one.
brain2 = tempfile.mkdtemp(prefix="brain-img2-")
os.makedirs(os.path.join(brain2, "06 - Images"))
r3 = c.post("/files/upload", data={"brain": brain2, "folder": "images"},
            files={"file": ("a.webp", b"RIFF", "image/webp")}).json()
check("CANARY: reuses the existing '06 - Images' folder, no second folder",
      sorted(os.listdir(brain2)) == ["06 - Images"], sorted(os.listdir(brain2)))
check("and the returned path points at that folder", "06 - Images/a.webp" in r3.get("path", ""), r3)

# ── 3. The media sweeper must NOT touch images/ ──────────────────────────────────────
brain3 = tempfile.mkdtemp(prefix="brain-gc-")
old = time.time() - 90 * 86400          # 90 days ago, far past the 30-day limit
for folder in ("images", "attachments", "inbox"):
    os.makedirs(os.path.join(brain3, folder), exist_ok=True)
    p = os.path.join(brain3, folder, "old-image.webp")
    with open(p, "wb") as f:
        f.write(b"RIFF" * 100)
    os.utime(p, (old, old))

areas = media_gc.media_dirs(brain3)
check("CANARY: images/ is NOT in the sweeper's cache area",
      not any(os.path.basename(d) == "images" for d in areas), areas)
check("attachments/ and inbox/ are still the cache area", len(areas) == 2, areas)

res = media_gc.sweep(brain3, max_age_days=30, max_mb=0)
check("the sweeper does delete old images in the cache area (the rule still runs)", res["files"] == 2, res)
check("CANARY: the note image in images/ is STILL THERE after sweeping",
      os.path.isfile(os.path.join(brain3, "images", "old-image.webp")))
check("the old image in attachments/ was swept (as designed before)",
      not os.path.isfile(os.path.join(brain3, "attachments", "old-image.webp")))

print()
if fails:
    print("FAIL - test_note_images: %d checks red" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("OK - test_note_images: all pass")
