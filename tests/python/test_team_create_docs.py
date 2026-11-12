"""Documents picked while creating a team, and brain files added to a team without uploading them again (2026-11-12).

    python tests/run.py team_create_docs

A customer: "tạo team mới thì lại phải up lại các file". The files were already in the brain; only the picker was
missing. Owner: "làm phần này khi tạo team luôn, thêm file và thêm link tài liệu".

- POST /teams takes `attachments` (a staged upload by `path`, or a brain file by `brain_path`, the path /files/search
  returns) and `links`. The team is made either way; the answer says what went in and how many did not.
- POST /teams/{id}/files takes the same `brain_path` form (the Info tab's search).
- A path that leaves the brain, and a link that is not http(s), never get in. A resend of the create request adds nothing.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-team-create-docs-"))

from fastapi.testclient import TestClient  # noqa: E402
import main as M  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:500] + "]") if not cond and extra != "" else ""))
    if not cond:
        fails.append(name)


brain = Path(tempfile.mkdtemp(prefix="javis-brain-team-create-docs-")).resolve()
(brain / "agents").mkdir()
(brain / "docs").mkdir()
(brain / "agents" / "lan.md").write_text("---\nname: Lan\nrole: Thành viên\n---\nBạn là Lan.\n", encoding="utf-8")
(brain / "docs" / "bang-gia.md").write_text("# Bảng giá\nRửa xe 100k\n", encoding="utf-8")
(brain / "docs" / "quy-trinh.md").write_text("# Quy trình\n", encoding="utf-8")
outside = Path(tempfile.mkdtemp(prefix="javis-outside-")) / "secret.md"
outside.write_text("not for a team", encoding="utf-8")

M._TEAM_API.deps.spawn = lambda coro: coro.close() if hasattr(coro, "close") else None
c = TestClient(M.app, base_url="http://127.0.0.1:8080")
q = f"?brain={brain}"
store = M.get_store()


def found(name):
    items = c.get(f"/files/search{q}&mode=name&limit=20&q={name}").json()["items"]
    return items[0]["path"]


def docs_of(sid):
    a = c.get(f"/sessions/{sid}/assets{q}").json()
    return [f["name"] for f in a["files"]], [l["url"] for l in a["links"]]


# ---- finding the file: words as people type them -------------------------------------------------------------------
names = lambda words: [i["name"] for i in c.get(f"/files/search{q}&mode=name&limit=20", params={"q": words}).json()["items"]]
check("several words find a name that holds them all, whatever sits between ('bảng giá' -> bang-gia.md)",
      names("bảng giá") == ["bang-gia.md"] and names("gia bang") == ["bang-gia.md"], (names("bảng giá"), names("gia bang")))
check("one word and a word that is not there behave as before", names("quy") == ["quy-trinh.md"] and names("bảng lương") == [],
      (names("quy"), names("bảng lương")))

# ---- a team created with a brain file, an uploaded file and a link ------------------------------------------------
M.STAGING.mkdir(parents=True, exist_ok=True)
staged = M.STAGING / "hop-dong.txt"
staged.write_text("Hợp đồng mẫu", encoding="utf-8")
price = found("bang-gia")
r = c.post(f"/teams{q}", json={
    "name": "Thiết kế Web", "members": ["lan"], "leader_slug": "lan", "client_req_id": "req-1",
    "attachments": [{"brain_path": price, "name": "bang-gia.md"}, {"path": str(staged), "name": "hop-dong.txt"},
                    {"brain_path": "../../../etc/passwd", "name": "passwd"}, {"path": str(outside), "name": "secret.md"}],
    "links": ["https://docs.google.com/document/d/1", "javascript:alert(1)", "https://docs.google.com/document/d/1"]})
d = r.json()
check("the team is created", r.status_code == 200 and d.get("ok") and d["team"]["team_id"], d)
doc = d.get("documents") or {}
check("the brain file and the upload went in", sorted(f["name"] for f in doc.get("files", [])) == ["bang-gia.md", "hop-dong.txt"], doc)
check("one link went in (the repeat counts once, the javascript: one is refused)", doc.get("links") == 1, doc)
check("the answer counts what did not go in: two bad paths and one bad link", doc.get("failed") == 3, doc)
tid, sid = d["team"]["team_id"], d["team"]["session_id"]
files, links = docs_of(sid)
check("the Info tab lists both files", {"bang-gia.md", "hop-dong.txt"} <= set(files), files)
check("and the link", links == ["https://docs.google.com/document/d/1"], links)
check("nothing from outside the brain got in", "secret.md" not in files and "passwd" not in files, files)
rows = {f["name"]: f for f in store.list_session_files(sid)}
check("text files are pinned, so member turns read them from the first message",
      rows.get("bang-gia.md", {}).get("pinned") and rows.get("hop-dong.txt", {}).get("pinned"), rows)
check("the brain file stays where it is (no copy)", (brain / "docs" / "bang-gia.md").is_file()
      and not (brain / "attachments" / "teams" / tid / "bang-gia.md").exists())
check("the upload is copied into the brain, under the team's folder", (brain / "attachments" / "teams" / tid / "hop-dong.txt").is_file())
block = M._team_docs_block(M._TEAM_API.teams().get(tid))
check("a member turn is told about the documents", "bang-gia.md" in block and "docs.google.com" in block, block[:300])

# ---- the same create request again adds nothing --------------------------------------------------------------------
r2 = c.post(f"/teams{q}", json={"name": "Thiết kế Web", "members": ["lan"], "leader_slug": "lan", "client_req_id": "req-1",
                                "attachments": [{"brain_path": found("quy-trinh"), "name": "quy-trinh.md"}],
                                "links": ["https://example.com/again"]})
d2 = r2.json()
check("a resend returns the team already made", d2.get("duplicate") is True and d2["team"]["team_id"] == tid, d2)
check("and adds no document", "documents" not in d2 and docs_of(sid) == (files, links), docs_of(sid))

# ---- a team without documents is created as before -----------------------------------------------------------------
r3 = c.post(f"/teams{q}", json={"name": "Không tài liệu", "members": ["lan"], "leader_slug": "lan"})
check("no documents asked: no `documents` in the answer", r3.status_code == 200 and "documents" not in r3.json(), r3.json())

# ---- documents that all fail never undo the team -------------------------------------------------------------------
r4 = c.post(f"/teams{q}", json={"name": "Hỏng tài liệu", "members": ["lan"], "leader_slug": "lan",
                                "attachments": [{"brain_path": "docs/khong-co.md", "name": "x"}], "links": ["ftp://a.b/c"]})
d4 = r4.json()
check("the team still exists when no document could be added", r4.status_code == 200 and d4["team"]["team_id"]
      and d4["documents"] == {"files": [], "links": 0, "failed": 2}, d4)

# ---- at most CREATE_DOCS_MAX of each ---------------------------------------------------------------------------------
import team_api  # noqa: E402
many = [f"https://example.com/{i}" for i in range(team_api.CREATE_DOCS_MAX + 5)]
r5 = c.post(f"/teams{q}", json={"name": "Nhiều link", "members": ["lan"], "leader_slug": "lan", "links": many})
check("links beyond the cap are left out", r5.json()["documents"]["links"] == team_api.CREATE_DOCS_MAX, r5.json().get("documents"))

# ---- the Info tab: a brain file joins an existing team ---------------------------------------------------------------
tid3, sid3 = r3.json()["team"]["team_id"], r3.json()["team"]["session_id"]
r6 = c.post(f"/teams/{tid3}/files{q}", json={"attachments": [{"brain_path": found("quy-trinh"), "name": "quy-trinh.md"}]})
check("POST /teams/{id}/files takes a brain file by its search path", r6.status_code == 200
      and [f["name"] for f in r6.json()["files"]] == ["quy-trinh.md"], r6.json())
check("and it shows in that team's documents", "quy-trinh.md" in docs_of(sid3)[0], docs_of(sid3))
r7 = c.post(f"/teams/{tid3}/files{q}", json={"attachments": [{"brain_path": "../outside.md", "name": "o"}]})
check("a path that leaves the brain is refused", r7.status_code == 400, r7.json())

print("")
if fails:
    print(f"RED: {len(fails)}")
    sys.exit(1)
print("All green.")
