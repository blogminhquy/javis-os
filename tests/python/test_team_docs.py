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
      "self._context(team, agent_key, role, task, step, authority_pin=pin)\n" in src
      and "+ self._docs(team, tool_turn) + \"\\n\\n\" + body" in src)
# 0.194.0: a Work/Help turn can open the files and the folder itself, so its block says so instead of "cannot open".
tblk = main._team_docs_block(dict(team, session_id=sid, brain_id=main._brain_key(b)), tools=True)
check("tool turns: the block says the turn can open the files and works in the folder",
      "có công cụ" in tblk and "KHÔNG mở được file" not in tblk and "chạy ngay trong thư mục đó" in tblk
      and "- web/" in tblk, tblk[:600])
check("tool turns through the runner get the tool wording, chat turns keep the text-only wording",
      "chạy ngay trong thư mục đó" in runner._docs(dict(team, session_id=sid, brain_id=main._brain_key(b)), True)
      and "Lượt nhóm không mở được file" in runner._docs(dict(team, session_id=sid, brain_id=main._brain_key(b))))
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

# ---- 0.192.0: pictures are described for the text-only member turns ----
import asyncio  # noqa: E402
import team_api  # noqa: E402
seen = {}


async def _fake_eyes(images, text, prov, api_model, chat_id=""):
    seen["args"] = (list(images), text, chat_id)
    return "Bảng giá: nước mắm 50.000đ, chai 500ml.", "openai-oauth/gpt-test", ""

main._bot_xem_ho = _fake_eyes
pic = client.post("/upload", data={"brain": b}, files={"file": ("bang-gia.png", b"\x89PNG fake2")}).json()
kept_pic = main._team_attach(dict(team, session_id=sid), [{"path": pic["staged"], "name": "bang-gia.png"}])
check("a picture is kept as a team document, marked as a picture", kept_pic and kept_pic[0]["image"], kept_pic)
asyncio.run(main._team_describe(dict(team, session_id=sid, brain_id=main._brain_key(b)), kept_pic, "giá bao nhiêu"))
check("another brain looks at the picture itself (the file in the brain), with the message as caption",
      seen.get("args") and seen["args"][0][0].endswith("bang-gia.png") and seen["args"][1] == "giá bao nhiêu"
      and seen["args"][2] == f"team:{tid}", seen)
desc = [f for f in store.list_session_files(sid) if f["name"] == "bang-gia.png (mô tả ảnh)"]
check("what it saw becomes a pinned team document", desc and desc[0]["pinned"], store.list_session_files(sid))
blk = main._team_docs_block(dict(team, session_id=sid, brain_id=main._brain_key(b)))
check("member turns read the description, and are told that is how they see a picture",
      "nước mắm 50.000đ" in blk and "openai-oauth/gpt-test" in blk and "mô tả ảnh" in blk, blk[:900])


async def _no_eyes(images, text, prov, api_model, chat_id=""):
    return "", "", "không bộ não nào xem được"

main._bot_xem_ho = _no_eyes
n0 = len(store.list_session_files(sid))
asyncio.run(main._team_describe(dict(team, session_id=sid, brain_id=main._brain_key(b)), kept_pic, ""))
check("no brain could look: nothing is invented", len(store.list_session_files(sid)) == n0)
check("the host wires the describer into team chat", main._TEAM_API.deps.describe is main._team_describe)
order = []


class _Api:
    class deps:
        @staticmethod
        async def describe(team, pics, caption):
            order.append("describe")


async def _turns():
    order.append("turns")

asyncio.run(team_api._described_then(_Api, team, kept_pic, "", _turns))
check("the member turns of a message with a picture start only after the picture is described",
      order == ["describe", "turns"], order)


class _SlowApi:
    class deps:
        @staticmethod
        async def describe(team, pics, caption):
            raise RuntimeError("engine down")

