"""0.197.0: unread count and @ mark per team, only the leader calls the owner, notifications per team with mute.

    python tests/python/test_team_unread_0197.py

Owner, 17/10/2026: "ở phần team cũng phải hiện chấm nổi bao nhiêu tin chưa đọc, có @ mình hay không và agent trưởng nhóm sẽ
được quyền tag chủ nhóm ... thông báo của team về cho chủ sẽ chỉ là những thông báo có được tag tên chủ ... team nào bị tắt
thông báo thì dù có tag tên cũng không báo về máy người dùng". Runs the real host, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sqlite3
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-unread-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-unread-brain-")).resolve()
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")

import main  # noqa: E402
import team_runner  # noqa: E402
import team_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


api = main._TEAM_API
sent = []


async def _fake_notify(session_id, text):
    sent.append((session_id, text))


def _spawn(coro):
    # Only the inbox delivery runs here; member turns (model calls) and socket packets are dropped.
    if getattr(getattr(coro, "cr_code", None), "co_name", "") == "go":
        return asyncio.run(coro)
    coro.close()


api.deps.spawn = _spawn
api.deps.notify = _fake_notify
published = []
api.deps.broadcast = lambda ev: (published.append(ev), _noop())[1]


async def _noop_coro():
    return None


def _noop():
    return _noop_coro()


client = TestClient(main.app, base_url="http://127.0.0.1:8080")
H = {"origin": "http://127.0.0.1:8080"}
B = str(BR)

r = client.post("/teams", params={"brain": B}, headers=H, json={"name": "Web bán hàng", "members": ["lan", "minh"],
                                                                 "leader_slug": "lan"})
team = r.json()["team"]
tid, sid = team["team_id"], team["session_id"]
keys = {m["slug_at_join"]: m["agent_key"] for m in api.teams().members(tid)}
lead, member = keys["lan"], keys["minh"]
runner = api.runner()


def row():
    return {t["team_id"]: t for t in client.get("/teams", params={"brain": B}).json()["teams"]}[tid]


check("a new team has nothing unread and is not muted", row()["unread"] == {"n": 0, "at": 0} and row()["muted"] is False,
      row())

# ---- unread ----
time.sleep(0.02)
runner._post(api.teams().get(tid), "Em đã xem xong bản nháp.", author_kind="agent", author_ref=member)
runner._post(api.teams().get(tid), "Đã giao việc cho Minh.", author_kind="system", role="system")
client.post(f"/teams/{tid}/messages", params={"brain": B}, headers=H, json={"text": "Ok", "client_msg_id": "u1"})
check("the owner's own message reads the team: earlier messages are no longer unread", row()["unread"]["n"] == 0,
      row()["unread"])
time.sleep(0.02)
runner._post(api.teams().get(tid), "Em đã xem xong bản nháp.", author_kind="agent", author_ref=member)
runner._post(api.teams().get(tid), "Đã giao việc cho Minh.", author_kind="system", role="system")
check("assistant and system messages after the owner read the team count as unread", row()["unread"] == {"n": 2, "at": 0},
      row()["unread"])

# ---- only the leader calls the owner ----
sent.clear()
m1 = runner._post(api.teams().get(tid), "@Chủ nhóm anh chọn mẫu A hay B?", author_kind="agent", author_ref=member)
check("a member calling @Chủ nhóm is not flagged and does not notify",
      not api.deps.session_store().team_message(sid, m1)["meta"].get("asks_owner") and sent == [], sent)
m2 = runner._post(api.teams().get(tid), "@Chủ nhóm anh chọn mẫu A hay B?", author_kind="agent", author_ref=lead)
check("the leader calling @Chủ nhóm is flagged", api.deps.session_store().team_message(sid, m2)["meta"].get("asks_owner") is True)
check("it reaches the owner's inbox once, with who called and the team name, without the raw @ tag",
      len(sent) == 1 and sent[0][0] == sid and "Lan" in sent[0][1] and "Web bán hàng" in sent[0][1]
      and "mẫu A hay B" in sent[0][1] and "@Chủ nhóm" not in sent[0][1], sent)
u = row()["unread"]
check("the list counts it and shows the @ mark", u == {"n": 4, "at": 1}, u)
check("plain messages never notify (only a call to the owner does)",
      len(sent) == 1)

# ---- read ----
published.clear()
r = client.post(f"/teams/{tid}/opened", params={"brain": B}, headers=H)
check("opening the team reads it: no unread, no @", r.status_code == 200 and row()["unread"] == {"n": 0, "at": 0}, row())
check("other pages and devices are told the team is read",
      any(e.get("type") == "team_read" and e.get("team_id") == tid for e in published), published)

# ---- mute ----
upd = api.teams().get(tid)["updated_at"]
r = client.post(f"/teams/{tid}/mute", params={"brain": B}, headers=H, json={"on": True})
check("POST /mute turns notifications off", r.status_code == 200 and r.json().get("muted") is True and row()["muted"] is True,
      r.text)
check("muting is not an edit (list order stays) but is logged",
      api.teams().get(tid)["updated_at"] == upd
      and any(e["kind"] == "muted" for e in api.teams().events(tid, 50)))
sent.clear()
time.sleep(0.02)
runner._post(api.teams().get(tid), "@Chủ nhóm anh duyệt giúp em.", author_kind="agent", author_ref=lead)
check("a muted team stays silent even when the leader calls the owner", sent == [], sent)
check("its unread count and @ still show on the list", row()["unread"] == {"n": 1, "at": 1}, row()["unread"])
runner._notify(tid, "Việc nhóm \"x\" bị chặn: thiếu quyền")
check("a muted team's other notices (a blocked job) stay silent too", sent == [], sent)
client.post(f"/teams/{tid}/mute", params={"brain": B}, headers=H, json={"on": False})
runner._post(api.teams().get(tid), "@Chủ nhóm xong rồi ạ.", author_kind="agent", author_ref=lead)
check("unmuted again: the call reaches the owner", len(sent) == 1, sent)
check("muting an unknown team is a 404",
      client.post("/teams/tm_nope/mute", params={"brain": B}, headers=H, json={"on": True}).status_code == 404)

# ---- no leader: anyone may call the owner ----
r = client.post("/teams", params={"brain": B}, headers=H, json={"name": "Không trưởng", "members": ["lan", "minh"]})
t2 = r.json()["team"]
if t2.get("leader_key"):
    api.teams().set_leader(t2["team_id"], None)
t2 = api.teams().get(t2["team_id"])
k2 = api.teams().members(t2["team_id"])[0]["agent_key"]
mx = runner._post(t2, "@Chủ nhóm cần anh quyết.", author_kind="agent", author_ref=k2)
check("a team with no leader: any member's call to the owner is flagged", not t2.get("leader_key")
      and api.deps.session_store().team_message(t2["session_id"], mx)["meta"].get("asks_owner") is True, t2)

# ---- prompt and migration ----
note = "\n".join(team_runner.INTERNAL_GROUP_NOTE)
check("members are told only the leader calls @Chủ nhóm and the others go through the leader",
      "Chỉ trưởng nhóm" in note and "@Chủ nhóm" in note and "gọi trưởng nhóm" in note)
db = Path(tempfile.mkdtemp(prefix="javis-team-mig-")) / "teams.db"
c = sqlite3.connect(db)
c.execute("CREATE TABLE teams(team_id TEXT PRIMARY KEY, brain_id TEXT, name TEXT, description TEXT, session_id TEXT, "
          "leader_key TEXT, leader_mode TEXT, status TEXT, caps_json TEXT, created_at REAL, updated_at REAL)")
c.execute("INSERT INTO teams VALUES('tm_old','b','Cũ','','s','','','active','{}',1.0,1.0)")
c.commit()
c.close()
before = time.time()
old = team_store.TeamStore(db).get("tm_old")
check("an existing team counts as read at the upgrade (no flood of old unread messages)",
      old is not None and old["read_at"] >= before - 1 and old["muted"] is False, old)

src = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
check("the page reads the open team as messages land and on returning to the tab",
      "readSoon()" in src and '"visibilitychange", onVisible' in src)
check("the mute switch reuses the pin saver", "function muteTeam(" in src and "return pinTeamWith(id, on, btn, {" in src)
check("app.js hands team_read to the Teams page",
      'data.type === "team_read"' in (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8"))
for name in ("server/team_store.py", "server/team_api.py", "server/team_runner.py", "server/sessions.py", "dashboard/teams.js"):
    s = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", "—" not in s and "–" not in s)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_team_unread_0197")
raise SystemExit(1 if fails else 0)
