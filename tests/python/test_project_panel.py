"""Project panel: instructions + documents + links attached to a group of conversations.

    python tests/run.py project_panel      (NO network)

Before this round `projects` was only a LABEL that grouped conversations to reduce clutter - it
did not change Javis's behaviour at all. Round 1 built the store + API so a project can carry
content: its own instructions, a list of documents in the brain, a list of links.

Two decisions worth guarding, because each has a wrong version that looks more reasonable:

1. `project_files` has NO `brain` column. The original spec had one. But a project already
   belongs to exactly one brain (`projects.brain`), and a file path only means something inside
   that brain. Storing the brain again here would let a project point at another brain's file -
   breaking exactly the fence `_safe_path` holds, and breaking it through DATA rather than a code
   bug, so no fence would catch it. The brain always comes from the project.

2. Deleting a project only UNLABELS its conversations, but DELETES its files/links outright. That
   is not inconsistent: a conversation has a life outside the project, while a project's
   documents mean nothing once the project is gone - leaving them is orphaned garbage.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-proj-"))

import sessions  # noqa: E402

_fails = []


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name
          + (("  [" + str(detail) + "]") if detail and not condition else ""))
    if not condition:
        _fails.append(name)


st = sessions.SessionStore(os.path.join(tempfile.mkdtemp(prefix="javis-proj-db-"), "s.db"))

# ============================================================
# 1. Instructions: save, edit, clear, and TRUNCATE AT SAVE TIME
# ============================================================
pid = st.create_project("Green Wood", brain="brain")
check("a new project has no instructions", not (st.get_project(pid) or {}).get("instructions"))

st.update_project(pid, instructions="Green palette. Avoid blue.")
check("instructions are saved",
      st.get_project(pid)["instructions"] == "Green palette. Avoid blue.")

st.update_project(pid, name="Green Wood 2")
check("renaming does NOT wipe the instructions (None = leave untouched)",
      st.get_project(pid)["instructions"] == "Green palette. Avoid blue.")

st.update_project(pid, instructions="")
check('passing "" CLEARS the instructions', st.get_project(pid)["instructions"] == "")

# Truncate in the STORE, not only when building the prompt: a cap at prompt time alone lets the
# store grow with every edit, and the user sees their text saved while Javis quietly reads only
# part of it.
st.update_project(pid, instructions="x" * (sessions.PROJECT_INSTRUCTIONS_MAX + 500))
check(f"instructions are cut to the {sessions.PROJECT_INSTRUCTIONS_MAX} cap at save time",
      len(st.get_project(pid)["instructions"]) == sessions.PROJECT_INSTRUCTIONS_MAX,
      len(st.get_project(pid)["instructions"]))
st.update_project(pid, instructions="Green palette.")

# ============================================================
# 2. Documents & links
# ============================================================
f1 = st.add_project_file(pid, "05 - Projects/price-list.md")
check("add a file, name derived from the path when none is given",
      st.get_project_full(pid)["files"][0]["name"] == "price-list.md")
check("adding the SAME path again returns the old id, no duplicate row",
      st.add_project_file(pid, "05 - Projects/price-list.md") == f1
      and len(st.get_project_full(pid)["files"]) == 1)
check("an empty path is rejected", st.add_project_file(pid, "   ") is None)

f2 = st.add_project_file(pid, "06 - Sources/brief.md", "Landing brief")
check("a custom name is kept",
      any(f["name"] == "Landing brief" for f in st.get_project_full(pid)["files"]))

l1 = st.add_project_link(pid, "https://elegant.vn", "Competitor")
check("add a link", len(st.get_project_full(pid)["links"]) == 1)
check("a duplicate URL does not create a second row",
      st.add_project_link(pid, "https://elegant.vn") == l1
      and len(st.get_project_full(pid)["links"]) == 1)

# Pinning moves to the top - this is the order the user sees, and also the order sent to the
# prompt.
st.set_project_file_pinned(pid, f2, True)
check("a pinned file jumps to the top of the list",
      st.get_project_full(pid)["files"][0]["id"] == f2,
      [f["name"] for f in st.get_project_full(pid)["files"]])
st.set_project_file_pinned(pid, f2, False)
check("unpinning goes back to newest-first order",
      st.get_project_full(pid)["files"][0]["id"] == f2)   # f2 was added later, so it stays first

# ============================================================
# 2b. Identical timestamps: newest-first must not depend on the clock ticking
# ============================================================
# Regression: on a fast machine two back-to-back adds can share one time.time() value, and
# the old ORDER BY (pinned, added_at) left the tie to SQLite, so the older row could come
# first. Freeze the clock so every row below gets the SAME added_at and check that
# insertion order (rowid) breaks the tie, for all four project/session asset lists.
from unittest import mock  # noqa: E402

pid_tie = st.create_project("Tie project", brain="brain")
st.get_or_create("s-tie", brain="brain", engine="cli", model="sonnet")
with mock.patch.object(sessions.time, "time", return_value=1_700_000_000.0):
    tf1 = st.add_project_file(pid_tie, "a/first.md")
    tf2 = st.add_project_file(pid_tie, "a/second.md")
    tl1 = st.add_project_link(pid_tie, "https://first.example")
    tl2 = st.add_project_link(pid_tie, "https://second.example")
    sf1 = st.add_session_file("s-tie", "a/first.md")
    sf2 = st.add_session_file("s-tie", "a/second.md")
    sl1 = st.add_session_link("s-tie", "https://first.example")
    sl2 = st.add_session_link("s-tie", "https://second.example")
_full_tie = st.get_project_full(pid_tie)
check("tie setup: both project files really share one timestamp",
      len({f["added_at"] for f in _full_tie["files"]}) == 1, _full_tie["files"])
check("same timestamp: project files still newest first",
      [f["id"] for f in _full_tie["files"]] == [tf2, tf1],
      [f["name"] for f in _full_tie["files"]])
check("same timestamp: project links still newest first",
      [l["id"] for l in _full_tie["links"]] == [tl2, tl1],
      [l["url"] for l in _full_tie["links"]])
check("same timestamp: session files still newest first",
      [f["id"] for f in st.list_session_files("s-tie")] == [sf2, sf1])
check("same timestamp: session links still newest first",
      [l["id"] for l in st.list_session_links("s-tie")] == [sl2, sl1])
st.set_project_file_pinned(pid_tie, tf1, True)
check("same timestamp: a pin still wins over the tie-break",
      [f["id"] for f in st.get_project_full(pid_tie)["files"]] == [tf1, tf2])
st.set_project_file_pinned(pid_tie, tf1, False)
check("same timestamp: unpinning goes back to newest first",
      [f["id"] for f in st.get_project_full(pid_tie)["files"]] == [tf2, tf1])
st.delete_project(pid_tie)

# ============================================================
# 3. No reaching into another project, even with a correctly guessed id
# ============================================================
pid2 = st.create_project("Other project", brain="brain")
check("deleting a file with the right id but the WRONG project does nothing",
      st.remove_project_file(pid2, f1) is False
      and len(st.get_project_full(pid)["files"]) == 2)
check("same for pinning", st.set_project_file_pinned(pid2, f1, True) is False)
check("same for links", st.remove_project_link(pid2, l1) is False)

# ============================================================
# 4. Left-hand list: COUNTS only, never pulls the instructions along
# ============================================================
row = [p for p in st.list_projects("brain") if p["id"] == pid][0]
check("list_projects counts files", row["file_count"] == 2, row)
check("list_projects counts links", row["link_count"] == 1, row)
check("and only says WHETHER there are instructions", row["has_instructions"] == 1, row)
check("does NOT include the instructions text (the list redraws very often)",
      "instructions" not in row, list(row.keys()))
check("nor the file/link lists", "files" not in row and "links" not in row)

# ============================================================
# 5. Deleting a project: conversations UNLABELED, files/links DELETED
# ============================================================
st.get_or_create("s-test", brain="brain", engine="cli", model="sonnet")
st.set_project("s-test", pid)
st.delete_project(pid)
check("the project is deleted", st.get_project(pid) is None)
check("get_project_full of a deleted project returns None", st.get_project_full(pid) is None)
_left_files = st._read("SELECT COUNT(*) c FROM project_files WHERE project_id = ?",
                       (pid,))[0]["c"]
_left_links = st._read("SELECT COUNT(*) c FROM project_links WHERE project_id = ?",
                       (pid,))[0]["c"]
check("the project's files are deleted with it, no orphaned rows", _left_files == 0, _left_files)
check("same for links", _left_links == 0, _left_links)
_conv = st._read("SELECT COUNT(*) c FROM sessions WHERE id = 's-test'")[0]["c"]
check("but the CONVERSATION remains (only unlabeled)", _conv == 1, _conv)
check("the other project is untouched", st.get_project(pid2) is not None)

# ============================================================
# 6. Source CANARY: nobody adds a brain column back to project_files
# ============================================================
_src = (SERVER / "sessions.py").read_text(encoding="utf-8")
_table = _src.split("CREATE TABLE IF NOT EXISTS project_files", 1)[1].split(");", 1)[0]
check("CANARY: project_files has NO brain column (the brain comes from the project)",
      "brain" not in _table, _table)
_main = (SERVER / "main.py").read_text(encoding="utf-8")
_add_route = _main.split("def projects_add_file", 1)[1].split("\n@app.", 1)[0]
check("CANARY: the add-file route takes the brain from the PROJECT, not from the client",
      'p.get("brain")' in _add_route and "brain: str = Form" not in _add_route,
      _add_route[:200])
check("CANARY: and checks the path with _safe_path before writing the store",
      "_safe_path(" in _add_route, _add_route[:200])
# ── Uploaded documents must land somewhere DURABLE, not in the cache area (owner, 02/09) ────
# attachments/ is pruned by media_gc by age (30 days by default) and by a size cap. A project's
# documents are attached for long-term use, so they must go to Sources.
_ui = (ROOT / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
_upload_fn = _ui.split("async function taiLenMot", 1)[1].split("\n  async function", 1)[0]
check("CANARY: project files upload into sources, NOT attachments",
      '"folder", "sources"' in _upload_fn and "attachments" not in _upload_fn,
      _upload_fn[:300])
# The SERVER finds the real folder name: a brain may call it "01 - Sources", and the browse
# root may sit above the brain root. Guessing with a hardcoded string in the frontend creates a
# second folder and the file goes astray.
check("CANARY: the frontend does not guess the folder name, it uses the path the server returns",
      "up.path" in _upload_fn and "homeCuaBrain" not in _ui, _upload_fn[:300])
_up = _main.split("async def files_upload", 1)[1].split("\n@app.", 1)[0]
check("the upload route takes a LOGICAL folder name and finds the real folder itself",
      "_THU_MUC_LOGIC" in _up and "_resolve_subfolder" in _up, _up[:300])
check("and returns the exact path it used so the caller need not rebuild it",
      '"path":' in _up and '"dir":' in _up, _up[:300])
check("an unknown folder name is rejected, nothing written at random",
      "Thư mục không hợp lệ" in _up, _up[:300])

# Safety net: even a file that already sat in attachments is no longer pruned once attached to
# a project. Without this the fix would only save NEW files, and old ones would still vanish
# silently.
check("CANARY: media_gc receives the project file list to spare",
      "all_project_file_paths" in _main
      and "giu_path" in (SERVER / "media_gc.py").read_text(encoding="utf-8"))
_ses = (SERVER / "sessions.py").read_text(encoding="utf-8")
check("the store returns every file path attached to a project",
      "def all_project_file_paths" in _ses)

_link = _main.split("def projects_add_link", 1)[1].split("\n@app.", 1)[0]
check("CANARY: links accept only http/https", "^https?://" in _link, _link[:200])

# ── One real upload, not just source inspection ──────────────────────────────────────────
# Inspecting strings only proves the code SAYS the right thing; it does not prove the file
# lands in the right place. The easiest case to get wrong is a brain that names the folder
# "01 - Sources": a hardcoded guess creates a second "sources" folder next to it, and the user
# opens Sources without finding the file they just uploaded.
from fastapi.testclient import TestClient  # noqa: E402
import main as _mainmod  # noqa: E402

_brain = tempfile.mkdtemp(prefix="brain-proj-")
os.makedirs(os.path.join(_brain, "01 - Sources"), exist_ok=True)
_c = TestClient(_mainmod.app, base_url="http://127.0.0.1")
_r = _c.post("/files/upload", data={"brain": _brain, "folder": "sources"},
             files={"file": ("report.pdf", b"%PDF-1.4 test", "application/pdf")}).json()
check("upload returns ok with the path it used", _r.get("ok") and _r.get("path"), _r)
check("CANARY: the file lands in the EXISTING Sources folder, no second folder created",
      sorted(os.listdir(_brain)) == ["01 - Sources"], sorted(os.listdir(_brain)))
check("and the file really is in there",
      os.listdir(os.path.join(_brain, "01 - Sources")) == ["report.pdf"])
check("the returned path points at that folder", "01 - Sources/report.pdf" in _r.get("path", ""))
_r2 = _c.post("/files/upload", data={"brain": _brain, "folder": "misc"},
              files={"file": ("x.txt", b"x", "text/plain")})
check("an unknown folder name is blocked with 400, nothing written to the brain",
      _r2.status_code == 400, _r2.text)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("ALL PASS")
