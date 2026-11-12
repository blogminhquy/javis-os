"""A whole folder of the brain attached as a document: project, chat, agent and team (2026-11-12).

    python tests/run.py folder_documents

Owner: "chỉ chọn một file được thôi mà không tìm hiện ra được thư mục để chọn cả cái thư mục đấy". Every "add a document"
box searched file names only, and the three add routes refused a folder.

- A folder is ONE row whose stored path ends in "/". That slash is the whole marker: no table and no frontmatter key
  changed, and the prompt renderer and the dashboard read the same string.
- Listed, the model sees `[thư mục] name - path/` and opens what it needs. Pinned, a short tree of the folder is loaded,
  within the same caps as a pinned file.
- A team turn may be text only, so a folder added to a team is pinned at once: the tree is all such a turn can read.
- The empty path (the browse ceiling itself), a path outside the brain and a folder that is not there stay refused.
- media_gc keeps every file under a folder somebody attached.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-folder-docs-"))

from fastapi.testclient import TestClient  # noqa: E402
import main as M  # noqa: E402
import main_attachment_rendering as R  # noqa: E402
import media_gc  # noqa: E402
import team_docs  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:600] + "]") if not cond and extra != "" else ""))
    if not cond:
        fails.append(name)


brain = Path(tempfile.mkdtemp(prefix="javis-brain-folder-docs-")).resolve()
os.environ["JAVIS_FILES_ROOT"] = str(brain)          # the browse ceiling is this brain, as on a server
(brain / "agents").mkdir()
(brain / "agents" / "lan.md").write_text("---\nname: Lan\nrole: Thành viên\n---\nBạn là Lan.\n", encoding="utf-8")
(brain / "Dự án Web" / "thiet-ke").mkdir(parents=True)
(brain / "Dự án Web" / "bang-gia.md").write_text("# Bảng giá\nRửa xe 100k\n", encoding="utf-8")
(brain / "Dự án Web" / "thiet-ke" / "trang-chu.md").write_text("# Trang chủ\n", encoding="utf-8")
(brain / "trong").mkdir()
BRAIN = str(brain)

M.cfgmod.gate_active = lambda: False
M._TEAM_API.deps.spawn = lambda coro: coro.close() if hasattr(coro, "close") else None
c = TestClient(M.app, base_url="http://127.0.0.1")
store = M.get_store()

# ---- the search every "add a document" box asks ---------------------------------------------------------------------
found = c.get("/files/search", params={"brain": BRAIN, "mode": "name", "include_dirs": "true", "limit": 20, "q": "du an"}).json()["items"]
check("the search returns the folder, marked as one", [(i["name"], i.get("type")) for i in found] == [("Dự án Web", "dir")], found)
both = c.get("/files/search", params={"brain": BRAIN, "mode": "name", "include_dirs": "true", "limit": 20, "q": "thiet"}).json()["items"]
check("folders and files come back together", {i["name"] for i in both} == {"thiet-ke"}
      and c.get("/files/search", params={"brain": BRAIN, "mode": "name", "include_dirs": "true", "q": "trang"}).json()["items"][0]["name"] == "trang-chu.md", both)
_ui = (ROOT / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
_teams = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
check("CANARY: the documents drawer (project, chat, agent) asks for folders too",
      "include_dirs=true" in _ui.split("async function timFile", 1)[1].split("\n  function ", 1)[0])
check("CANARY: both team boxes (create, Info tab) ask for folders too", _teams.count("mode=name&include_dirs=true") == 2)
check("CANARY: a folder row has no 'delete from the brain' button", "xoaDuoc: con && !dir" in _ui)

# ---- a chat -------------------------------------------------------------------------------------------------------------
SID = "folder-docs-chat"
store.get_or_create(SID, brain=BRAIN, engine="cli", model="x")
API = f"/sessions/{SID}/assets"
r = c.post(API + "/files", data={"path": "Dự án Web"})
check("a chat takes a folder", r.status_code == 200 and r.json().get("ok") and r.json().get("dir") is True, r.text)
FID = r.json().get("id")
rows = store.list_session_files(SID)
check("stored as ONE row whose path ends in a slash", [(f["path"], f["name"]) for f in rows] == [("Dự án Web/", "Dự án Web")], rows)
again = [c.post(API + "/files", data={"path": p}).json().get("id") for p in ("Dự án Web/", "/Dự án Web", "Dự án Web")]
check("the same folder again, however it is spelled, is the same row", again == [FID] * 3 and len(store.list_session_files(SID)) == 1, again)
row = [f for f in c.get(API).json()["files"] if f.get("id") == FID][0]
check("the drawer is told it is a folder that exists", row.get("dir") is True and row.get("exists") is True
      and row.get("image") is False and row.get("brain_path") == "Dự án Web/", row)
block = M._session_block(SID)
check("listed, the prompt names it as a folder", "- [thư mục] Dự án Web - Dự án Web/" in block, block)
check("and loads nothing while it is not pinned", "bang-gia.md" not in block, block)
c.post(f"{API}/files/{FID}/pin", data={"pinned": "1"})
block = M._session_block(SID)
check("pinned, a short tree of the folder is loaded", "## Dự án Web - Dự án Web/" in block and "- bang-gia.md" in block
      and "- thiet-ke/" in block and "  - trang-chu.md" in block, block)
check("the tree lists names only, never a file's content", "Rửa xe 100k" not in block, block)
check("a pinned folder is not called a binary file", "nhị phân" not in block, block)

check("the empty path (the browse ceiling itself) is still refused",
      c.post(API + "/files", data={"path": ""}).status_code in (404, 422)
      and c.post(API + "/files", data={"path": "/"}).status_code == 404)
check("a folder that is not there is refused", c.post(API + "/files", data={"path": "khong-co"}).status_code == 404)
check("a folder outside the brain is refused", c.post(API + "/files", data={"path": "../"}).status_code == 400)

r = c.post(API + "/files", data={"path": "trong"})
c.post(f"{API}/files/{r.json().get('id')}/pin", data={"pinned": "1"})
check("an empty pinned folder says it is empty", "(thư mục đang trống)" in M._session_block(SID), M._session_block(SID))
(brain / "trong").rmdir()
row = [f for f in c.get(API).json()["files"] if f.get("path") == "trong/"][0]
check("a folder removed from disk stays in the list, marked gone", row.get("dir") is True and row.get("exists") is False, row)
check("and the prompt says it cannot be read", "- [thư mục, đã ghim nhưng đọc không được] trong - trong/" in M._session_block(SID))

# ---- a project ----------------------------------------------------------------------------------------------------------
pid = store.create_project("Web", brain=BRAIN)
r = c.post(f"/projects/{pid}/files", data={"path": "Dự án Web"})
check("a project takes a folder", r.status_code == 200 and r.json().get("dir") is True, r.text)
files = c.get(f"/projects/{pid}").json()["project"]["files"]
check("stored with the slash the drawer reads", [f["path"] for f in files] == ["Dự án Web/"], files)
check("the project block names it as a folder", "- [thư mục] Dự án Web - Dự án Web/" in M._project_block(pid), M._project_block(pid))
r2 = c.post(f"/projects/{pid}/files", data={"path": "Dự án Web/bang-gia.md"})
check("a file is still stored exactly as given", r2.status_code == 200 and r2.json().get("dir") is False
      and "Dự án Web/bang-gia.md" in [f["path"] for f in c.get(f"/projects/{pid}").json()["project"]["files"]], r2.text)

# ---- an agent -----------------------------------------------------------------------------------------------------------
AG = "/agents/lan/assets"
r = c.post(AG + "/files", data={"path": "Dự án Web", "brain": BRAIN})
check("an agent takes a folder", r.status_code == 200 and r.json().get("dir") is True, r.text)
d = c.get(AG, params={"brain": BRAIN}).json()
check("kept in the agent's own file, with the slash", [f["path"] for f in d["files"]] == ["Dự án Web/"]
      and "path: Dự án Web/" in (brain / "agents" / "lan.md").read_text(encoding="utf-8"), d)
meta = M._read_md(brain / "agents" / "lan.md")[0]
check("the agent's prompt names it as a folder", "- [thư mục] Dự án Web - Dự án Web/" in M._agent_assets_block(BRAIN, meta))

# ---- a team -------------------------------------------------------------------------------------------------------------
q = f"?brain={BRAIN}"
r = c.post(f"/teams{q}", json={"name": "Web", "members": ["lan"], "leader_slug": "lan",
                               "attachments": [{"brain_path": "Dự án Web/", "name": "Dự án Web"}]})
d = r.json()
check("a team is created with a folder among its documents", r.status_code == 200
      and [(f["name"], f["path"], f.get("dir")) for f in d["documents"]["files"]] == [("Dự án Web", "Dự án Web/", True)]
      and d["documents"]["failed"] == 0, d)
tid, sid = d["team"]["team_id"], d["team"]["session_id"]
trow = store.list_session_files(sid)
check("one row, pinned at once (a text-only turn can only read the tree)", [(f["path"], bool(f["pinned"])) for f in trow] == [("Dự án Web/", True)], trow)
tblock = M._team_docs_block(M._TEAM_API.teams().get(tid))
check("a member turn reads the folder's tree", "## Dự án Web - Dự án Web/" in tblock and "- bang-gia.md" in tblock, tblock[:600])
check("nothing was copied into the team's upload folder", not (brain / "attachments" / "teams" / tid).exists())
r = c.post(f"/teams/{tid}/files{q}", json={"attachments": [{"brain_path": "Dự án Web/thiet-ke", "name": "thiet-ke"}]})
check("the Info tab adds a folder to an existing team", r.status_code == 200
      and r.json()["files"] == [{"name": "thiet-ke", "path": "Dự án Web/thiet-ke/", "image": False, "dir": True}], r.json())
check("the brain root itself is not something to attach",
      team_docs.save([{"path": BRAIN, "name": "brain"}], staging=M.STAGING, brain_root=brain, dest_dir=brain / "x",
                     to_rel=lambda p: "", add=lambda rel, name: "id", pin=lambda fid: None, readable=()) == [])
outside = Path(tempfile.mkdtemp(prefix="javis-outside-dir-"))
check("a folder outside the brain never gets in",
      team_docs.save([{"path": str(outside), "name": "o"}], staging=M.STAGING, brain_root=brain, dest_dir=brain / "x",
                     to_rel=lambda p: "o", add=lambda rel, name: "id", pin=lambda fid: None, readable=()) == [])

# ---- the pure renderer --------------------------------------------------------------------------------------------------
limits = dict(list_max=15, allowed_suffixes=M.PROJECT_GHIM_DUOI, file_max=2000, total_max=6000)
files = [{"name": "Docs", "path": "docs/", "pinned": 0}, {"name": "Tree", "path": "tree/", "pinned": 1},
         {"name": "Gone", "path": "gone/", "pinned": 1}, {"name": "noext", "path": "noext", "pinned": 1}]
lines, sections = R.render_attachment_lists(files, [], [None, "- a.md\n- b/", None, None], **limits)
check("renderer: folder rows by their slash, a file with no extension as before", lines == [
    "- [thư mục] Docs - docs/", "- [thư mục, đã ghim nhưng đọc không được] Gone - gone/",
    "- [file, đã ghim nhưng là tệp nhị phân - tự mở khi cần] noext - noext"] and sections == ["\n## Tree - tree/\n- a.md\n- b/"], (lines, sections))
big = [{"name": str(i), "path": f"{i}/", "pinned": 1} for i in range(5)]
lines, sections = R.render_attachment_lists(big, [], ["x" * 5000] * 5, **limits)
check("renderer: a folder tree spends the same budget as a pinned file", len(sections) == 3
      and all(len(x) <= 2000 + 60 for x in sections) and len([x for x in lines if "hết chỗ nạp" in x]) == 2, (lines, [len(x) for x in sections]))

# ---- media_gc keeps what an attached folder holds -----------------------------------------------------------------------
gc_root = Path(tempfile.mkdtemp(prefix="javis-gc-dir-"))
entries = [(str(gc_root / "attachments" / "kept" / "a.png"), 10, 0.0), (str(gc_root / "attachments" / "kept" / "sub" / "b.png"), 10, 0.0),
           (str(gc_root / "attachments" / "kept-not" / "c.png"), 10, 0.0), (str(gc_root / "attachments" / "d.png"), 10, 0.0)]
gone = media_gc.plan_deletions(entries, 10 ** 9, 30, 0, giu_path={str(gc_root / "attachments" / "kept") + "/"})
check("media_gc: every file under an attached folder stays, a folder with a longer name does not ride along",
      sorted(Path(p).name for p in gone) == ["c.png", "d.png"], gone)
check("the store hands media_gc the folder with its slash", "Dự án Web/" in store.all_session_file_paths()
      and "Dự án Web/" in store.all_project_file_paths())

print("")
if fails:
    print(f"RED: {len(fails)}")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("All green.")
