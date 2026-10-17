"""0.195.0: team project tags, and the Teams page opens the team the owner worked in last.

    python tests/python/test_team_tags.py

Owner, 17/10/2026: "khi vào team thì sẽ vào đoạn chat mà chủ team đang làm việc gần nhất", "trong team cũng phải gắn được
tag phân loại ... nhiều team đang triển khai cùng 1 dự án thì sẽ có thể add vào 1 tag". Runs the real host, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-tags-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-tags-brain-")).resolve()
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")

import main  # noqa: E402
import team_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


api = main._TEAM_API
api.deps.spawn = lambda coro: coro.close() if hasattr(coro, "close") else None
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
H = {"origin": "http://127.0.0.1:8080"}
B = str(BR)

# ---- cleaning ----
ct = team_store.clean_tags
check("tags are trimmed, inner spaces collapsed, empties and case duplicates dropped (first spelling kept)",
      ct(["  Web  bán hàng ", "web bán HÀNG", "", "Q4"]) == ["Web bán hàng", "Q4"], ct(["  Web  bán hàng ", "web bán HÀNG", "", "Q4"]))
check("a comma separated string is accepted", ct("A, B ,a") == ["A", "B"])
check("at most TAGS_MAX tags of at most TAG_CHARS characters",
      len(ct([f"t{i}" for i in range(20)])) == team_store.TAGS_MAX and len(ct(["x" * 80])[0]) == team_store.TAG_CHARS)
try:
    ct(42)
    bad = False
except team_store.TeamError:
    bad = True
check("a non-list is refused", bad)


def make(name):
    r = client.post("/teams", params={"brain": B}, headers=H, json={"name": name, "members": ["lan", "minh"], "leader_slug": "lan"})
    return r.json()["team"]


t1, t2, t3 = make("Nội dung Web"), make("Quảng cáo Web"), make("Game")
check("a new team has no tags and no owner time", t1.get("tags") == [] and t1.get("owner_at") is None, t1)

# ---- PATCH tags ----
for t in (t1, t2):
    r = client.patch(f"/teams/{t['team_id']}", params={"brain": B}, headers=H, json={"tags": ["Web bán hàng", " web bán hàng "]})
check("PATCH stores cleaned tags and returns them", r.status_code == 200 and r.json()["team"]["tags"] == ["Web bán hàng"], r.text)
r = client.patch(f"/teams/{t1['team_id']}", params={"brain": B}, headers=H, json={"tags": "nope"})
check("PATCH with a plain string still cleans it into a list", r.status_code == 200 and r.json()["team"]["tags"] == ["nope"], r.text)
client.patch(f"/teams/{t1['team_id']}", params={"brain": B}, headers=H, json={"tags": ["Web bán hàng", "Q4"]})
lst = client.get("/teams", params={"brain": B}).json()["teams"]
by = {t["team_id"]: t for t in lst}
check("GET /teams carries every team's tags; two teams share one tag",
      by[t1["team_id"]]["tags"] == ["Web bán hàng", "Q4"] and by[t2["team_id"]]["tags"] == ["Web bán hàng"]
      and by[t3["team_id"]]["tags"] == [], {k: v["tags"] for k, v in by.items()})
ev = [e for e in api.teams().events(t1["team_id"], 50) if e["kind"] == "updated"]
check("changing tags is logged like any team edit (before and after)",
      any(e["after"].get("tags") == ["Web bán hàng", "Q4"] and e["before"].get("tags") == ["nope"] for e in ev), ev)
r = client.patch(f"/teams/{t1['team_id']}", params={"brain": B}, headers=H, json={"tags": []})
check("an empty list removes every tag", r.json()["team"]["tags"] == [])

# ---- last worked team ----
order_before = [t["team_id"] for t in client.get("/teams", params={"brain": B}).json()["teams"]]
upd_before = api.teams().get(t3["team_id"])["updated_at"]
r = client.post(f"/teams/{t3['team_id']}/opened", params={"brain": B}, headers=H)
after = api.teams().get(t3["team_id"])
check("POST /opened marks the owner's time on that team", r.status_code == 200 and after["owner_at"], r.text)
check("opening is not an edit: list order and updated_at stay",
      after["updated_at"] == upd_before and [t["team_id"] for t in client.get("/teams", params={"brain": B}).json()["teams"]]
      == order_before)
check("opening an unknown team is a 404", client.post("/teams/tm_nope/opened", params={"brain": B}, headers=H).status_code == 404)
time.sleep(0.02)
client.post(f"/teams/{t2['team_id']}/messages", params={"brain": B}, headers=H, json={"text": "Chào cả nhóm", "client_msg_id": "m1"})
o2, o3 = api.teams().get(t2["team_id"])["owner_at"], api.teams().get(t3["team_id"])["owner_at"]
check("sending a message also marks the owner's time, newer than the earlier open", o2 and o3 and o2 > o3, (o2, o3))
lst = client.get("/teams", params={"brain": B}).json()["teams"]
best = max(lst, key=lambda t: t.get("owner_at") or 0)
check("GET /teams tells the page which team was worked in last", best["team_id"] == t2["team_id"], [(t["name"], t["owner_at"]) for t in lst])

src = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
check("the page opens the last worked team once per visit and tells the server when a team is opened",
      "lastWorkedTeam(S.teams)" in src and "S.autoOpened = true" in src and '"/opened"' in src)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_team_tags")
raise SystemExit(1 if fails else 0)
