"""A team keeps taking pictures after its document list is full (2026-11-12).

    python tests/run.py team_docs_room

A customer: "up hình tới một lúc nó không cho up nữa". A conversation holds SESSION_ASSETS_MAX documents; each picture
sent in a team takes two places (the picture and its description), so the list filled after about 25 picture messages
and every later file was dropped without a word.

- Full list: the oldest pictures and picture descriptions of the team leave the list, the new file goes in. The file
  stays on disk. A document the owner attached never leaves by itself.
- A file that still cannot be kept (the list is full of the owner's documents) is said in the answer, never silent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-team-docs-room-"))

from fastapi.testclient import TestClient  # noqa: E402
import main as M  # noqa: E402
import sessions  # noqa: E402
import team_docs  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:500] + "]") if not cond and extra != "" else ""))
    if not cond:
        fails.append(name)


CAP = sessions.SESSION_ASSETS_MAX
brain = Path(tempfile.mkdtemp(prefix="javis-brain-team-docs-room-")).resolve()
(brain / "agents").mkdir()
(brain / "docs").mkdir()
(brain / "agents" / "lan.md").write_text("---\nname: Lan\nrole: Thành viên\n---\nBạn là Lan.\n", encoding="utf-8")
(brain / "docs" / "bang-gia.md").write_text("# Bảng giá\n", encoding="utf-8")

M._TEAM_API.deps.spawn = lambda coro: coro.close() if hasattr(coro, "close") else None
c = TestClient(M.app, base_url="http://127.0.0.1:8080")
q = f"?brain={brain}"
store = M.get_store()
M.STAGING.mkdir(parents=True, exist_ok=True)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def new_team(name):
    t = c.post(f"/teams{q}", json={"name": name, "members": ["lan"], "leader_slug": "lan"}).json()["team"]
    return t["team_id"], t["session_id"]


def stage(name, data=PNG):
    p = M.STAGING / name
    p.write_bytes(data)
    return {"path": str(p), "name": name}


# ---- the rule, on its own ---------------------------------------------------------------------------------------------
rows = [{"id": "pic1", "path": "attachments/teams/t1/1.png", "added_at": 1},
        {"id": "desc1", "path": "attachments/teams/t1/1 - mo ta anh.txt", "added_at": 2},
        {"id": "brain", "path": "docs/bang-gia.md", "added_at": 0},
        {"id": "pdf", "path": "attachments/teams/t1/hop-dong.pdf", "added_at": 0.5},
        {"id": "pic2", "path": "attachments/teams/t1/2.JPG", "added_at": 3},
        {"id": "desc2", "path": "attachments/teams/t1/x - mo ta anh (2).txt", "added_at": 2.5}]
check("the oldest picture leaves first", team_docs.rows_to_drop(rows, "attachments/teams/t1", 1) == ["pic1"])
check("only pictures and their descriptions may leave, oldest first",
      team_docs.rows_to_drop(rows, "attachments/teams/t1/", 9) == ["pic1", "desc1", "desc2", "pic2"])
check("another team's folder is not touched", team_docs.rows_to_drop(rows, "attachments/teams/t2", 3) == [])

# ---- a team that keeps getting pictures --------------------------------------------------------------------------------
tid, sid = new_team("Thiết kế Web")
c.post(f"/teams/{tid}/files{q}", json={"attachments": [{"brain_path": c.get(f"/files/search{q}&mode=name&q=bang-gia").json()["items"][0]["path"],
                                                        "name": "bang-gia.md"}, stage("hop-dong.txt", "Hợp đồng".encode("utf-8"))]})
kept = []
for i in range(CAP + 15):
    r = c.post(f"/teams/{tid}/messages{q}", json={"text": f"ảnh {i}", "client_msg_id": f"m{i}", "attachments": [stage(f"anh-{i:03d}.png")]})
    # Taken = the message went, carries the file's name, the file is a document of the team, and nothing was warned.
    kept.append(r.status_code == 200 and f"anh-{i:03d}.png" in r.json().get("text", "")
                and any(f["name"] == f"anh-{i:03d}.png" for f in store.list_session_files(sid))
                and not [n for n in (r.json().get("notes") or []) if "file" in n])
check(f"all {CAP + 15} pictures are taken, none dropped and no warning", all(kept), [i for i, k in enumerate(kept) if not k][:5])
names = [f["name"] for f in store.list_session_files(sid)]
check("the list stays within the cap", len(names) == CAP, len(names))
check("the newest picture is in the list, the oldest left it", f"anh-{CAP + 14:03d}.png" in names and "anh-000.png" not in names)
check("the owner's documents are still there", "bang-gia.md" in names and "hop-dong.txt" in names, names[:6])
check("a picture that left the list is still on disk", (brain / "attachments" / "teams" / tid / "anh-000.png").is_file())
texts = [m["content"] for m in c.get(f"/teams/{tid}/messages{q}&limit=200").json()["messages"]]
check("and its message still names it", any("anh-000.png" in t for t in texts))

# ---- a description takes its own place the same way ------------------------------------------------------------------
import asyncio  # noqa: E402
before = len(store.list_session_files(sid))
adder = M._team_doc_adder(store, sid, M._files_rel(M._files_root(str(brain)), brain / "attachments" / "teams" / tid))
out = team_docs.save_description(["anh-moi.png"], "Một chiếc xe màu đỏ", "Javis", dest_dir=brain / "attachments" / "teams" / tid,
                                 to_rel=lambda p: M._files_rel(M._files_root(str(brain)), Path(p)), add=adder,
                                 pin=lambda fid: store.set_session_file_pinned(sid, fid, True))
check("a picture description is kept on a full list too", bool(out) and len(store.list_session_files(sid)) == before == CAP, out)

# ---- a list full of the owner's own documents: said, not silent ------------------------------------------------------
tid2, sid2 = new_team("Tài liệu")
for i in range(CAP):
    store.add_session_file(sid2, f"docs/tai-lieu-{i}.md", f"tai-lieu-{i}.md")
r = c.post(f"/teams/{tid2}/messages{q}", json={"text": "xem ảnh này", "client_msg_id": "x1", "attachments": [stage("khong-vao.png")]})
d = r.json()
check("the message still goes when its file cannot be kept", r.status_code == 200 and d.get("message_id")
      and "khong-vao.png" not in d.get("text", ""), d)
check("and the answer says the file was left out, with the reason and the way out",
      any(str(CAP) in n and "Info" in n or str(CAP) in n and "Thông tin" in n for n in d.get("notes") or []), d.get("notes"))
r = c.post(f"/teams/{tid2}/messages{q}", json={"text": "", "client_msg_id": "x2", "attachments": [stage("khong-vao-2.png")]})
check("a file alone that cannot be kept is refused with that reason, not 'empty message'",
      r.status_code == 400 and str(CAP) in str(r.json().get("error")), r.json())
check("nothing of the owner's left the list", len(store.list_session_files(sid2)) == CAP)

print("")
if fails:
    print(f"RED: {len(fails)}")
    sys.exit(1)
print("All green.")
