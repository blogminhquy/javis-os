# -*- coding: utf-8 -*-
"""Disk cleanup page routes (/filescan/*): scan, overview, duplicates, look-alikes, thumbnails, quarantine round trip.

    python tests/run.py file_scan_routes

Real endpoints from main.py mounted on a bare FastAPI app with a temporary state folder and file tree, so no
background job or engine of the app starts and no real drive is read.
"""
from _paths import ROOT, SERVER  # noqa: F401
import os
import sys
import tempfile
import time
from pathlib import Path

state = tempfile.mkdtemp(prefix="javis-filescan-routes-")
os.environ["JAVIS_STATE_DIR"] = state
os.environ["BRAINS_DIR"] = str(Path(state) / "brains")
os.environ["JAVIS_SESSIONS_DB"] = str(Path(state) / "sessions.db")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
import file_scan as fs  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        fails.append(name)


app = FastAPI()
for method, path, fn in (
        ("get", "/filescan/drives", main.filescan_drives), ("get", "/filescan/status", main.filescan_status),
        ("post", "/filescan/scan", main.filescan_scan), ("post", "/filescan/cancel", main.filescan_cancel),
        ("get", "/filescan/overview", main.filescan_overview), ("get", "/filescan/duplicates", main.filescan_duplicates),
        ("get", "/filescan/similar", main.filescan_similar), ("get", "/filescan/thumb", main.filescan_thumb),
        ("get", "/filescan/quarantine", main.filescan_batches), ("post", "/filescan/quarantine", main.filescan_quarantine),
        ("post", "/filescan/restore", main.filescan_restore), ("post", "/filescan/purge", main.filescan_purge)):
    getattr(app, method)(path)(fn)
c = TestClient(app)

tree = Path(tempfile.mkdtemp(prefix="javis-filescan-routes-tree-"))
blob = os.urandom(120_000)
for sub in ("a", "b"):
    (tree / sub).mkdir()
    (tree / sub / "song.mp3").write_bytes(blob)
if fs.pillow_ready():
    from PIL import Image, ImageDraw
    # Stripes keep both files above the 10 KB floor that skips icons.
    im = Image.new("RGB", (800, 600), (30, 120, 200))
    dr = ImageDraw.Draw(im)
    for x in range(0, 800, 16):
        dr.rectangle([x, 0, x + 7, 600], fill=(x % 255, 60, 220 - x % 200))
    dr.ellipse([200, 100, 600, 500], fill=(240, 200, 30))
    im.save(tree / "photo.jpg", quality=95)
    im.resize((400, 300)).save(tree / "photo small.jpg", quality=70)

check("drives answer with a list", isinstance(c.get("/filescan/drives").json()["drives"], list))
check("scan without roots is refused with a message", not c.post("/filescan/scan", json={}).json()["ok"])
r = c.post("/filescan/scan", json={"roots": [str(tree / "missing")]}).json()
check("a missing folder is refused with a hint", not r["ok"] and r["message"], r)
r = c.post("/filescan/scan", json={"roots": [str(tree)], "images": True}).json()
check("scan starts", r["ok"] and r["running"] in (True, False), r)
fs.JOB.wait(60)
st = c.get("/filescan/status").json()
check("status reports the finished scan and Pillow", st["status"] == "done" and st["running"] is False and "pillow" in st, st)

ov = c.get("/filescan/overview").json()
check("overview has totals and duplicate figures", ov["files"] >= 2 and ov["dup_groups"] == 1 and ov["dup_wasted"] == len(blob), ov)
d = c.get("/filescan/duplicates", params={"limit": 10}).json()
check("duplicates list the song group", d["total"] == 1 and d["groups"][0]["count"] == 2, d)
check("a size floor above the files hides them", c.get("/filescan/duplicates", params={"min_kb": 1024}).json()["total"] == 0)

if fs.pillow_ready():
    s = c.get("/filescan/similar").json()
    check("look-alikes list the resized photo", s["pillow"] and s["total"] == 1, s)
    t = c.get("/filescan/thumb", params={"path": str(tree / "photo.jpg")})
    check("a thumbnail is served as JPEG", t.status_code == 200 and t.headers["content-type"] == "image/jpeg" and t.content[:2] == b"\xff\xd8")
check("a path outside the index gets no thumbnail", c.get("/filescan/thumb", params={"path": str(Path(SERVER) / "main.py")}).status_code == 404)

copy = d["groups"][0]["copies"][0]
check("quarantine without paths is refused", not c.post("/filescan/quarantine", json={}).json()["ok"])
q = c.post("/filescan/quarantine", json={"paths": [copy], "note": "route test"}).json()
check("quarantine moves the copy", q["ok"] and len(q["moved"]) == 1 and not os.path.exists(copy), q)
b = c.get("/filescan/quarantine").json()["batches"]
check("the batch is listed", b and b[0]["id"] == q["batch"] and b[0]["state"] == "quarantined", b)
r = c.post("/filescan/restore", json={"batch": q["batch"]}).json()
check("restore brings it back", r["ok"] and r["restored"] == [copy] and os.path.exists(copy), r)
check("restoring again says nothing is left", not c.post("/filescan/restore", json={"batch": q["batch"]}).json()["ok"])
q = c.post("/filescan/quarantine", json={"paths": [copy]}).json()
r = c.post("/filescan/purge", json={"batch": q["batch"]}).json()
check("purge deletes the quarantined copy for good", r["ok"] and r["deleted"] == 1 and not os.path.exists(copy), r)
check("the kept copy is untouched", (Path(d["groups"][0]["keep"])).read_bytes() == blob)
check("purge of an unknown batch is refused", not c.post("/filescan/purge", json={"batch": "nope"}).json()["ok"])

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
