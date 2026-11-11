# -*- coding: utf-8 -*-
"""Folder organizer: plans by rules and by Javis, safety rules, apply, undo, plugin ops and page routes.

    python tests/run.py file_organize

No network. Temporary JAVIS_STATE_DIR and folder tree; never touches a real drive.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

state = tempfile.mkdtemp(prefix="javis-organize-state-")
os.environ["JAVIS_STATE_DIR"] = state
os.environ["BRAINS_DIR"] = str(Path(state) / "brains")
os.environ["JAVIS_SESSIONS_DB"] = str(Path(state) / "sessions.db")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import file_scan as fs  # noqa: E402
import file_organize as fo  # noqa: E402
import plugins_host  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def write(p: Path, data: bytes, mtime=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if mtime:
        os.utime(p, (mtime, mtime))


T2024_03 = 1709900000  # 2024-03-08
T2025_07 = 1752000000  # 2025-07-08


def make_tree() -> Path:
    src = Path(tempfile.mkdtemp(prefix="javis-organize-src-"))
    write(src / "hoa don thang 3.pdf", os.urandom(3000), T2024_03)
    write(src / "Bao cao.docx", os.urandom(2000), T2025_07)
    write(src / "so lieu.xlsx", os.urandom(2000), T2025_07)
    write(src / "Downloads" / "clip.mp4", os.urandom(5000), T2025_07)
    write(src / "Downloads" / "setup.exe", os.urandom(4000), T2025_07)
    write(src / "Downloads" / "bo anh.zip", os.urandom(4000), T2025_07)
    write(src / "Downloads" / "data.weird", os.urandom(100), T2025_07)
    # Two files with the same name heading for the same folder.
    write(src / "Downloads" / "hoa don thang 3.pdf", os.urandom(1000), T2024_03)
    # A project folder: left whole.
    write(src / "web-app" / "package.json", b"{}")
    write(src / "web-app" / "src" / "index.js", b"console.log(1)")
    write(src / "web-app" / "logo.png", os.urandom(500))
    # Hidden and system files stay.
    write(src / ".hidden.txt", b"x")
    write(src / "Downloads" / "desktop.ini", b"x")
    # Already in the right place for mode "type".
    write(src / "Video" / "old.mp4", os.urandom(600), T2025_07)
    return src


# ---------- helpers ----------
check("folder names are made safe", fo.safe_part('a<b>:c?') == "a_b__c_" and fo.safe_part("  ..x.  ") == "x"
      and fo.safe_part("") == "_")
check("relative folders cannot climb out", fo.safe_rel("../../etc/x") == os.path.join("etc", "x")
      and fo.safe_rel("Khách hàng/ABC") == os.path.join("Khách hàng", "ABC"))
check("document types get their own subfolder",
      fo.dest_folder("document", "pdf", 2024, 3, "type") == os.path.join("Tài liệu", "PDF")
      and fo.dest_folder("document", "xlsx", 2024, 3, "type_year") == os.path.join("Tài liệu", "Excel", "2024")
      and fo.dest_folder("image", "jpg", 2024, 3, "type_month") == os.path.join("Ảnh", "2024", "2024-03")
      and fo.dest_folder("video", "mp4", 2024, 3, "date") == os.path.join("2024", "2024-03"))
check("folder names can be renamed", fo.dest_folder("image", "jpg", 2024, 3, "type", {"image": "Photos"}) == "Photos")

# ---------- plan by type ----------
src = make_tree()
plan = fo.build_plan(str(src), "type")
dst_of = {os.path.relpath(it["src"], src): os.path.relpath(it["dst"], src) for it in plan["items"]}
check("a PDF goes to Tài liệu/PDF", dst_of.get("hoa don thang 3.pdf") == os.path.join("Tài liệu", "PDF", "hoa don thang 3.pdf"), dst_of)
check("Word, Excel, video, installer, archive and other land in their folders",
      dst_of.get("Bao cao.docx") == os.path.join("Tài liệu", "Word", "Bao cao.docx")
      and dst_of.get("so lieu.xlsx") == os.path.join("Tài liệu", "Excel", "so lieu.xlsx")
      and dst_of.get(os.path.join("Downloads", "clip.mp4")) == os.path.join("Video", "clip.mp4")
      and dst_of.get(os.path.join("Downloads", "setup.exe")) == os.path.join("Phần mềm", "setup.exe")
      and dst_of.get(os.path.join("Downloads", "bo anh.zip")) == os.path.join("File nén", "bo anh.zip")
      and dst_of.get(os.path.join("Downloads", "data.weird")) == os.path.join("Khác", "data.weird"), dst_of)
pdfs = sorted(v for k, v in dst_of.items() if k.endswith("hoa don thang 3.pdf"))
check("two files with one name are numbered, never overwritten",
      pdfs == sorted([os.path.join("Tài liệu", "PDF", "hoa don thang 3.pdf"), os.path.join("Tài liệu", "PDF", "hoa don thang 3 (1).pdf")]), pdfs)
check("a project folder is left whole", not any(k.startswith("web-app") for k in dst_of) and plan["skipped"]["project"] == 3
      and any(p.endswith("web-app") for p in plan["projects"]), plan["skipped"])
check("hidden and system files stay", plan["skipped"]["hidden"] == 2 and not any(".hidden" in k or "desktop.ini" in k for k in dst_of))
check("a file already in place is not moved", plan["skipped"]["in_place"] == 1 and os.path.join("Video", "old.mp4") not in dst_of)
sm = fo.plan_summary(plan)
check("the summary groups by destination folder", sm["files"] == len(plan["items"]) == 8
      and {g["folder"] for g in sm["folders"]} >= {os.path.join("Tài liệu", "PDF"), "Video", "Khác"}, sm)
check("the plan is saved and can be read back", fo.current_plan()["id"] == plan["id"])
check("items of one folder can be listed", len(fo.plan_items(plan, os.path.join("Tài liệu", "PDF"))) == 2)
check("plans by month use the file date", os.path.join("Tài liệu", "PDF", "2024", "2024-03", "hoa don thang 3.pdf") in
      [os.path.relpath(it["dst"], src) for it in fo.build_plan(str(src), "type_month")["items"]])
top = fo.build_plan(str(src), "type", scope="top")
check("only loose files when asked", all(os.path.dirname(it["src"]) == str(src) for it in top["items"]) and len(top["items"]) == 3)
try:
    fo.build_plan(str(src / "nope"))
    check("a missing folder is refused", False)
except fo.OrganizeError as e:
    check("a missing folder is refused", str(e) == "no_source")

# A photo's EXIF date wins over its modified date.
if fs.pillow_ready():
    from PIL import Image
    im = Image.new("RGB", (64, 48), (200, 10, 10))
    exif = Image.Exif()
    exif[306] = "2019:05:20 10:00:00"
    im.save(src / "IMG_1.jpg", exif=exif)
    os.utime(src / "IMG_1.jpg", (T2025_07, T2025_07))
    p2 = fo.build_plan(str(src), "type_month")
    img = [it for it in p2["items"] if it["src"].endswith("IMG_1.jpg")]
    check("a photo is filed by the date it was taken", img and os.path.relpath(img[0]["dst"], src) == os.path.join("Ảnh", "2019", "2019-05", "IMG_1.jpg"), img)
    os.remove(src / "IMG_1.jpg")

# ---------- apply and undo ----------
fs.scan([str(src)], images=False)
plan = fo.build_plan(str(src), "type")
excl_file = str(src / "so lieu.xlsx")
res = fo.apply_plan(plan["id"], exclude=[excl_file], exclude_folders=["Phần mềm"])
check("apply moves the chosen files", res["moved"] == 6 and not res["skipped"], res)
check("a left-out file and a left-out folder stay put", (src / "so lieu.xlsx").exists() and (src / "Downloads" / "setup.exe").exists())
check("files are in their new place", (src / "Tài liệu" / "PDF" / "hoa don thang 3 (1).pdf").exists() or (src / "Tài liệu" / "PDF" / "hoa don thang 3.pdf").exists())
check("the project folder is untouched", (src / "web-app" / "src" / "index.js").exists() and (src / "web-app" / "logo.png").exists())
con = fs.connect()
row = con.execute("SELECT COUNT(*) FROM files WHERE path = ?", (str(src / "Video" / "clip.mp4"),)).fetchone()[0]
con.close()
check("the index follows the move", row == 1)
check("the plan is cleared after it ran", fo.current_plan() is None)
b = [x for x in fs.batches() if x["id"] == res["batch"]][0]
check("the run is an organize batch that can be undone", b["kind"] == "organize" and b["state"] == "organized" and b["files"] == 6, b)
try:
    fs.purge(res["batch"])
    check("an organize batch can never be purged", False)
except fs.QuarantineError:
    check("an organize batch can never be purged", True)
try:
    fo.apply_plan(plan["id"])
    check("a plan cannot run twice", False)
except fo.OrganizeError as e:
    check("a plan cannot run twice", str(e) == "no_plan")

out = fs.restore(res["batch"])
check("undo puts every file back", len(out["restored"]) == 6 and (src / "Downloads" / "clip.mp4").exists()
      and (src / "hoa don thang 3.pdf").exists() and (src / "Downloads" / "hoa don thang 3.pdf").exists(), out)
check("undo removes the folders it had created", not (src / "Tài liệu").exists() and not (src / "File nén").exists())
check("undo keeps folders that still hold files", (src / "Video" / "old.mp4").exists())
con = fs.connect()
back = con.execute("SELECT COUNT(*) FROM files WHERE path = ?", (str(src / "Downloads" / "clip.mp4"),)).fetchone()[0]
con.close()
check("the index follows the undo", back == 1)

# Changes after planning are respected.
plan = fo.build_plan(str(src), "type")
write(src / "Bao cao.docx", b"edited after the plan", T2025_07 + 99)
write(src / "Tài liệu" / "Excel" / "so lieu.xlsx", b"someone made this meanwhile")
res = fo.apply_plan(plan["id"])
check("a file edited after planning is skipped", any(r["reason"] == "changed" and r["path"].endswith("Bao cao.docx") for r in res["skipped"]), res)
check("a name taken after planning gets a number", (src / "Tài liệu" / "Excel" / "so lieu (1).xlsx").exists()
      and (src / "Tài liệu" / "Excel" / "so lieu.xlsx").read_bytes() == b"someone made this meanwhile")
fs.restore(res["batch"])
check("undo again leaves the other file alone", (src / "Tài liệu" / "Excel" / "so lieu.xlsx").exists() and (src / "so lieu.xlsx").exists())

# ---------- into another folder ----------
dest = Path(tempfile.mkdtemp(prefix="javis-organize-dest-"))
plan = fo.build_plan(str(src), "type", target=str(dest))
check("a target folder receives the structure", all(fs._under(it["dst"], str(dest)) for it in plan["items"]))
fo.discard_plan()
check("a plan can be discarded", fo.current_plan() is None)

# ---------- Javis's own plan ----------
plan = fo.propose_plan(str(src), [
    {"src": "hoa don thang 3.pdf", "folder": "Kế toán/Hoá đơn 2024"},
    {"src": str(src / "Bao cao.docx"), "folder": "Báo cáo"},
    {"src": "so lieu.xlsx", "folder": "../../ra ngoai"},
    {"src": "khong co.pdf", "folder": "X"},
    {"src": "web-app/logo.png", "folder": "Ảnh"},
    {"src": "hoa don thang 3.pdf", "folder": "Lặp lại"},
    {"src": "Downloads/clip.mp4", "folder": ""},
], note="theo chủ đề")
rel = {os.path.relpath(it["src"], src): os.path.relpath(it["dst"], src) for it in plan["items"]}
check("Javis's plan keeps valid moves", rel.get("hoa don thang 3.pdf") == os.path.join("Kế toán", "Hoá đơn 2024", "hoa don thang 3.pdf")
      and rel.get("Bao cao.docx") == os.path.join("Báo cáo", "Bao cao.docx"), rel)
check("a climbing folder is made safe inside the target", rel.get("so lieu.xlsx") == os.path.join("ra ngoai", "so lieu.xlsx"), rel)
check("missing files, project files, repeats and empty folders are dropped", plan["skipped"]["rejected"] == 4 and len(plan["items"]) == 3, plan["skipped"])
check("Javis's plan is marked as such", plan["by"] == "javis" and plan["mode"] == "topic" and plan["note"] == "theo chủ đề")
lst = fo.list_files(str(src))
check("the file list for Javis leaves out projects and hidden files",
      lst["total"] >= 8 and not any(f["rel"].startswith("web-app") or f["rel"].startswith(".") for f in lst["files"]), lst["total"])

# ---------- plugin ----------
spec = importlib.util.spec_from_file_location("javis_files_plugin_org", ROOT / "system/plugins/javis-files/plugin.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ctx = plugins_host.PluginContext("javis-files", "bundled", ROOT / "system/plugins/javis-files", "")
m.register(ctx)
tool = ctx._tools[0]
h = tool["handler"]
check("planning ops are read-only, carrying out needs full",
      all(tool["op_modes"][o] == "readonly" for o in ("organize_list", "organize_plan", "organize_propose", "organize_show"))
      and tool["op_modes"]["organize_apply"] == "full")
out = asyncio.run(h({"op": "organize_list", "roots": [str(src)]}, ctx))
check("organize_list shows relative paths", "hoa don thang 3.pdf" in out and "organize_propose" in out, out)
out = asyncio.run(h({"op": "organize_plan", "roots": [str(src)], "mode": "type_year"}, ctx))
check("organize_plan says nothing moved yet", "CHƯA chuyển" in out and "Tài liệu" in out, out)
pid = fo.current_plan()["id"]
check("organize_show reads the waiting plan", pid in asyncio.run(h({"op": "organize_show"}, ctx)))
out = asyncio.run(h({"op": "organize_apply", "plan_id": pid}, ctx))
check("organize_apply carries it out and says how to undo", "Đã chuyển" in out and "op=restore" in out, out)
bid = [b for b in fs.batches() if b["kind"] == "organize"][0]["id"]
out = asyncio.run(h({"op": "restore", "batch": bid}, ctx))
check("restore through the tool undoes it", "Đã khôi phục" in out and (src / "Bao cao.docx").exists(), out)
out = asyncio.run(h({"op": "organize_propose", "roots": [str(src)], "moves": [{"src": "Bao cao.docx", "folder": "Báo cáo"}]}, ctx))
check("organize_propose saves Javis's plan", "theo chủ đề" in out or "Javis tự xếp" in out, out)
check("organize_apply without an id is refused", asyncio.run(h({"op": "organize_apply"}, ctx)).startswith("ERROR"))
check("a wrong mode is explained", "mode phải" in asyncio.run(h({"op": "organize_plan", "roots": [str(src)], "mode": "x"}, ctx)))

# ---------- routes ----------
import main  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
app = FastAPI()
app.get("/filescan/organize/plan")(main.filescan_organize_get)
app.post("/filescan/organize/plan")(main.filescan_organize_build)
app.post("/filescan/organize/apply")(main.filescan_organize_apply)
app.post("/filescan/organize/discard")(main.filescan_organize_discard)
app.post("/filescan/restore")(main.filescan_restore)
c = TestClient(app)
r = c.post("/filescan/organize/plan", json={"source": str(src), "mode": "type"}).json()
check("the page can make a plan", r["ok"] and r["plan"]["files"] >= 6, r)
folder = r["plan"]["folders"][0]["folder"]
items = c.get("/filescan/organize/plan", params={"folder": folder}).json()["items"]
check("the page can open one folder of the plan", items and all("src" in i and "dst" in i for i in items))
check("a bad folder gets a message", not c.post("/filescan/organize/plan", json={"source": str(src / "nope")}).json()["ok"])
r2 = c.post("/filescan/organize/apply", json={"id": r["plan"]["id"], "exclude_folders": [folder]}).json()
check("the page can carry out the plan minus a folder", r2["ok"] and r2["moved"] == r["plan"]["files"] - r["plan"]["folders"][0]["files"], r2)
check("the page can undo", c.post("/filescan/restore", json={"batch": r2["batch"]}).json()["ok"] and (src / "Bao cao.docx").exists())
check("an outdated plan id is refused with a message", c.post("/filescan/organize/apply", json={"id": "old"}).json()["code"] == "no_plan")

for f in (Path(__file__), ROOT / "server/file_organize.py"):
    check(f"no em dash in {f.name}", "\u2014" not in f.read_text(encoding="utf-8"))

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