order.clear()
asyncio.run(team_api._described_then(_SlowApi, team, kept_pic, "", _turns))
check("a failed description never stops the turns", order == ["turns"], order)
src = (ROOT / "server" / "team_api.py").read_text(encoding="utf-8")
check("send and the info panel both describe new pictures",
      src.count("_described_then(api, team, pics,") == 3 and "DESCRIBE_TIMEOUT_S = 120.0" in src)

# ---- 0.192.0: who is writing right now (the "is typing" strip) ----
teams_store = main._TEAM_API.teams()
key = team["members"][0]["agent_key"] if team.get("members") else teams_store.get(tid)["leader_key"]
events = []
runner = main._TEAM_API.runner()
runner._publish_fn = lambda ev: events.append(ev)
turn = teams_store.reserve_turn(tid, None, None, key, "member_reply")
check("a turn still waiting for its seat is not typing yet", teams_store.active_turns(tid) == [])
runner._mark_engine(turn, "fake", "m")
check("a turn at the engine is typing, and the chat is told",
      [t["agent_key"] for t in teams_store.active_turns(tid)] == [key]
      and any(e.get("type") == "team_typing" and e["team_id"] == tid and e["typing"][0]["agent_key"] == key
              and e["typing"][0]["role"] == "member_reply" for e in events), events)
g = client.get(f"/teams/{tid}", params={"brain": b}).json()
check("opening the team returns who is typing", [t["agent_key"] for t in g.get("typing") or []] == [key], g.get("typing"))
events.clear()
runner._settle_turn(turn, "ok")
check("the turn ends: nobody is typing, the chat is told",
      teams_store.active_turns(tid) == [] and events and events[-1]["typing"] == [], events)

# ---- 0.192.0: @all, the owner flag, pinned messages ----
r = client.post(f"/teams/{tid}/messages", params={"brain": b}, headers=H, json={
    "text": "@all họp nhanh nhé", "mentions": [], "mention_all": True, "as_job": False, "client_msg_id": "all1"})
allm = store.team_message(sid, r.json().get("message_id") or 0) or {}
everyone = [m["agent_key"] for m in teams_store.members(tid)]
check("@all calls every active member, leader first, past the per-message @ cap",
      r.status_code == 200 and sorted(allm.get("meta", {}).get("mentions") or []) == sorted(everyone)
      and allm["meta"].get("mention_all") is True, (r.text, allm.get("meta")))
check("without @all the cap still holds", "if len(wanted) > cap and not mention_all:" in
      (ROOT / "server" / "team_runner.py").read_text(encoding="utf-8"))
import team_runner  # noqa: E402
# 0.197.0: only the leader's call to the owner is flagged (test_team_unread_0197.py covers the other members).
lead_key = teams_store.get(tid)["leader_key"]
mid_ask = runner._post(teams_store.get(tid), "@Chủ nhóm ơi, anh chọn mẫu A hay B?", author_kind="agent", author_ref=lead_key)
mid_no = runner._post(teams_store.get(tid), "Em làm xong rồi, gửi @Lan xem.", author_kind="agent", author_ref=lead_key)
check("the leader calling the owner is flagged; calling a teammate is not",
      store.team_message(sid, mid_ask)["meta"].get("asks_owner") is True
      and not store.team_message(sid, mid_no)["meta"].get("asks_owner"))
check("team members are told to tag the owner and each other",
      any("@Chủ nhóm" in line for line in team_runner.INTERNAL_GROUP_NOTE))
client.post(f"/teams/{tid}/messages/{mid_ask}/decision", params={"brain": b}, headers=H, json={"on": True})
g = client.get(f"/teams/{tid}", params={"brain": b}).json()
check("opening the team returns its pinned messages for the pinned strip",
      [p["id"] for p in g.get("pinned") or []] == [mid_ask] and "mẫu A hay B" in g["pinned"][0]["content"], g.get("pinned"))
client.post(f"/teams/{tid}/messages/{mid_ask}/decision", params={"brain": b}, headers=H, json={"on": False})
check("unpinned: off the strip", client.get(f"/teams/{tid}", params={"brain": b}).json().get("pinned") == [])

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_team_docs: all pass")
