"""Files, links and a working folder in a team chat (0.191.0).

    python tests/python/test_team_docs.py

Owner, 16/10/2026: a team chat needs what the main chat has: attach files, pin a working folder, documents and links
the whole team uses, and an info panel (members, files, links) behind the team picture. Team turns stay text only
(decision R3), so what a member reads is what the server puts in its prompt. Runs the real host, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-docs-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-docs-brain-"))
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n", encoding="utf-8")
(BR / "du-an" / "web" / "src").mkdir(parents=True)
(BR / "du-an" / "web" / "README.md").write_text("# Web\n", encoding="utf-8")
(BR / "tai-lieu.md").write_text("Giá sỉ: 50.000đ một chai.\n", encoding="utf-8")

import main  # noqa: E402
import team_docs  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


async def _quiet(ev):
    return None

main._CHAT_RUNTIME.publish = _quiet
main._TEAM_API.deps.spawn = lambda job: job.close() if hasattr(job, "close") else None
main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
H = {"origin": "http://127.0.0.1"}
b = str(BR)
r = client.post("/teams", params={"brain": b}, headers=H, json={"name": "Phòng Lập Trình", "members": ["lan", "minh"],
                                                               "leader_slug": "lan", "client_req_id": "r1"})
team = r.json()["team"]
tid, sid = team["team_id"], team["session_id"]
store = main.get_store()

# ---- attach in the composer ----
up = client.post("/upload", data={"brain": b}, files={"file": ("spec.md", b"# Spec\nTrang ban nuoc mam co gio hang.\n")}).json()
pdf_like = client.post("/upload", data={"brain": b}, files={"file": ("anh.png", b"\x89PNG fake")}).json()
r = client.post(f"/teams/{tid}/messages", params={"brain": b}, headers=H, json={
    "text": "Xem spec giúp anh", "mentions": [], "as_job": False, "client_msg_id": "c1",
    "attachments": [{"path": up["staged"], "name": "spec.md"}, {"path": pdf_like["staged"], "name": "anh.png"},
                    {"path": "/etc/hostname", "name": "lạ"}]})
check("a message with files is accepted", r.status_code == 200 and r.json().get("ok"), r.text)
msg = store.team_message(sid, r.json()["message_id"])
check("the message keeps the typed text and names the files for the team turns",
      msg["content"] == "Xem spec giúp anh\n\n📎 spec.md, anh.png", msg["content"])
check("the bubble gets the files as chips (meta), the picture marked as one",
      [f["name"] for f in msg["meta"]["files"]] == ["spec.md", "anh.png"] and msg["meta"]["files"][1]["image"], msg["meta"])
kept = BR / "attachments" / "teams" / tid / "spec.md"
check("an upload is copied into the brain (the staging area is swept after a few days)", kept.is_file())
check("a file from elsewhere on the machine is never pulled in", not any("hostname" in f["path"] for f in msg["meta"]["files"]))
files = {f["name"]: f for f in store.list_session_files(sid)}
check("both become team documents; the text one is pinned so every member reads it",
      files["spec.md"]["pinned"] and not files["anh.png"]["pinned"], files)
r = client.post(f"/teams/{tid}/messages", params={"brain": b}, headers=H, json={
    "text": "", "mentions": [], "as_job": False, "client_msg_id": "c2", "attachments": [{"path": up["staged"], "name": "spec.md"}]})
check("a message with only a file is fine", r.status_code == 200, r.text)

# ---- the team info panel's own add (no message) ----
r = client.post(f"/teams/{tid}/files", params={"brain": b}, headers=H,
                json={"attachments": [{"path": str(BR / "tai-lieu.md"), "name": "tai-lieu.md"}]})
check("a brain file added from the info panel stays where it is and is pinned",
      r.status_code == 200 and any(f["name"] == "tai-lieu.md" and f["pinned"] for f in store.list_session_files(sid)), r.text)
check("adding nothing usable says so",
      client.post(f"/teams/{tid}/files", params={"brain": b}, headers=H, json={"attachments": [{"path": "/etc/passwd"}]}).status_code == 400)
a = client.get(f"/sessions/{sid}/assets", params={"brain": b}).json()
check("the info panel reads the team's files from the conversation assets", {"spec.md", "anh.png", "tai-lieu.md"} <=
      {f["name"] for f in a["files"]}, a)
client.post(f"/sessions/{sid}/assets/links", data={"url": "https://zalo.me/g/abc", "label": ""})
check("links added in the panel are team links", any(l["url"] == "https://zalo.me/g/abc" for l in
                                                    client.get(f"/sessions/{sid}/assets", params={"brain": b}).json()["links"]))

# ---- what a member turn reads ----
blk = main._team_docs_block(dict(team, session_id=sid, brain_id=main._brain_key(b)))
check("member turns get the team documents with their content (text only turns cannot open files)",
      "TÀI LIỆU VÀ LINK CỦA NHÓM" in blk and "Trang ban nuoc mam co gio hang" in blk and "Giá sỉ: 50.000đ" in blk
      and "https://zalo.me/g/abc" in blk and "KHÔNG mở được file" in blk, blk[:600])
form = {"path": "du-an", "brain": b}
r = client.post(f"/coding/session/{sid}/pin", data=form)
check("a working folder pins on the team's conversation (same route as the main chat)", r.status_code == 200 and
      (r.json().get("folder") or {}).get("name") == "du-an", r.text)
blk = main._team_docs_block(dict(team, session_id=sid, brain_id=main._brain_key(b)))
check("member turns see the folder as a short tree", "THƯ MỤC LÀM VIỆC CỦA NHÓM" in blk and "- web/" in blk and "README.md" in blk, blk[-500:])
runner = main._TEAM_API.runner()
check("the runner adds the block to every member turn", runner.docs_block is not None
      and "THƯ MỤC LÀM VIỆC" in runner._docs(dict(team, session_id=sid, brain_id=main._brain_key(b))))
src = (ROOT / "server" / "team_runner.py").read_text(encoding="utf-8")
check("_prepare puts it between the team context and the message",
      "self._context(team, agent_key, role, task, step, authority_pin=pin) + self._docs(team)" in src)
check("tree keeps hidden folders out and stops at the cap",
      team_docs.tree(str(BR), cap=3)[-1].endswith("(còn nữa, đã cắt)") and not any(".x" in x for x in team_docs.tree(str(BR))))

# ---- the folder list says which folders have folders inside (the ">" of the picker) ----
d = client.get("/files/list", params={"brain": b, "subdirs": 1}).json()
rows = {i["name"]: i for i in d["items"] if i["type"] == "dir"}
check("subdirs=1: a folder with folders inside is marked, an empty one is not",
      rows["du-an"]["dirs"] is True and rows["agents"]["dirs"] is False, rows)
d = client.get("/files/list", params={"brain": b, "path": "du-an/web", "subdirs": 1}).json()
check("going inside lists the subfolder's folders", [i["name"] for i in d["items"] if i["type"] == "dir"] == ["src"], d)
check("without subdirs the file browser gets the same rows as before",
      "dirs" not in [i for i in client.get("/files/list", params={"brain": b}).json()["items"] if i["type"] == "dir"][0])

# ---- Javis Core has no jobs of its own: its Jobs tab says "no jobs yet", not "could not load" ----
import javis_core  # noqa: E402
r = client.get(f"/agents/{javis_core.SLUG}/jobs", params={"brain": b})
check("the Jobs tab of Javis Core gets an empty ok list (it used to be a 404 shown as a load error)",
      r.status_code == 200 and r.json().get("ok") and r.json()["jobs"] == [] and r.json()["total"] == 0, r.text)
check("an unknown assistant is still a 404", client.get("/agents/khong-co/jobs", params={"brain": b}).status_code == 404)

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_team_docs: all pass")
