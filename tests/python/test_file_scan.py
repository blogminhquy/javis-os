# -*- coding: utf-8 -*-
"""File scan and duplicate finder: index, three-pass duplicate search, NAS folders, rescans, plugin tool.

    python tests/run.py file_scan

No network. Uses a temporary JAVIS_STATE_DIR and a temporary folder tree; never reads the real drives.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-filescan-state-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import file_scan as fs  # noqa: E402
import plugins_host  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def write(p: Path, data: bytes, mtime=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if mtime:
        os.utime(p, (mtime, mtime))


base = Path(tempfile.mkdtemp(prefix="javis-filescan-tree-"))
root = base / "data"
photo = os.urandom(300_000)
write(root / "Photos" / "beach.jpg", photo, mtime=1_600_000_000)
write(root / "Downloads" / "beach (1).jpg", photo, mtime=1_700_000_000)
write(root / "Backup" / "old" / "beach.jpg", photo, mtime=1_700_000_100)
# Same size, same first and last 64 KB, different middle: must NOT be a duplicate.
edge = os.urandom(64 * 1024)
write(root / "Docs" / "a.bin", edge + b"A" * 50_000 + edge)
write(root / "Docs" / "b.bin", edge + b"B" * 50_000 + edge)
# Small identical files are compared through the edge hash, which already covers the whole file.
write(root / "Docs" / "note.txt", b"hello javis")
write(root / "Docs" / "note copy.txt", b"hello javis")
# Empty files never count as duplicates.
write(root / "Docs" / "empty1.txt", b"")
write(root / "Docs" / "empty2.txt", b"")
# Folders the scan skips: tool caches anywhere, NAS recycle bins and thumbnails.
write(root / "proj" / "node_modules" / "beach.jpg", photo)
write(root / "#recycle" / "beach.jpg", photo)
write(root / "Photos" / "@eaDir" / "beach.jpg", photo)
write(root / "Photos" / ".snapshot" / "beach.jpg", photo)
# A hard link takes no extra space, so it is not a duplicate of its own data.
hard_ok = True
try:
    os.link(root / "Docs" / "note.txt", root / "Docs" / "note-link.txt")
except Exception:
    hard_ok = False

# ---- helpers
check("human sizes read naturally", fs.human_size(512) == "512 B" and fs.human_size(1536) == "1.5 KB"
      and fs.human_size(3 * 1024 ** 3) == "3.0 GB")
check("categories by extension", fs.category("JPG") == "image" and fs.category("xlsx") == "document"
      and fs.category("weird") == "other")
check("a bare drive letter becomes a drive root", os.name != "nt" or fs.normalize_root("C:", resolve_mapped=False) == "C:\\")
check("UNC paths are network paths", fs.is_network_path(r"\\nas\share") and fs.is_network_path("//nas/share")
      and not fs.is_network_path(r"E:\data"))
if os.name == "nt":
    check("a UNC share keeps its form", fs.normalize_root(r"\\nas\share\Photos") == r"\\nas\share\Photos")
    check("a folder at the top of a UNC share is a top folder", fs._is_top(r"\\nas\share\Windows")
          and not fs._is_top(r"\\nas\share\Docs\Windows"))
    check("a folder at the top of a drive is a top folder", fs._is_top("E:\\Windows") and not fs._is_top("E:\\a\\Windows"))
else:
    check("a folder at the top of the filesystem is a top folder", fs._is_top("/proc") and not fs._is_top("/home/proc"))
check("mount escapes are decoded", fs._unescape_mount(r"E:\134") == "E:\\" and fs._unescape_mount(r"/mnt/my\040disk") == "/mnt/my disk")
gh = fs.classify_mount("E:\\", "/github", "9p", "ro,noatime,aname=drvfs;path=E:\\;uid=0")
check("a Docker Desktop bind mount reads as the host drive, read-only",
      gh == {"path": "/github", "kind": "local", "host": "E:\\", "fs": "9p", "readonly": True}, gh)
nas = fs.classify_mount("//nas/share", "/mnt/nas", "cifs", "rw,vers=3.0")
check("a cifs mount is a network drive with its share", nas and nas["kind"] == "network" and nas["unc"] == "//nas/share"
      and "readonly" not in nas, nas)
check("system and hidden mounts are not offered",
      all(fs.classify_mount(s, m, t, "rw") is None for s, m, t in (
          ("/dev/sde", "/etc/hostname", "ext4"), ("/dev/sde", "/home/javis/.claude", "ext4"), ("proc", "/proc", "proc"),
          ("E:\\", "/certs", "9p"), ("overlay", "/", "overlay"))))
check("a USB disk under /media is removable",
      fs.classify_mount("/dev/sdb1", "/media/usb", "vfat", "rw")["kind"] == "removable")
drives = fs.list_drives()
check("drives are listed with a kind", isinstance(drives, list) and all("path" in d and "kind" in d for d in drives))

# ---- first scan
res = fs.scan([str(root)])
check("scan counts every file outside skipped folders", res["files"] == 9 + (1 if hard_ok else 0), res)
check("skipped folders are counted", res["skipped"] >= 4, res)
groups = fs.duplicates([str(root)])
by_name = {os.path.basename(g["keep"]): g for g in groups}
check("the three copies of the photo form one group", "beach.jpg" in by_name and by_name["beach.jpg"]["count"] == 3,
      [g["keep"] for g in groups])
g = by_name.get("beach.jpg", {})
check("the oldest copy is the one suggested to keep", g.get("keep", "").endswith(os.path.join("Photos", "beach.jpg")))
check("wasted space is the extra copies", g.get("wasted") == 2 * len(photo))
check("skipped folders never show up in a group",
      not any(x in p for grp in groups for p in [grp["keep"]] + grp["copies"]
              for x in ("node_modules", "#recycle", "@eaDir", ".snapshot")))
check("same edges but a different middle is not a duplicate",
      not any(os.path.basename(gr["keep"]) in ("a.bin", "b.bin") for gr in groups))
notes = [gr for gr in groups if os.path.basename(gr["keep"]).startswith("note")]
check("identical small files are found through the edge hash", len(notes) == 1, notes)
if hard_ok:
    check("a hard link is not counted as a duplicate copy", notes and notes[0]["count"] == 2, notes)
check("empty files never form a group", not any(gr["size"] == 0 for gr in groups))
check("biggest waste comes first", groups and groups[0]["wasted"] == max(gr["wasted"] for gr in groups))

# ---- rescans only hash what changed
con = fs.connect()
hashes_before = dict(con.execute("SELECT path, full_hash FROM files WHERE full_hash IS NOT NULL"))
con.close()
res2 = fs.scan([str(root)])
check("a rescan of unchanged files hashes nothing", res2["hashed"] == 0, res2)
write(root / "Downloads" / "beach (1).jpg", photo[:-1] + b"\x00", mtime=1_700_000_500)
os.remove(root / "Backup" / "old" / "beach.jpg")
res3 = fs.scan([str(root)])
check("a changed file is hashed again", res3["hashed"] >= 1, res3)
groups = fs.duplicates([str(root)])
check("a changed copy and a deleted copy leave no photo group",
      not any(os.path.basename(gr["keep"]).startswith("beach") for gr in groups), [gr["keep"] for gr in groups])
con = fs.connect()
check("a deleted file leaves the index",
      con.execute("SELECT COUNT(*) FROM files WHERE path LIKE ?", ("%old%beach.jpg",)).fetchone()[0] == 0)
con.close()

# ---- nested roots: a narrower scan, then the wider one, never doubles rows
fs.scan([str(root / "Docs")])
fs.scan([str(root)])
con = fs.connect()
dup_rows = con.execute("SELECT COUNT(*) - COUNT(DISTINCT path) FROM files").fetchone()[0]
roots_rows = [r[0] for r in con.execute("SELECT root FROM roots")]
con.close()
check("each file is indexed once across nested roots", dup_rows == 0)
check("the wider scan replaces the narrower root entry", roots_rows == [fs.normalize_root(str(root))], roots_rows)

# ---- two places scanned in separate runs (the PC, then a NAS) still find copies across them
pc = base / "pc"
nas = base / "nas"
video = os.urandom(200_000)
write(pc / "Videos" / "trip.mp4", video)
write(nas / "Share" / "trip.mp4", video)
fs.scan([str(pc)])
check("one copy alone in the PC is not a duplicate yet",
      not any(os.path.basename(gr["keep"]) == "trip.mp4" for gr in fs.duplicates()))
fs.scan([str(nas)])
trip = [gr for gr in fs.duplicates() if os.path.basename(gr["keep"]) == "trip.mp4"]
check("a copy on the NAS matches the PC copy scanned earlier", len(trip) == 1 and trip[0]["count"] == 2, trip)
check("filtering by one place still shows the cross-place group only when both are asked for",
      not any(os.path.basename(gr["keep"]) == "trip.mp4" for gr in fs.duplicates([str(nas)])))
# A place that is switched off is not read (no time-outs per file), and its files are tried again later.
write(nas / "Share" / "trip2.mp4", video[:-1] + b"\x01")
write(pc / "Videos" / "trip2.mp4", video[:-1] + b"\x01")
fs.scan([str(nas)])
off = base / "nas-off"
os.rename(nas, off)
try:
    res_off = fs.scan([str(pc)])
    check("a scan works while another indexed place is offline", res_off["files"] >= 2, res_off)
finally:
    os.rename(off, nas)

# ---- stats and report
st = fs.stats([str(root)])
check("stats sum files and bytes", st["files"] >= 7 and st["bytes"] > 0, st)
check("stats group by category", {c["category"] for c in st["categories"]} >= {"image", "document"}, st["categories"])
check("heaviest folders are listed", st["folders"] and st["folders"][0]["bytes"] >= st["folders"][-1]["bytes"])
md = fs.report_markdown([str(root)])
check("the report says nothing was touched", "chưa di chuyển hay xoá" in md)
check("the report has no em dash", "\u2014" not in md)

# ---- plugin tool
vault = Path(tempfile.mkdtemp(prefix="javis-filescan-vault-"))
spec = importlib.util.spec_from_file_location("javis_files_plugin", ROOT / "system/plugins/javis-files/plugin.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ctx = plugins_host.PluginContext("javis-files", "bundled", ROOT / "system/plugins/javis-files", str(vault))
m.register(ctx)
tool = ctx._tools[0]
h = tool["handler"]
check("tool javis_files registered read-only, report needs safe",
      tool["name"] == "javis_files" and tool["min_mode"] == "readonly" and tool["op_modes"].get("report") == "safe"
      and all(tool["op_modes"].get(o) for o in m.OPS))

write(root / "Downloads" / "beach (2).jpg", photo, mtime=1_700_001_000)
out = asyncio.run(h({"op": "scan", "roots": [str(root)], "wait": 60}, ctx))
check("scan through the tool reports duplicates", "nhóm file trùng" in out and "Chưa di chuyển" in out, out)
out = asyncio.run(h({"op": "duplicates", "limit": 5}, ctx))
check("duplicates lists keep and copies", "giữ:" in out and "trùng:" in out, out)
out = asyncio.run(h({"op": "stats", "roots": [str(root)]}, ctx))
check("stats through the tool", "Theo loại" in out and "Ảnh" in out, out)
out = asyncio.run(h({"op": "report"}, ctx))
reports = list((vault / "exports").glob("bao-cao-quet-file-*.md"))
check("report is saved into exports/ of the brain", len(reports) == 1 and "exports/" in out, out)
out = asyncio.run(h({"op": "scan"}, ctx))
check("scan without roots asks where", out.startswith("ERROR") and "roots" in out)
out = asyncio.run(h({"op": "scan", "roots": [str(base / "missing")]}, ctx))
check("a missing folder explains what to check", out.startswith("ERROR") and "op=drives" in out, out)
out = asyncio.run(h({"op": "drives"}, ctx))
check("drives through the tool", "ổ" in out, out)
check("status after a scan summarises it", "Quét xong" in asyncio.run(h({"op": "status"}, ctx)))
check("cancel with nothing running says so", "Không có" in asyncio.run(h({"op": "cancel"}, ctx)))
check("unknown op -> clear error", asyncio.run(h({"op": "fly"}, ctx)).startswith("ERROR"))

# ---- background job: a slow scan answers with progress, then finishes
done_states = []
orig_scan = fs.scan


def slow_scan(*a, **k):
    time.sleep(1.5)
    return orig_scan(*a, **k)


fs.scan = slow_scan
try:
    m.fs.JOB.start([str(root)], on_done=lambda s: done_states.append(s))
    out = asyncio.run(h({"op": "scan", "roots": [str(root)], "wait": 0}, ctx))
    check("a second scan while one runs is refused", "Đang có một lượt quét" in out, out)
    m.fs.JOB.wait(30)
    check("the background scan finishes and calls back", done_states and done_states[0]["status"] == "done", done_states)
finally:
    fs.scan = orig_scan

# ---- quarantine: move, refuse the last copy, restore, purge
clean = base / "clean"
doc = os.urandom(150_000)
write(clean / "A" / "report.pdf", doc, mtime=1_600_000_000)
write(clean / "B" / "report.pdf", doc, mtime=1_650_000_000)
write(clean / "C" / "report.pdf", doc, mtime=1_700_000_000)
solo = os.urandom(90_000)
write(clean / "pair1.bin", solo)
write(clean / "pair2.bin", solo)
fs.scan([str(clean)], images=False)
qa, qb, qc = (str(clean / x / "report.pdf") for x in "ABC")
p1, p2 = str(clean / "pair1.bin"), str(clean / "pair2.bin")

res = fs.quarantine([p1, p2])
check("choosing every copy refuses all of them (the last copy always stays)",
      not res["moved"] and {r["reason"] for r in res["refused"]} == {"last_copy"} and os.path.exists(p1) and os.path.exists(p2), res)
check("a cleanup that moved nothing leaves no batch", res["batch"] == "" and not [b for b in fs.batches() if b["files"]])
check("an unknown path is refused", fs.quarantine([str(clean / "nope.txt")])["refused"][0]["reason"] == "not_indexed")

res = fs.quarantine([qb, qc], note="test")
batch = res["batch"]
qdir = clean / fs.QUARANTINE_DIR / batch
check("two of three copies move into quarantine", len(res["moved"]) == 2 and res["bytes"] == 2 * len(doc), res)
check("moved files sit under .javis-quarantine with the same relative path",
      (qdir / "B" / "report.pdf").exists() and (qdir / "C" / "report.pdf").exists() and not os.path.exists(qb))
check("the keeper stays where it was", os.path.exists(qa) and res["moved"][0]["keeper"] == qa)
check("quarantined copies leave the duplicate list",
      not any(os.path.basename(g["keep"]) == "report.pdf" for g in fs.duplicates([str(clean)])))
bl = fs.batches()
check("the batch is listed with its files and note", bl and bl[0]["id"] == batch and bl[0]["files"] == 2
      and bl[0]["note"] == "test" and bl[0]["state"] == "quarantined", bl[:1])
res2 = fs.scan([str(clean)], images=False)
check("a rescan skips the quarantine folder", res2["files"] == 3, res2)
check("after a rescan there are still no report duplicates",
      not any(os.path.basename(g["keep"]) == "report.pdf" for g in fs.duplicates([str(clean)])))

# A copy that changed after the scan is refused.
write(clean / "D" / "x.txt", b"same text here")
write(clean / "E" / "x.txt", b"same text here")
fs.scan([str(clean)], images=False)
write(clean / "E" / "x.txt", b"edited text!!!", mtime=1_800_000_000)
check("a copy edited since the scan is refused",
      fs.quarantine([str(clean / "E" / "x.txt")])["refused"][0]["reason"] == "changed")

out = fs.restore(batch)
check("restore puts every file back", sorted(out["restored"]) == sorted([qb, qc]) and os.path.exists(qb) and os.path.exists(qc), out)
check("restore removes the empty quarantine folders", not (clean / fs.QUARANTINE_DIR).exists())
check("restored files are back in the duplicate list",
      any(os.path.basename(g["keep"]) == "report.pdf" and g["count"] == 3 for g in fs.duplicates([str(clean)])))
check("a restored batch is marked restored", fs.batches()[0]["state"] == "restored")
try:
    fs.restore(batch)
    check("restoring twice says there is nothing left", False)
except fs.QuarantineError:
    check("restoring twice says there is nothing left", True)

res = fs.quarantine([qc])
write(Path(qc), b"someone put a new file here")
out = fs.restore(res["batch"])
check("a restore never overwrites a file that took the old place",
      out["kept"] and out["kept"][0]["reason"] == "taken" and Path(qc).read_bytes() == b"someone put a new file here", out)
check("the copy that could not go back stays in quarantine", fs.batches()[0]["state"] == "quarantined")
out = fs.purge(res["batch"])
check("purge deletes only the quarantined copy", out["deleted"] == 1 and out["bytes"] == len(doc)
      and Path(qc).read_bytes() == b"someone put a new file here" and os.path.exists(qa), out)
check("purge removes the empty quarantine folders", not (clean / fs.QUARANTINE_DIR).exists())
check("a purged batch is marked purged", fs.batches()[0]["state"] == "purged")

# ---- look-alike photos (needs Pillow)
if fs.pillow_ready():
    from PIL import Image, ImageDraw
    pics = base / "pics"
    pics.mkdir()
    big = Image.new("RGB", (1200, 900))
    d = ImageDraw.Draw(big)
    for i in range(0, 1200, 40):
        d.rectangle([i, 0, i + 20, 900], fill=(i % 255, 90, 200 - i % 150))
    d.ellipse([300, 200, 900, 700], fill=(250, 220, 40))
    big.save(pics / "original.jpg", quality=95)
    big.resize((600, 450)).save(pics / "small copy.jpg", quality=70)
    other = Image.new("RGB", (1200, 900), (20, 20, 20))
    ImageDraw.Draw(other).rectangle([0, 0, 600, 900], fill=(240, 240, 240))
    other.save(pics / "other.jpg", quality=90)
    res = fs.scan([str(pics)])
    check("photos get a fingerprint during the scan", res.get("images") == 3, res)
    sim = fs.similar([str(pics)])
    check("a resized copy is found as a look-alike", len(sim) == 1 and sim[0]["count"] == 2, sim)
    check("the larger picture is suggested to keep", sim and sim[0]["keep"].endswith("original.jpg") and sim[0]["files"][0]["w"] == 1200)
    check("a different picture is not grouped", not any(f["path"].endswith("other.jpg") for g in sim for f in g["files"]))
    check("a thumbnail is a small JPEG of an indexed photo", (fs.thumbnail(str(pics / "original.jpg")) or b"")[:2] == b"\xff\xd8")
    check("no thumbnail for a file outside the index", fs.thumbnail(str(base / "nope.jpg")) is None
          and fs.thumbnail(str(root / "Docs" / "note.txt")) is None)
    small = str(pics / "small copy.jpg")
    check("a look-alike is refused unless look-alikes are allowed", fs.quarantine([small])["refused"][0]["reason"] == "last_copy")
    res = fs.quarantine([small], allow_similar=True)
    check("with look-alikes allowed the smaller copy moves", len(res["moved"]) == 1 and not os.path.exists(small), res)
    fs.restore(res["batch"])
    check("and comes back on restore", os.path.exists(small))
    check("byte-identical photos stay in duplicates, not look-alikes",
          not any(os.path.basename(g["keep"]) == "beach.jpg" for g in fs.similar()))
else:
    print("skip look-alike photo checks: Pillow not installed")

# ---- plugin ops for cleanup
check("quarantine and restore need full, similar and batches are read-only",
      tool["op_modes"]["quarantine"] == "full" and tool["op_modes"]["restore"] == "full"
      and tool["op_modes"]["similar"] == "readonly" and tool["op_modes"]["batches"] == "readonly")
check("there is no delete-for-good op in the tool", "purge" not in m.OPS and "delete" not in m.OPS)
out = asyncio.run(h({"op": "quarantine", "paths": [qb]}, ctx))
check("quarantine through the tool names the batch and how to restore", "cách ly" in out and "op=restore" in out, out)
bid = fs.batches()[0]["id"]
out = asyncio.run(h({"op": "batches"}, ctx))
check("batches through the tool lists the batch", bid in out, out)
out = asyncio.run(h({"op": "restore", "batch": bid}, ctx))
check("restore through the tool", "Đã khôi phục 1 file" in out and os.path.exists(qb), out)
check("restore without a batch -> clear error", asyncio.run(h({"op": "restore"}, ctx)).startswith("ERROR"))
check("quarantine without paths -> clear error", asyncio.run(h({"op": "quarantine"}, ctx)).startswith("ERROR"))
if fs.pillow_ready():
    out = asyncio.run(h({"op": "similar"}, ctx))
    check("similar through the tool lists the look-alike group", "original.jpg" in out and "gần giống" in out, out)

for f in (Path(__file__), ROOT / "server/file_scan.py", ROOT / "system/plugins/javis-files/plugin.py",
          ROOT / "system/plugins/javis-files/plugin.yaml", ROOT / "dashboard/cleanup.js", ROOT / "dashboard/cleanup.css"):
    check(f"no em dash in {f.name}", "\u2014" not in f.read_text(encoding="utf-8"))

print(f"\n{len(_fails)} failed" if _fails else "\nall passed")
sys.exit(1 if _fails else 0)
