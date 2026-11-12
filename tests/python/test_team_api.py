"""Nhóm chat team T1, nhiệm vụ 6: route `/teams/*` nối vào main.py (spec 2026-10-13-team-chat-design mục 15.1).

    python tests/run.py team_api

Không gọi model: engine của lượt nhóm được thay bằng engine giả; việc nền (lượt trả lời, điều phối) gom lại rồi chạy
trong test thay vì tạo task nền.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-api-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-api-brain-"))
BR2 = Path(tempfile.mkdtemp(prefix="javis-team-api-brain2-"))
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh"), ("hoa", "Hoa")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")
(BR2 / "agents").mkdir()

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


sent, spawned, inbox, calls = [], [], [], []


async def fake_publish(ev):
    sent.append(ev)


main._CHAT_RUNTIME.publish = fake_publish
api = main._TEAM_API
api.deps.spawn = spawned.append
api.deps.notify = lambda session_id, text: inbox.append((session_id, text))
script = {}


def fake_engine_for(team, agent_key, role):
    async def run(req):
        calls.append(req)
        q = script.get((agent_key, role)) or []
        return {"text": q.pop(0) if q else f"{agent_key} {role} xong", "tokens_in": 3, "tokens_out": 2}
    return "fake", "fake-model", run


api.deps.engine_for = fake_engine_for


def drain():
    """Chạy hết việc nền đã gom (lượt trả lời, điều phối), kể cả việc nền do việc nền sinh ra."""
    async def go():
        while spawned:
            job = spawned.pop(0)
            if asyncio.iscoroutine(job):
                await job
        await api.runner().wait_jobs()
    asyncio.run(go())


def dispatch():
    asyncio.run(api.runner().dispatch_once(wait=True))
    drain()


c = TestClient(main.app, base_url="http://127.0.0.1:8080")
Q = f"?brain={BR}"

r = c.post(f"/teams{Q}", json={"name": "Ra mắt", "description": "Nhóm ra mắt", "members": ["lan", "minh", "khong-co"],
                               "leader_slug": "lan"})
check("tạo nhóm với agent không có: 400, không tạo gì", r.status_code == 400 and not c.get(f"/teams{Q}").json()["teams"],
      r.text)
r = c.post(f"/teams{Q}", json={"name": "Ra mắt", "description": "Nhóm ra mắt", "members": ["lan", "minh"],
                               "leader_slug": "lan"})
check("tạo nhóm: 200", r.status_code == 200 and r.json()["ok"], r.text)
T = r.json()["team"]
TID = T["team_id"]
keys = {m["slug"]: m["agent_key"] for m in T["members"]}
check("thành viên có mã bền, trưởng nhóm đúng", set(keys) == {"lan", "minh"} and T["leader_key"] == keys["lan"])
ra = {a["slug"]: a for a in c.get(f"/resonance/agents{Q}").json()["agents"]}
check("vào nhóm cấp mã nhưng KHÔNG bật Cộng hưởng", ra["lan"]["registered"] and not ra["lan"]["enabled"]
      and ra["lan"]["agent_key"] == keys["lan"])
sess = main.get_store().get_session(T["session_id"])
check("phiên nhóm là kênh team:<id>, không hiện trong lịch sử chat", sess["channel"] == f"team:{TID}"
      and T["session_id"] not in {s["id"] for s in main.get_store().list_sessions(limit=100)})
lst = c.get(f"/teams{Q}").json()["teams"]
check("danh sách nhóm kèm số việc", [t["team_id"] for t in lst] == [TID] and lst[0]["counts"] == {
    "running": 0, "waiting": 0, "blocked": 0})
check("brain khác không thấy nhóm", c.get(f"/teams?brain={BR2}").json()["teams"] == []
      and c.get(f"/teams/{TID}?brain={BR2}").status_code == 404)

# Tin trò chuyện
r = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Chào nhóm"})
check("thiếu client_msg_id: 400", r.status_code == 400)
r = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Chào nhóm", "client_msg_id": "m1"})
check("gửi tin: 200, trưởng nhóm sẽ trả lời", r.status_code == 200 and r.json()["replies"] == [keys["lan"]], r.text)
n_spawn = len(spawned)
r2 = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Chào nhóm", "client_msg_id": "m1"})
check("gửi lại cùng client_msg_id: cùng tin, không thêm lượt", r2.json()["message_id"] == r.json()["message_id"]
      and r2.json()["created"] is False and len(spawned) == n_spawn)
drain()
page = c.get(f"/teams/{TID}/messages{Q}").json()
check("trang tin: tin chủ rồi câu trả lời của trưởng nhóm", [m["author_kind"] for m in page["messages"]] == [
    "owner", "agent"] and page["messages"][1]["author_ref"] == keys["lan"])
check("WS: có gói team_message", any(e.get("type") == "team_message" for e in sent))
r = c.post(f"/teams/{TID}/messages{Q}", json={"text": "x", "client_msg_id": "m2",
                                              "mentions": [keys["lan"], keys["minh"], "a", "b"]})
check("quá trần @: 400 nói rõ trần", r.status_code == 400 and "3" in r.json()["error"], r.text)

# Sổ quyết định vào khối nhóm
mid_owner = page["messages"][0]["id"]
r = c.post(f"/teams/{TID}/messages/{mid_owner}/decision{Q}", json={"on": True})
check("ghim quyết định: 200", r.status_code == 200, r.text)
calls.clear()
c.post(f"/teams/{TID}/messages{Q}", json={"text": "Tiếp nhé", "client_msg_id": "m3"})
drain()
check("khối nhóm có sổ quyết định", calls and "Sổ quyết định" in calls[-1]["prompt"]
      and "Chào nhóm" in calls[-1]["prompt"].split("Sổ quyết định", 1)[1])

# Giao việc, hàng đợi, Ưu tiên
ja = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Việc A", "client_msg_id": "j1", "as_job": True,
                                               "mentions": [keys["minh"]]}).json()["task_id"]
jb = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Việc B", "client_msg_id": "j2", "as_job": True}).json()["task_id"]
jc = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Việc C", "client_msg_id": "j3", "as_job": True}).json()["task_id"]
q = c.get(f"/teams/{TID}/queue{Q}").json()
check("hàng đợi đúng thứ tự thêm", [t["id"] for t in q["waiting"]] == [ja, jb, jc] and q["version"] > 0)
r = c.post(f"/teams/{TID}/queue/{jc}/priority{Q}", json={"on": True, "expected_queue_version": q["version"] - 1})
check("Ưu tiên với version cũ: 409 kèm hàng đợi mới", r.status_code == 409 and r.json()["queue"]["version"] == q["version"])
r = c.post(f"/teams/{TID}/queue/{jc}/priority{Q}", json={"on": True, "expected_queue_version": q["version"]})
check("Ưu tiên C: C lên đầu hàng chờ", r.status_code == 200 and [t["id"] for t in r.json()["queue"]["waiting"]] == [
    jc, ja, jb], r.text)
r = c.post(f"/teams/{TID}/tasks/{jb}/amend{Q}", json={"text": "thêm ảnh"})
check("sửa yêu cầu: revision 2", r.status_code == 200 and r.json()["revision"] == 2, r.text)
r = c.post(f"/teams/{TID}/tasks/{jb}/cancel{Q}")
check("huỷ việc chờ", r.status_code == 200 and main.tasks_feature.store.get_task(jb)["status"] == "cancelled")
dispatch()
dispatch()
check("điều phối: C rồi A chạy xong", main.tasks_feature.store.get_task(jc)["status"] == "done"
      and main.tasks_feature.store.get_task(ja)["status"] == "done")
d = c.get(f"/teams/{TID}/tasks/{ja}{Q}").json()
check("chi tiết việc: các bước và tin của việc", d["task"]["id"] == ja and [s["kind"] for s in d["steps"]] == ["work"]
      and any(m["task_id"] == ja for m in d["messages"]))
turns = c.get(f"/teams/{TID}/turns{Q}").json()["turns"]
check("sổ lượt có lượt của việc", any(t["task_id"] == ja and t["status"] == "ok" for t in turns))

# Đề xuất việc của trưởng nhóm, chủ bấm Tạo việc
script[(keys["lan"], "leader_reply")] = ['Nên làm bản tin. <!-- JAVIS_TEAM: {"op": "propose_job", "title": "Bản tin"} -->']
c.post(f"/teams/{TID}/messages{Q}", json={"text": "Tuần này?", "client_msg_id": "m4"})
drain()
card = c.get(f"/teams/{TID}/messages{Q}").json()["messages"][-1]
r = c.post(f"/teams/{TID}/messages/{card['id']}/accept{Q}")
check("Tạo việc từ đề xuất: một việc vào hàng", r.status_code == 200 and r.json()["task_id"]
      and c.post(f"/teams/{TID}/messages/{card['id']}/accept{Q}").json()["task_id"] == r.json()["task_id"])
c.post(f"/teams/{TID}/tasks/{r.json()['task_id']}/cancel{Q}")

# Thành viên, trưởng nhóm, trần, trạng thái
r = c.post(f"/teams/{TID}/members{Q}", json={"slug": "hoa"})
check("thêm thành viên", r.status_code == 200 and any(m["slug"] == "hoa" for m in r.json()["team"]["members"]), r.text)
keys["hoa"] = next(m["agent_key"] for m in r.json()["team"]["members"] if m["slug"] == "hoa")
r = c.post(f"/teams/{TID}/leader{Q}", json={"agent_key": None})
check("bỏ trưởng nhóm", r.status_code == 200 and r.json()["team"]["leader_key"] is None)
jn = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Việc chung", "client_msg_id": "j4", "as_job": True}).json()["task_id"]
dispatch()
check("không trưởng nhóm: việc chung bị chặn no_leader", main.tasks_feature.store.get_task(jn)["block_kind"] == "no_leader")
r = c.post(f"/teams/{TID}/leader{Q}", json={"agent_key": keys["hoa"]})
check("chọn trưởng nhóm mới: việc no_leader về hàng", r.status_code == 200
      and main.tasks_feature.store.get_task(jn)["status"] == "team_queued")
r = c.post(f"/teams/{TID}/leader{Q}", json={"agent_key": "ag_nguoi_la"})
check("trưởng nhóm phải là thành viên: 400", r.status_code == 400)
r = c.post(f"/teams/{TID}/caps{Q}", json={"caps": {"daily_turns": 50}})
check("đổi trần", r.status_code == 200 and r.json()["team"]["caps"]["daily_turns"] == 50)
check("trần sai: 400", c.post(f"/teams/{TID}/caps{Q}", json={"caps": {"bay": 1}}).status_code == 400)
r = c.patch(f"/teams/{TID}{Q}", json={"status": "paused"})
check("tạm dừng nhóm: không nhận việc mới", r.status_code == 200 and not asyncio.run(api.runner().dispatch_once()))
c.patch(f"/teams/{TID}{Q}", json={"status": "active"})
drain()
dispatch()
check("tiếp tục nhóm: việc chạy", main.tasks_feature.store.get_task(jn)["status"] == "done")
jw = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Việc chờ", "client_msg_id": "j5", "as_job": True}).json()["task_id"]
r = c.post(f"/teams/{TID}/tasks/{jw}/unblock{Q}", json={"action": "retry"})
check("gỡ chặn việc không bị chặn: 409", r.status_code == 409)

# T5: tin cuối ở danh sách nhóm, số lần đã dùng hôm nay, nút "Cho thêm lượt"
row = c.get(f"/teams{Q}").json()["teams"][0]
last = row.get("last") or {}
check("T5 danh sách nhóm kèm tin cuối (loại người gửi, tên, trích, giờ)", last.get("text") == "Việc chờ"
      and last.get("author_kind") == "owner" and last.get("ts", 0) > 0 and "author" in last, row.get("last"))
v = c.get(f"/teams/{TID}{Q}").json()["team"]
check("T5 chi tiết nhóm kèm số lần đã dùng hôm nay và giới hạn", v.get("usage", {}).get("cap") == 50
      and v["usage"]["today"] >= 1, v.get("usage"))
check("T5 Cho thêm lượt cho việc không bị chặn: 409", c.post(f"/teams/{TID}/tasks/{jw}/extend{Q}").status_code == 409)
c.post(f"/teams/{TID}/caps{Q}", json={"caps": {"daily_turns": v["usage"]["today"]}})
dispatch()
check("T5 hết lần trả lời hôm nay: việc chặn cap_reached",
      main.tasks_feature.store.get_task(jw)["block_kind"] == "cap_reached")
r = c.post(f"/teams/{TID}/tasks/{jw}/extend{Q}")
check("T5 Cho thêm lượt: 200, nâng trần ngày, việc về hàng", r.status_code == 200
      and r.json()["cap"] == "daily_turns" and r.json()["value"] == v["usage"]["today"] + 20
      and main.tasks_feature.store.get_task(jw)["status"] == "team_queued", r.text)
check("T5 Cho thêm lượt việc nhóm khác: 404", c.post(f"/teams/{TID}/tasks/t_khong_co/extend{Q}").status_code == 404)
c.post(f"/teams/{TID}/tasks/{jw}/cancel{Q}")
c.post(f"/teams/{TID}/caps{Q}", json={"caps": {"daily_turns": 50}})

# Ảnh đại diện đúng ảnh trợ lý đang dùng; ảnh nhóm ghép từ ảnh thành viên; ghim nhóm
v = c.get(f"/teams/{TID}{Q}").json()["team"]
check("thành viên kèm ảnh đại diện của trợ lý (hình, bảng màu)", all(
    isinstance(m.get("avatar"), dict) and m["avatar"].get("shape") and m["avatar"].get("palette") for m in v["members"]), v["members"])
row = c.get(f"/teams{Q}").json()["teams"][0]
check("dòng nhóm kèm tối đa 4 gương mặt (trưởng nhóm trước) và tổng số người",
      1 <= len(row.get("faces") or []) <= 4 and row["member_count"] == len([m for m in v["members"] if m["status"] == "active"])
      and row["faces"][0]["slug"] == next(m["slug"] for m in v["members"] if m["agent_key"] == v["leader_key"])
      and all(f.get("avatar", {}).get("shape") for f in row["faces"]), row.get("faces"))
r = c.post(f"/teams/{TID}/pin{Q}", json={"on": True})
check("ghim nhóm: 200, dòng nhóm có mốc ghim", r.status_code == 200
      and c.get(f"/teams{Q}").json()["teams"][0]["pinned_at"], r.text)
check("ghim nhóm của brain khác: 404", c.post(f"/teams/{TID}/pin?brain={BR2}", json={"on": True}).status_code == 404)
c.post(f"/teams/{TID}/pin{Q}", json={"on": False})
check("bỏ ghim", c.get(f"/teams{Q}").json()["teams"][0]["pinned_at"] is None)
r = c.delete(f"/teams/{TID}/members/{keys['minh']}{Q}")
check("bỏ thành viên", r.status_code == 200 and keys["minh"] not in {m["agent_key"] for m in r.json()["team"]["members"]})
c.post(f"/teams/{TID}/members{Q}", json={"slug": "minh"})

# Xoá agent rồi tạo lại cùng slug (TC5)
c.post("/agents/delete", data={"slug": "minh", "brain": str(BR)})
mem = c.get(f"/teams/{TID}{Q}").json()["team"]["members"]
check("xoá agent: không còn là thành viên", keys["minh"] not in {m["agent_key"] for m in mem})
import agent_avatar  # noqa: E402
old_ava = agent_avatar.for_agent({}, "minh")   # Minh cũ không chọn ảnh: ảnh mặc định suy từ slug
new_shape = next(s for s in agent_avatar.SHAPES if s != old_ava["shape"])
new_pal = next(p for p in ("ruby", "jade") if p != old_ava["palette"])
(BR / "agents" / "minh.md").write_text(f"---\nname: Minh mới\navatar:\n  shape: {new_shape}\n  palette: {new_pal}\n---\nx\n",
                                       encoding="utf-8", newline="\n")
r = c.post(f"/teams/{TID}/members{Q}", json={"slug": "minh"})
new_key = next(m["agent_key"] for m in r.json()["team"]["members"] if m["slug"] == "minh")
check("tạo lại cùng slug: mã mới, phải thêm lại mới là thành viên", new_key != keys["minh"])
# Review b93c46bd #2: tác giả tin cũ đã rời nhóm vẫn có tên và ảnh, tra theo agent_key độc lập với thành viên hiện tại
v = c.get(f"/teams/{TID}{Q}").json()["team"]
au = v.get("authors") or {}
check("#2 sổ tác giả gồm cả người đã rời (mã cũ của Minh), kèm slug, tên, ảnh",
      keys["minh"] in au and au[keys["minh"]]["slug"] == "minh" and au[keys["minh"]].get("name")
      and isinstance(au[keys["minh"]].get("avatar"), dict) and au[keys["minh"]]["avatar"].get("shape")
      and keys["minh"] not in {m["agent_key"] for m in v["members"]}, au.get(keys["minh"]))
check("#2 sổ tác giả gồm cả thành viên đang hoạt động", all(m["agent_key"] in au for m in v["members"]))
# Review 4f6268bd #1: hai trợ lý cùng slug ở hai thời điểm giữ nhân dạng RIÊNG theo agent_key
check("4f6268bd #1 mã cũ giữ đúng Minh cũ (tên, ảnh), không nhận của Minh mới",
      au[keys["minh"]]["name"] == "Minh" and au[keys["minh"]]["avatar"] == old_ava, au.get(keys["minh"]))
check("4f6268bd #1 mã mới là Minh mới (tên, ảnh mới)", au[new_key]["name"] == "Minh mới"
      and au[new_key]["avatar"]["shape"] == new_shape and au[new_key]["avatar"]["palette"] == new_pal, au.get(new_key))
check("4f6268bd #1 thành viên đang hoạt động là Minh mới", next(m for m in v["members"] if m["agent_key"] == new_key)["name"]
      == "Minh mới")
# Bản ghi cũ chưa có ảnh chụp nhân dạng (trước bản sửa): mã đã nghỉ không lấy tên/ảnh của người mới cùng slug
with api.teams()._Tx(api.teams()) as tx:
    tx.execute("UPDATE team_members SET identity_json=NULL WHERE team_id=? AND agent_key=?", (TID, keys["minh"]))
fb = c.get(f"/teams/{TID}{Q}").json()["team"]["authors"][keys["minh"]]
check("4f6268bd #1 chưa có ảnh chụp: dùng nhân dạng dự phòng của chính mã cũ (tên theo slug lúc vào, ảnh suy từ mã)",
      fb["name"] == "minh" and fb.get("avatar") is None and fb.get("avatar_seed") == keys["minh"], fb)

# Việc đang chạy nhưng không còn ai chạy (đã dừng ở điểm điều phối lúc tạm dừng) phải bị huỷ khi lưu trữ.
jr = c.post(f"/teams/{TID}/messages{Q}", json={"text": "Việc treo", "client_msg_id": "j6", "as_job": True,
                                               "mentions": [keys["lan"]]}).json()["task_id"]
c.patch(f"/teams/{TID}{Q}", json={"status": "paused"})
idle = main.tasks_feature.store.claim_team_next(TID, "w-cu")["id"]
r = c.patch(f"/teams/{TID}{Q}", json={"status": "archived"})
check("lưu trữ nhóm: huỷ mọi việc chờ", r.status_code == 200
      and {main.tasks_feature.store.get_task(x)["status"] for x in (jw, jr) if x != idle} == {"cancelled"})
check("lưu trữ nhóm: việc đang chạy mà không còn ai chạy cũng bị huỷ, không treo mãi",
      main.tasks_feature.store.get_task(idle)["status"] == "cancelled", main.tasks_feature.store.get_task(idle)["status"])
check("nhóm lưu trữ không nhận đề xuất thành việc", c.post(f"/teams/{TID}/messages/{card['id']}/accept{Q}").status_code
      == 409)
check("nhóm lưu trữ không gửi tin được", c.post(f"/teams/{TID}/messages{Q}", json={
    "text": "x", "client_msg_id": "m9"}).status_code == 409)
check("không có nhóm: 404", c.get(f"/teams/tm_khong{Q}").status_code == 404)
drain()

# T2: reaction qua route (spec 14, TC28 tới TC29)
page = c.get(f"/teams/{TID}/messages{Q}&limit=200").json()["messages"]
am = [m for m in page if m["author_kind"] == "agent"][0]
om = [m for m in page if m["author_kind"] == "owner"][0]
turns0 = len(c.get(f"/teams/{TID}/turns{Q}").json()["turns"])
r = c.post(f"/teams/{TID}/messages/{am['id']}/reaction{Q}", json={"value": "sad", "reasons": ["too_long"],
                                                                     "comment": "Gọn hơn", "nonce": "rx1"})
check("route reaction: 200, trả trạng thái", r.status_code == 200 and r.json()["reaction"]["value"] == "sad"
      and r.json()["reaction"]["reasons"] == ["too_long"], r.text)
page = c.get(f"/teams/{TID}/messages{Q}&limit=200").json()["messages"]
check("trang tin kèm reaction của từng tin", [m.get("reaction") and m["reaction"]["value"] for m in page
                                             if m["id"] == am["id"]] == ["sad"]
      and all(m.get("reaction") is None for m in page if m["id"] != am["id"]))
check("route reaction: giá trị lạ 400", c.post(f"/teams/{TID}/messages/{am['id']}/reaction{Q}", json={
    "value": "thumbs", "nonce": "rx2"}).status_code == 400)
check("route reaction: tin của chủ 400", c.post(f"/teams/{TID}/messages/{om['id']}/reaction{Q}", json={
    "value": "like", "nonce": "rx3"}).status_code == 400)
check("route reaction: brain khác 404", c.post(f"/teams/{TID}/messages/{am['id']}/reaction?brain={BR2}", json={
    "value": "like", "nonce": "rx4"}).status_code == 404)
# Review T2 #1: khung lọc theo việc (chi tiết việc) cũng phải kèm phản hồi, kẻo bấm emoji ở đó xoá lý do và góp ý.
tm_ = [m for m in page if m["author_kind"] == "agent" and m.get("task_id")][0]
c.post(f"/teams/{TID}/messages/{tm_['id']}/reaction{Q}", json={"value": "wow", "reasons": ["missing"],
                                                                  "comment": "Thêm số liệu", "nonce": "rx-task"})
det = c.get(f"/teams/{TID}/tasks/{tm_['task_id']}{Q}").json()["messages"]
check("chi tiết việc kèm phản hồi của từng tin (khung lọc theo việc không mất lý do, góp ý)",
      [(m.get("reaction") or {}).get("comment") for m in det if m["id"] == tm_["id"]] == ["Thêm số liệu"], det[:2])
r = c.post(f"/teams/{TID}/messages/{am['id']}/reaction{Q}", json={"value": "like", "nonce": "rx-task"})
check("nonce đã dùng cho tin khác: 409 (hợp đồng T2), không báo đã lưu", r.status_code == 409, r.text)
kinds = [getattr(getattr(x, "cr_code", None), "co_name", "") for x in spawned]
check("route reaction: không mở lượt nào, chỉ đẩy gói WS", len(c.get(f"/teams/{TID}/turns{Q}").json()["turns"])
      == turns0 and not ({"run_replies", "dispatch_once"} & set(kinds)) and "fake_publish" in kinds, kinds)
drain()

# T3: Toàn quyền qua route của chủ, thao tác host thật (_TeamAdmin) cho lệnh quản trị.
r = c.post(f"/teams{Q}", json={"name": "Tự vận hành", "members": ["lan", "minh"], "leader_slug": "lan"})
T3 = r.json()["team"]
T3ID = T3["team_id"]
k3 = {m["slug"]: m["agent_key"] for m in T3["members"]}
check("T3 nhóm mới ở Quyền giới hạn, view có authority và trần hiệu lực", T3["authority"]["authority"] is None
      # 2026-11-12: a team made through the route has no per-job cap (replies, steps); the daily cap stays.
      and T3["authority"]["effective_caps"]["task_turns"] is None and T3["authority"]["effective_caps"]["task_steps"] is None
      and T3["authority"]["effective_caps"]["daily_turns"] == 100 and "provider_quota" in T3["authority"]["fixed_limits"])
grant = {"caps": {"task_turns": {"unlimited": True}}, "ceilings": {"task_turns": {"unlimited": True}, "daily_turns": 150},
         "providers_unlimited": ["aux"], "can_interrupt": False}
r = c.post(f"/teams/{T3ID}/authority{Q}", json={"mode": "full", "grant": grant})
v = r.json().get("team", {}).get("authority", {})
check("T3 chủ bật Toàn quyền qua route: 200, Không giới hạn là null", r.status_code == 200
      and v["authority"]["leader_key"] == k3["lan"] and v["effective_caps"]["task_turns"] is None, r.text)
check("T3 hộp cấp quyền sai khuôn: 400", c.post(f"/teams/{T3ID}/authority{Q}", json={
    "mode": "full", "grant": {"caps": {"task_turns": 99}, "ceilings": {"task_turns": 20}}}).status_code == 400)
check("T3 chế độ lạ: 400", c.post(f"/teams/{T3ID}/authority{Q}", json={"mode": "god"}).status_code == 400)
r = c.post(f"/teams/{T3ID}/members/{k3['minh']}/managed{Q}", json={"on": True})
check("T3 chủ giao agent cho nhóm quản lý", r.status_code == 200
      and [m["managed"] for m in r.json()["team"]["members"] if m["slug"] == "minh"] == [True], r.text)
check("T3 agent đã do nhóm khác quản lý: 409", c.post(f"/teams/{TID}/members/{k3['minh']}/managed{Q}",
                                                       json={"on": True}).status_code in (404, 409))
adm = main._TeamAdmin()
before = (BR / "agents" / "lan.md").read_bytes()
s1 = adm.create_agent(str(BR), "Lan", "Người viết", "Bạn viết.")
check("T3 host tạo agent mới không ghi đè agent cùng tên, có tag", s1 == "lan-2" and (BR / "agents" / "lan.md").read_bytes()
      == before and "Nhóm" in (BR / "agents" / "lan-2.md").read_text(encoding="utf-8"), s1)
adm.edit_prompt(str(BR), "lan-2", "Lời nhắc mới")
check("T3 host sửa lời nhắc, giữ frontmatter", (BR / "agents" / "lan-2.md").read_text(encoding="utf-8").rstrip()
      .endswith("Lời nhắc mới") and "name: Lan" in (BR / "agents" / "lan-2.md").read_text(encoding="utf-8"))
(BR / "agents" / "hong.md").write_text("Chỉ có thân, không frontmatter", encoding="utf-8", newline="\n")
try:
    adm.edit_prompt(str(BR), "hong", "Lời nhắc mới")
    refused = False
except ValueError:
    refused = True
check("T3 review #5: file không có frontmatter thì không sửa (không xoá tên, vai, model)", refused
      and (BR / "agents" / "hong.md").read_text(encoding="utf-8") == "Chỉ có thân, không frontmatter")
(BR / "agents" / "hong.md").unlink()
adm.set_resonance(str(BR), "lan-2", True, "leader:test")
ra = {a["slug"]: a for a in c.get(f"/resonance/agents{Q}").json()["agents"]}
check("T3 host bật Cộng hưởng cho agent do nhóm quản lý (ghi by=leader)", ra["lan-2"]["enabled"])
r = c.post(f"/teams/{T3ID}/authority{Q}", json={"mode": "limited"})
check("T3 chủ thu hồi: về Quyền giới hạn", r.status_code == 200 and r.json()["team"]["authority"]["authority"] is None
      and r.json()["team"]["authority"]["effective_caps"]["task_turns"] is None)

# T4: tìm trong nhóm qua route
main.get_store().append_team_message(T3["session_id"], "user", "Kế hoạch RA MẮT tháng Mười", author_kind="owner",
                                     client_msg_id="t4s1")
r = c.get(f"/teams/{T3ID}/search{Q}&q=ra%20mat%20thang")
check("T4 route tìm: 200, khớp không dấu, có id và đoạn trích", r.status_code == 200 and len(r.json()["results"]) == 1
      and r.json()["results"][0]["snippet"].startswith("Kế hoạch") and r.json()["results"][0]["id"], r.text)
check("T4 route tìm: không lẫn nhóm khác", c.get(f"/teams/{TID}/search{Q}&q=ra%20mat%20thang").json()["results"] == [])
check("T4 route tìm: câu quá ngắn 400, brain khác 404", c.get(f"/teams/{T3ID}/search{Q}&q=a").status_code == 400
      and c.get(f"/teams/{T3ID}/search?brain={BR2}&q=ra%20mat").status_code == 404)

# Vòng nền: cài mới (chưa có team.sqlite3 lúc khởi động) thì KHÔNG chạy phục hồi về sau, kẻo chặn nhầm việc đang chạy.
import dataclasses  # noqa: E402
import team_api  # noqa: E402
fresh_path = Path(tempfile.mkdtemp(prefix="team-fresh-")) / "team.sqlite3"
api2 = team_api.TeamApi(dataclasses.replace(api.deps, store_path=fresh_path, spawn=spawned.append))
api2.prime()
tm2 = api2.teams()
t2 = tm2.create_team(str(BR), "Mới", "", main.get_store().create_session(brain=str(BR), channel="team:tm_x"))
tu = tm2.reserve_turn(t2["team_id"], None, None, "ag_x", "leader_reply")
asyncio.run(api2.tick())
check("cài mới: lượt đang giữ chỗ không bị phục hồi nhầm (không hoàn lượt)", tm2.turn(tu)["status"] == "reserved")
api3 = team_api.TeamApi(dataclasses.replace(api.deps, store_path=fresh_path, spawn=spawned.append))
api3.prime()
asyncio.run(api3.tick())
check("khởi động lại khi đã có kho: phục hồi chạy một lần", tm2.turn(tu)["status"] == "refunded")
spawned.clear()
raise SystemExit(1 if fails else 0)
