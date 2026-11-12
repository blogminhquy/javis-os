"""Nhóm chat team, GOAL T1 qua đường host thật (main.py, route `/teams/*`, `/agents`, `/resonance/agents/*`).

    python tests/run.py team_t1_goal_host -v

Engine của lượt nhóm là engine GIẢ (thay `deps.engine_for`); thêm chốt: dựng engine thật (`team_engine.build`) thì test
dừng ngay, nên lần đổi API sau không âm thầm gọi model thật. Các ca:
- H5 bảng giới hạn có trong khung nhìn nhóm; chủ đặt Không giới hạn qua route; trần máy chủ không đặt được.
- H6 lệnh `set_resonance` của trưởng nhóm Toàn quyền: bật thì đánh thức mục tiêu như route bật của chủ (`wake_agent_goals`),
  nhật ký by=leader; trợ lý chủ đã tắt mà nhóm không quản lý thì không bật lại được.
- H7 (GOAL 12.1) đổi tag của trợ lý (thay cả tập, thêm, đổi tên, xoá tag) không đổi tư cách thành viên, trưởng nhóm, quyền.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-goal-host-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-goal-host-brain-"))
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh"), ("hoa", "Hoa")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class RealEngineUsed(AssertionError):
    pass


def _no_real_engine(*a, **k):
    raise RealEngineUsed("test tried to build a REAL team engine; the fake engine must be used")


main.team_engine.build = _no_real_engine   # chốt: không có đường nào tới model thật

sent, spawned, calls = [], [], []


async def fake_publish(ev):
    sent.append(ev)


main._CHAT_RUNTIME.publish = fake_publish
api = main._TEAM_API
api.deps.spawn = spawned.append
api.deps.notify = lambda session_id, text: None
script = {}


def fake_engine_for(team, agent_key, role):
    async def run(req):
        calls.append(req)
        q = script.get((agent_key, role)) or []
        return {"text": q.pop(0) if q else f"{agent_key} {role} xong", "tokens_in": 1, "tokens_out": 1}
    return "fake", "fake-model", run


api.deps.engine_for = fake_engine_for


def drain():
    async def go():
        while spawned:
            job = spawned.pop(0)
            if asyncio.iscoroutine(job):
                await job
        await api.runner().wait_jobs()
    asyncio.run(go())


def directive(**op):
    import json
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


c = TestClient(main.app, base_url="http://127.0.0.1:8080")
Q = f"?brain={BR}"
r = c.post(f"/teams{Q}", json={"name": "Vận hành", "members": ["lan", "minh", "hoa"], "leader_slug": "lan"})
T = r.json()["team"]
TID = T["team_id"]
K = {m["slug"]: m["agent_key"] for m in T["members"]}
check("tạo nhóm qua route", r.status_code == 200 and T["leader_key"] == K["lan"], r.text)

# ═════ H5: bảng giới hạn, Không giới hạn của chủ qua route ═════
lim = T["authority"].get("limits") or []
check("H5 khung nhìn nhóm có bảng giới hạn đủ bốn nhóm", {x["category"] for x in lim} == {"owner", "leader", "server", "provider"},
      lim)
r = c.post(f"/teams/{TID}/caps{Q}", json={"caps": {"daily_turns": {"unlimited": True}}})
check("H5 chủ đặt Không giới hạn số lần mỗi ngày qua route: lưu null", r.status_code == 200
      and r.json()["team"]["caps"]["daily_turns"] is None and r.json()["team"]["usage"]["cap"] is None, r.text)
r = c.post(f"/teams/{TID}/caps{Q}", json={"caps": {"running_jobs": 2}})
check("H5 trần máy chủ (việc chạy cùng lúc mỗi nhóm) không đặt được qua route", r.status_code in (400, 409)
      and c.get(f"/teams/{TID}{Q}").json()["team"]["caps"]["running_jobs"] == 3, r.text)
c.post(f"/teams/{TID}/caps{Q}", json={"caps": {"daily_turns": 100}})

# ═════ H6: set_resonance của trưởng nhóm đánh thức mục tiêu; luật quản lý ═════
check("H6 chủ giao Minh cho nhóm quản lý", c.post(f"/teams/{TID}/members/{K['minh']}/managed{Q}", json={"on": True})
      .status_code == 200)
grant = {"caps": {}, "ceilings": {"task_turns": 24, "task_steps": 12, "help_depth": 3, "daily_turns": 200},
         "can_interrupt": False, "providers_unlimited": [], "billing": "subscription"}
r = c.post(f"/teams/{TID}/authority{Q}", json={"mode": "full", "grant": grant})
AUTH_ID = r.json()["team"]["authority"]["authority"]["id"]
check("H6 chủ bật Toàn quyền", r.status_code == 200, r.text)
for slug in ("minh", "hoa"):
    c.post(f"/resonance/agents/toggle{Q}", json={"slug": slug, "enabled": True})
    c.post(f"/resonance/agents/toggle{Q}", json={"slug": slug, "enabled": False})
rs = main._resonance_store()
woke = []
_orig_wake = rs.wake_agent_goals


def _rec_wake(brain_id, agent_key, *a, **k):
    woke.append(agent_key)
    return _orig_wake(brain_id, agent_key, *a, **k)


rs.wake_agent_goals = _rec_wake


def agents():
    return {a["slug"]: a for a in c.get(f"/resonance/agents{Q}").json()["agents"]}


check("H6 chủ đã tắt Auto của Minh và Hoa", not agents()["minh"]["enabled"] and not agents()["hoa"]["enabled"])
script[(K["lan"], "leader_reply")] = ["Bật Auto cho Hoa." + directive(op="set_resonance", agent="hoa", on=True)]
c.post(f"/teams/{TID}/messages{Q}", json={"text": "Bật Auto cho Hoa", "client_msg_id": "h1"})
drain()
check("H6 Hoa chỉ tham gia (nhóm không quản lý): trưởng nhóm Toàn quyền không bật lại được, không đánh thức gì",
      not agents()["hoa"]["enabled"] and K["hoa"] not in woke, (agents()["hoa"], woke))
script[(K["lan"], "leader_reply")] = ["Bật Auto cho Minh." + directive(op="set_resonance", agent="minh", on=True)]
c.post(f"/teams/{TID}/messages{Q}", json={"text": "Bật Auto cho Minh", "client_msg_id": "h2"})
drain()
ev = rs.agent_events(main._brain_key(str(BR)), K["minh"])
check("H6 Minh do nhóm quản lý, Toàn quyền: bật được và mục tiêu được đánh thức NGAY (như route của chủ)",
      agents()["minh"]["enabled"] and woke == [K["minh"]], (agents()["minh"], woke))
# Kho Cộng hưởng ghi người làm dạng "<vai>:<by>" (Principal của host thay chủ), nên đuôi là leader:<mã>.
check("H6 nhật ký: sự kiện bật của Cộng hưởng ghi by=leader:<mã trưởng nhóm>",
      ev and ev[-1]["kind"] == "enabled" and ev[-1]["by"].endswith(f"leader:{K['lan']}"), ev[-2:])
check("H6 engine giả đã được dùng, không có lượt nào tới engine thật", len(calls) >= 2
      and all(t["engine"] == "fake" for t in api.teams().turns(TID)), [t["engine"] for t in api.teams().turns(TID)])

# ═════ H7: đổi tag không đổi tư cách thành viên, trưởng nhóm hay quyền (GOAL 4.1, 12.1) ═════


def snapshot():
    t = c.get(f"/teams/{TID}{Q}").json()["team"]
    auth = t["authority"]["authority"] or {}
    return {"members": sorted((m["agent_key"], m["role"], m["status"], m["managed"]) for m in t["members"]),
            "leader": t["leader_key"], "mode": t["leader_mode"], "auth": (auth.get("id"), auth.get("leader_key")),
            "teams": sorted(x["team_id"] for x in c.get(f"/teams{Q}").json()["teams"]),
            "keys": {s: agents()[s]["agent_key"] for s in ("lan", "minh", "hoa")}}


before = snapshot()
r1 = c.post("/capability/meta", data={"kind": "agent", "slug": "minh", "brain": str(BR), "add_tags": '["Marketing"]'})
r2 = c.post("/agents", data={"slug": "lan", "name": "Lan", "role": "Thành viên", "prompt": "Bạn là Lan.", "brain": str(BR),
                             "tags": '["Bán hàng", "Vận hành"]'})
r3 = c.post("/agents/tags/rename", data={"brain": str(BR), "from_tag": "Marketing", "to_tag": "Tiếp thị"})
r4 = c.post("/agents/tags/delete", data={"brain": str(BR), "tag": "Vận hành"})
check("H7 bốn thao tác tag thành công", all(x.status_code == 200 for x in (r1, r2, r3, r4)),
      [x.status_code for x in (r1, r2, r3, r4)])
tags_now = {s: (main._read_md(BR / "agents" / f"{s}.md")[0] or {}).get("tags") for s in ("lan", "minh")}
check("H7 tag đã đổi thật trên file trợ lý", tags_now["lan"] == ["Bán hàng"] and tags_now["minh"] == ["Tiếp thị"], tags_now)
after = snapshot()
check("H7 đổi tag: thành viên, vai, trạng thái, nhóm quản lý không đổi", after["members"] == before["members"],
      (before["members"], after["members"]))
check("H7 đổi tag: trưởng nhóm, chế độ quyền và dòng Toàn quyền không đổi",
      (after["leader"], after["mode"], after["auth"]) == (before["leader"], before["mode"], before["auth"])
      and after["auth"][0] == AUTH_ID, (before, after))
check("H7 đổi tag: không tạo hay ghép nhóm nào, mã bền của trợ lý giữ nguyên",
      after["teams"] == before["teams"] and after["keys"] == before["keys"], (before, after))

# ═════ H8 (review T1 #5): bật Auto được ghi mà đánh thức lỗi, qua host thật ═════
c.post(f"/resonance/agents/toggle{Q}", json={"slug": "minh", "enabled": False})


def _boom_wake(brain_id, agent_key, *a, **k):
    raise RuntimeError("database is locked")


rs.wake_agent_goals = _boom_wake
script[(K["lan"], "leader_reply")] = ["Bật lại Auto cho Minh." + directive(op="set_resonance", agent="minh", on=True)]
c.post(f"/teams/{TID}/messages{Q}", json={"text": "Bật lại Auto cho Minh", "client_msg_id": "h8"})
drain()
rs.wake_agent_goals = _rec_wake
evs = api.teams().events(TID)
last_lan = [m for m in c.get(f"/teams/{TID}/messages{Q}").json()["messages"]
            if m["author_kind"] == "agent" and m["author_ref"] == K["lan"]][-1]
check("H8 đánh thức lỗi: Auto của Minh VẪN bật (trạng thái thật, không cuộn lại)", agents()["minh"]["enabled"],
      agents()["minh"])
check("H8 nhật ký nhóm có agent_set_resonance và agent_wake_failed kèm nguyên nhân",
      [e["kind"] for e in evs].count("agent_wake_failed") == 1 and "agent_set_resonance" in [e["kind"] for e in evs]
      and "locked" in next(e for e in evs if e["kind"] == "agent_wake_failed")["after"]["error"],
      [(e["kind"], e.get("after")) for e in evs[:4]])
check("H8 ghi chú trên tin nói Auto đã bật, không báo lệnh thất bại",
      any("Auto đã bật" in n for n in last_lan["meta"]["notes"])
      and not any("Không áp được lệnh" in n or "lỗi" == n for n in last_lan["meta"]["notes"]), last_lan["meta"]["notes"])

# ═════ H9 (review T1 #7): NaN và vô cực qua route caps trả 4xx, không lưu, JSON trả về hợp lệ ═════
caps0 = c.get(f"/teams/{TID}{Q}").json()["team"]["caps"]
for raw in ('{"caps": {"busy_wait_s": NaN}}', '{"caps": {"task_turns": Infinity}}', '{"caps": {"daily_turns": -Infinity}}',
            '{"caps": {"mentions": 1e400}}', '{"caps": ["task_turns"]}'):
    r = c.post(f"/teams/{TID}/caps{Q}", content=raw, headers={"content-type": "application/json"})
    try:
        body_ok = r.json().get("ok") is False
    except ValueError:
        body_ok = False
    check(f"H9 caps {raw}: trả 4xx kèm JSON lỗi hợp lệ", 400 <= r.status_code < 500 and body_ok, (r.status_code, r.text))
caps1 = c.get(f"/teams/{TID}{Q}").json()["team"]["caps"]
check("H9 không giá trị hỏng nào được lưu", caps1 == caps0, (caps0, caps1))

print(f"\n{len(fails)} FAIL" if fails else "\nALL OK")
raise SystemExit(1 if fails else 0)
