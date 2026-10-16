"""0.142.0: tab Công việc của trợ lý ở trang Cộng sự.

    python tests/run.py agent_jobs_0142

Gom việc theo agent_key, đọc thẳng bản ghi gốc (không sao chép): việc nhóm (giao thẳng, điều phối, bước con, hỗ trợ),
việc Kanban từ chat riêng và từ nút Giao việc, mục tiêu Auto. Đi qua route thật của main với kho SQLite thật, không gọi
model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import time
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agent-jobs-")
BR = Path(tempfile.mkdtemp(prefix="javis-agent-jobs-brain-")).resolve()
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh"), ("hoa", "Hoa")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n",
                                              encoding="utf-8", newline="\n")

import main  # noqa: E402
import agent_jobs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


api = main._TEAM_API
api.deps.spawn = lambda coro: coro.close()
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
B = str(BR)


def jobs(slug):
    r = client.get(f"/agents/{slug}/jobs", params={"brain": B})
    return r.status_code, r.json()


# Chưa có gì: không lỗi, không tạo gì.
code, j = jobs("lan")
check("trợ lý chưa có việc: danh sách rỗng, đủ bốn ngăn", code == 200 and j["jobs"] == []
      and set(j["counts"]) == {"running", "waiting", "needs_you", "done"}, j)
check("chỉ đọc không cấp mã, không tạo kho nhóm", j["agent_key"] is None and not api.exists(), j)
check("trợ lý không có: 404", client.get("/agents/khong-co/jobs", params={"brain": B}).status_code == 404)

# Nhóm: Lan trưởng nhóm (điều phối), Minh được giao thẳng, Hoa chỉ hỗ trợ một bước.
r = client.post("/teams", params={"brain": B}, json={"name": "Ra mắt", "members": ["lan", "minh", "hoa"],
                                                      "leader_slug": "lan"})
team = r.json()["team"]
tid = team["team_id"]
keys = {m["slug"]: m["agent_key"] for m in team["members"]}
r = client.post(f"/teams/{tid}/messages", params={"brain": B},
                json={"text": "Viết thông cáo", "mentions": [keys["minh"]], "as_job": True, "client_msg_id": "j1"})
task_id = r.json()["task_id"]
r2 = client.post(f"/teams/{tid}/messages", params={"brain": B},
                 json={"text": "Việc chung", "as_job": True, "client_msg_id": "j2"})
task2 = r2.json()["task_id"]
teams = api.teams()
t = main.tasks_feature.store.get_task(task_id)
# Thêm bước qua bộ chạy (đúng đường của việc thật): Minh làm, Hoa hỗ trợ.
api.runner()._put_steps(teams.get(tid), t, [{"kind": "work", "agent": keys["minh"], "brief": "viết"},
                                            {"kind": "help", "agent": keys["hoa"], "brief": "soát số liệu"}])

code, j = jobs("minh")
mine = [x for x in j["jobs"] if x["source"] == "team"]
check("Minh thấy việc giao thẳng, nguồn là nhóm, mở đúng nhóm và việc",
      len(mine) == 1 and mine[0]["roles"] == ["worker"] and mine[0]["source_label"] == "Ra mắt"
      and mine[0]["open"] == {"kind": "team", "team_id": tid, "task_id": task_id}, j)
check("việc đang chờ: ngăn Đang chờ, vị trí thật trong hàng của nhóm, có Huỷ",
      mine[0]["bucket"] == "waiting" and mine[0]["queue_pos"] == 1 and mine[0]["cancel"]["task_id"] == task_id, mine)
check("tiến độ là số bước thật", mine[0]["progress"] == {"done": 0, "total": 2}, mine)
code, j = jobs("hoa")
hoa = [x for x in j["jobs"] if x["source"] == "team"]
check("người chỉ hỗ trợ một bước cũng thấy việc liên quan, vai Hỗ trợ",
      [x["id"] for x in hoa] == [f"team:{task_id}"] and hoa[0]["roles"] == ["helper"], j)
code, j = jobs("lan")
lan = {x["id"]: x for x in j["jobs"] if x["source"] == "team"}
check("trưởng nhóm thấy cả hai việc với vai Điều phối", set(lan) == {f"team:{task_id}", f"team:{task2}"}
      and all("coordinator" in x["roles"] for x in lan.values()), j)
check("cùng bản ghi gốc: không sinh việc Kanban mới khi đọc",
      [x for x in main.tasks_feature.store.list_tasks(str(BR)) if x.get("lane") != "team"] == [])

# Huỷ một việc không ảnh hưởng việc khác.
client.post(f"/teams/{tid}/tasks/{task2}/cancel", params={"brain": B})
code, j = jobs("lan")
lan = {x["id"]: x for x in j["jobs"]}
check("huỷ một việc: việc đó sang Đã xong (huỷ), việc kia giữ nguyên",
      lan[f"team:{task2}"]["bucket"] == "done" and lan[f"team:{task2}"]["cancelled"]
      and lan[f"team:{task_id}"]["bucket"] == "waiting", lan)

# Giao việc: một việc Kanban gắn mã trợ lý, báo về chat riêng, chống gửi trùng.
main.tasks_feature.store.set_orchestration(str(BR), "off")
r = client.post("/agents/minh/jobs", params={"brain": B}, json={"text": "Soạn email cảm ơn khách", "nonce": "n1"})
a1 = r.json()
r = client.post("/agents/minh/jobs", params={"brain": B}, json={"text": "Soạn email cảm ơn khách", "nonce": "n1"})
check("Giao việc: bấm hai lần cùng nonce chỉ một việc", a1["ok"] and r.json()["task_id"] == a1["task_id"], (a1, r.json()))
r = client.post("/agents/lan/jobs", params={"brain": B}, json={"text": "Soạn email cảm ơn khách", "nonce": "n2"})
check("cùng nội dung giao cho trợ lý khác là việc khác (không gộp theo tiêu đề)", r.json()["task_id"] != a1["task_id"])
kt = main.tasks_feature.store.get_task(a1["task_id"])
sess = main.get_store().get_session(a1["session_id"])
check("việc Kanban báo về đúng cuộc chat riêng với trợ lý", kt["chat_id"] == f"web:{a1['session_id']}"
      and sess["channel"] == "agent:minh" and "Minh" in kt["title"], (kt, sess))
code, j = jobs("minh")
kj = [x for x in j["jobs"] if x["source"] == "chat"]
check("việc giao hiện ở tab, nguồn chat riêng, mở đúng cuộc chat",
      len(kj) == 1 and kj[0]["open"] == {"kind": "chat", "session_id": a1["session_id"]}, j)
check("hàng chờ trung thực: AI tự vận hành tắt thì ghi rõ", kj[0]["bucket"] == "waiting" and kj[0]["board_off"]
      and j["board"] == "off", kj)
code, j2 = jobs("lan")
check("việc của trợ lý khác không lẫn sang", all(x["id"] != f"kanban:{a1['task_id']}" for x in j2["jobs"]))
check("thiếu nội dung: 400", client.post("/agents/minh/jobs", params={"brain": B},
                                          json={"text": " ", "nonce": "n3"}).status_code == 400)

# Việc xếp từ chat riêng (javis_task với chat_id web:<phiên>) cũng thuộc trợ lý đó.
t2 = main.tasks_feature.enqueue(B, "Tra giá đối thủ", "Tra giá", chat_id=f"web:{a1['session_id']}")
code, j = jobs("minh")
check("việc xếp từ chat riêng thuộc trợ lý của phiên", any(x["id"] == f"kanban:{t2}" for x in j["jobs"]), j)
# Huỷ một việc Kanban không đụng việc khác.
main.tasks_feature.store.move(t2, "cancelled", "test")
code, j = jobs("minh")
by = {x["id"]: x for x in j["jobs"]}
check("huỷ việc Kanban: chỉ việc đó Đã xong", by[f"kanban:{t2}"]["bucket"] == "done"
      and by[f"kanban:{a1['task_id']}"]["bucket"] == "waiting", by)

# Persona: việc giao cho trợ lý chạy với vai của trợ lý đó, engine và quyền của Kanban giữ nguyên.
p = main.tasks_feature._persona(kt, str(BR))
check("việc giao mang vai của trợ lý", "Minh" in p and "Bạn là Minh" in p, p[:300])
check("việc Kanban thường không mang vai", main.tasks_feature._persona(main.tasks_feature.store.get_task(t2), str(BR)) == "")
check("khoá giao việc đọc ngược được", agent_jobs.parse_assign_key(kt["idempotency_key"]) == (j["agent_key"], "minh"))

# Ngăn và thứ tự: Cần bạn trước, rồi Đang làm, Đang chờ, Đã xong.
order = [x["bucket"] for x in j["jobs"]]
rank = {"needs_you": 0, "running": 1, "waiting": 2, "done": 3}
check("thứ tự ngăn đúng", order == sorted(order, key=lambda b: rank[b]), order)
check("không nguồn nào lỗi ngầm", j["errors"] == [], j["errors"])
check("đếm theo ngăn khớp danh sách", all(j["counts"][b] == order.count(b) for b in rank), j["counts"])

# review #8: nonce chỉ toàn ký tự lạ thì từ chối, không dùng chung một khoá.
r = client.post("/agents/minh/jobs", params={"brain": B}, json={"text": "Việc lạ", "nonce": "!!! ###"})
check("review #8: nonce rỗng sau khi lọc: 400", r.status_code == 400, r.text)
# review #7: phiên chat cũ đã ghim mã của trợ lý trước (cùng slug) không nhận việc của trợ lý hiện tại.
old_sid = main.get_store().create_session(brain=B, channel="agent:hoa", title="Hoa cũ")
with main._resonance_store()._conn() as c:
    c.execute("INSERT INTO session_agents(session_id,brain_id,agent_key,by,created_at) VALUES(?,?,?,?,?)",
              (old_sid, str(BR), "ag_tro_ly_cu", "test", 0))
r = client.post("/agents/hoa/jobs", params={"brain": B}, json={"text": "Gửi báo giá", "nonce": "h1"})
check("review #7: Giao việc không báo vào phiên của trợ lý cũ cùng slug, mở phiên mới",
      r.json()["ok"] and r.json()["session_id"] != old_sid, r.json())

# ───────────── bước kế tiếp, vai, ưu tiên (bổ sung sau review đầy đủ 0.142.0) ─────────────
ROOT_B = str(BR)
store = main.tasks_feature.store
code, j = jobs("minh")
tj = next(x for x in j["jobs"] if x["id"] == f"team:{task_id}")
check("bước kế của việc nhóm đang chờ: vị trí thật trong hàng của nhóm",
      tj["next"] == {"code": "queue", "n": 1, "team": "Ra mắt"}, tj)
kj = next(x for x in j["jobs"] if x["id"] == f"kanban:{a1['task_id']}")
check("bước kế của việc giao khi AI tự vận hành tắt: bật ở trang Việc", kj["next"] == {"code": "board_off"}, kj)
check("vai chỉ còn bốn loại", all(r in agent_jobs.ROLES for x in j["jobs"] for r in x["roles"]), j["jobs"])
check("việc nhóm đang chờ có Ưu tiên theo route của nhóm (CAS phiên bản hàng)",
      tj["priority"]["kind"] == "team" and tj["priority"]["on"] is True and isinstance(tj["priority"]["version"], int), tj)
r = client.post(f"/teams/{tid}/queue/{task_id}/priority", params={"brain": B},
                json={"on": True, "expected_queue_version": tj["priority"]["version"]})
code, j = jobs("minh")
tj = next(x for x in j["jobs"] if x["id"] == f"team:{task_id}")
check("ưu tiên qua route gốc của nhóm: thẻ thấy đã ưu tiên", r.json().get("ok") and tj["priority"]["on"] is False, r.text)

# Trợ lý đang bận ở nhóm khác: việc chờ nói rõ đang chờ trợ lý xong việc ở nhóm kia.
r = client.post("/teams", params={"brain": B}, json={"name": "Hậu cần", "members": ["minh", "lan"],
                                                      "leader_slug": "lan"})
tid2 = r.json()["team"]["team_id"]
teams.acquire_busy(keys["minh"], tid2, "turn-x")
code, j = jobs("minh")
tj = next(x for x in j["jobs"] if x["id"] == f"team:{task_id}")
check("bận ở nhóm khác: bước kế là chờ xong việc ở nhóm đó", tj["next"] == {"code": "busy", "team": "Hậu cần"}, tj)
teams.release_busy(keys["minh"], "turn-x")

# ───────────── Giao việc vào một nhóm (máy của nhóm, không tạo đường mới) ─────────────
code, j = jobs("minh")
check("tab trả nhóm đang hoạt động mà trợ lý là thành viên (nơi nhận kết quả)",
      {t["team_id"] for t in j["teams"]} == {tid, tid2}, j["teams"])
body = {"text": "Tổng hợp phản hồi khách", "criteria": "Có ít nhất 5 ý, kèm nguồn", "nonce": "tm1", "target": f"team:{tid}"}
r1 = client.post("/agents/minh/jobs", params={"brain": B}, json=body).json()
r2 = client.post("/agents/minh/jobs", params={"brain": B}, json=body).json()
tt = store.get_task(r1.get("task_id") or "") or {}
check("giao vào nhóm: một việc nhóm giao cho đúng trợ lý, tiêu chí trong nội dung",
      r1.get("ok") and tt.get("lane") == "team" and tt.get("team_id") == tid and tt.get("assignee_key") == keys["minh"]
      and "Có ít nhất 5 ý" in (tt.get("intent") or ""), (r1, tt))
check("giao vào nhóm: gửi lại cùng nonce không nhân đôi", r2.get("task_id") == r1.get("task_id") and r2.get("created") is False,
      r2)
r = client.post("/agents/hoa/jobs", params={"brain": B}, json=dict(body, nonce="tm2", target=f"team:{tid2}"))
check("trợ lý không trong nhóm: 409, không tạo gì", r.status_code == 409, r.text)
r = client.post("/agents/minh/jobs", params={"brain": B}, json=dict(body, nonce="tm3", target="team:khong-co"))
check("nhóm không có: 404", r.status_code == 404, r.text)
r = client.post("/agents/minh/jobs", params={"brain": B}, json=dict(body, nonce="tm4", target="zalo:abc"))
check("nơi nhận lạ: 400", r.status_code == 400, r.text)
code, j = jobs("minh")
check("việc giao vào nhóm hiện ở tab với nguồn nhóm, vai Thực hiện",
      any(x["id"] == f"team:{r1['task_id']}" and x["roles"] == ["worker"] and x["source"] == "team" for x in j["jobs"]), j)
kt2 = store.get_task(a1["task_id"])
r = client.post("/agents/lan/jobs", params={"brain": B}, json={"text": "Viết lại", "criteria": "Ngắn gọn", "nonce": "c1"})
check("Giao việc vào chat riêng: tiêu chí xong đi vào mô tả việc Kanban",
      "Tiêu chí xong:\nNgắn gọn" in (store.get_task(r.json()["task_id"]) or {}).get("intent", ""), r.json())

# ───────────── Việc kiểm chứng là một việc riêng ─────────────
r = client.post("/agents/lan/jobs", params={"brain": B}, json={"text": "Soát email", "kind": "verify", "nonce": "v0"})
check("kiểm chứng không có tiêu chí: 400", r.status_code == 400, r.text)
r = client.post("/agents/minh/jobs", params={"brain": B}, json={"text": "Tự soát", "kind": "verify", "criteria": "x",
                                                                 "nonce": "v9", "link": f"kanban:{a1['task_id']}"})
check("không giao kiểm chứng việc cho chính trợ lý làm nó", r.status_code == 400, r.text)
r = client.post("/agents/lan/jobs", params={"brain": B}, json={"text": "Soát", "kind": "verify", "criteria": "x",
                                                                "nonce": "v8", "link": "kanban:khong-co"})
check("mục cần kiểm không có trong brain: 404", r.status_code == 404, r.text)
vb = {"text": "Soát email cảm ơn của Minh", "kind": "verify", "criteria": "Đúng tên khách, không lỗi chính tả",
      "nonce": "v1", "link": f"kanban:{a1['task_id']}"}
v1 = client.post("/agents/lan/jobs", params={"brain": B}, json=vb).json()
v2 = client.post("/agents/lan/jobs", params={"brain": B}, json=vb).json()
vt = store.get_task(v1["task_id"])
info = agent_jobs.parse_assign(vt["idempotency_key"])
check("kiểm chứng: kiểu việc và mục được kiểm nằm trong khoá bền, gửi lại không nhân đôi",
      v1["ok"] and v2["task_id"] == v1["task_id"] and info["kind"] == "verify" and info["link"] == f"kanban:{a1['task_id']}"
      and info["agent_key"] == keys["lan"], (v1, info))
# Nội dung việc bị viết lại khi chạy (bước đặc tả): kiểu và liên kết vẫn đọc được từ khoá.
with store._lock:
    store._db.execute("UPDATE tasks SET intent='viết lại', metadata_json='{}' WHERE id=?", (v1["task_id"],))
    store._db.commit()
code, j = jobs("lan")
vj = next(x for x in j["jobs"] if x["id"] == f"kanban:{v1['task_id']}")
check("tab hiện vai Kiểm chứng và mục được kiểm (tên, mở được), kể cả sau khi nội dung bị viết lại",
      vj["roles"] == ["verifier"] and vj["kind"] == "verify" and vj["link"]["title"] == kt2["title"]
      and vj["link"]["open"] == {"kind": "chat", "session_id": a1["session_id"]}, vj)
tv = client.post("/agents/lan/jobs", params={"brain": B},
                 json={"text": "Soát bản tổng hợp", "kind": "verify", "criteria": "Đủ 5 ý", "nonce": "v2",
                       "target": f"team:{tid}", "link": f"team:{r1['task_id']}"}).json()
code, j = jobs("lan")
tvj = next((x for x in j["jobs"] if x["id"] == f"team:{tv.get('task_id')}"), {})
check("kiểm chứng giao vào nhóm: việc nhóm, vai Kiểm chứng, liên kết tới việc được kiểm",
      tv.get("ok") and "verifier" in tvj.get("roles", []) and (tvj.get("link") or {}).get("id") == f"team:{r1['task_id']}"
      and (tvj.get("link") or {}).get("open", {}).get("team_id") == tid, (tv, tvj))
check("brief đọc ngược", agent_jobs.parse_brief(agent_jobs.brief("a", "b", "verify", {"id": "goal:g_1", "title": "T"}))
      == {"kind": "verify", "link": "goal:g_1"})
r = client.get("/agents/lan/jobs/verify-targets", params={"brain": B})
items = r.json().get("items") or []
ids = {x["id"] for x in items}
check("danh sách mục để kiểm: việc của trợ lý khác, bỏ việc người kiểm đang tham gia",
      r.status_code == 200 and f"kanban:{a1['task_id']}" in ids and f"team:{task_id}" not in ids
      and all(x["slug"] != "lan" for x in items), items)

# ───────────── lọc nguồn, phân trang, không trần ngầm ─────────────
for i in range(7):
    client.post("/agents/lan/jobs", params={"brain": B}, json={"text": f"Việc số {i}", "nonce": f"p{i}"})
full = client.get("/agents/lan/jobs", params={"brain": B, "limit": 100}).json()
ids_full = [x["id"] for x in full["jobs"]]
seen, cur, pages = [], "", 0
while True:
    pg = client.get("/agents/lan/jobs", params={"brain": B, "limit": 3, "cursor": cur}).json()
    seen += [x["id"] for x in pg["jobs"]]
    pages += 1
    cur = pg["next"]
    if not cur or pages > 50:
        break
check("phân trang: đi hết các trang ra đúng danh sách đầy đủ, không trùng, không sót",
      seen == ids_full and len(set(seen)) == len(seen) and full["total"] == len(ids_full) and pages > 1,
      (len(seen), len(ids_full), pages))
tm = client.get("/agents/lan/jobs", params={"brain": B, "source": "team", "limit": 100}).json()
check("lọc nguồn Nhóm: chỉ việc nhóm, đếm nguồn khớp",
      tm["jobs"] and all(x["source"] == "team" for x in tm["jobs"]) and tm["source_counts"]["team"] == len(tm["jobs"])
      and sum(tm["counts"].values()) == tm["total"], tm["source_counts"])
ch = client.get("/agents/lan/jobs", params={"brain": B, "source": "chat", "bucket": "waiting", "limit": 100}).json()
check("lọc nguồn Chat riêng và ngăn Đang chờ cùng lúc", ch["jobs"] and all(x["source"] == "chat" and x["bucket"] == "waiting"
                                                                       for x in ch["jobs"]), ch["jobs"][:2])
many = [{"id": f"t_{i:03d}", "title": f"x{i}", "status": "done", "updated_at": i} for i in range(80)]


class _FakeTasks:
    def team_queue(self, _tid):
        return {"version": 1, "running": [], "waiting": [], "blocked": []}

    def team_history(self, _tid, limit):
        return [dict(t, assignee_key="ag_x") for t in sorted(many, key=lambda t: -t["updated_at"])][:min(500, limit)]


class _FakeTeams:
    def busy_of(self, _k):
        return None

    def teams_of_agent(self, _k):
        return [{"team_id": "tm", "brain_id": "R", "name": "N"}]

    def steps(self, _tid):
        return []


got, cur = [], None
while True:
    pg = agent_jobs.collect("ag_x", "x", "R", teams=_FakeTeams(), tasks=_FakeTasks(), cursor=cur, limit=30)
    got += [x["id"] for x in pg["jobs"] if x["source"] == "team"]
    cur = pg["next"]
    if not cur:
        break
check("lịch sử nhóm dài hơn trần cũ (30) vẫn xem hết qua phân trang", len(got) == 80 and len(set(got)) == 80, len(got))

# ───────────── một trợ lý chạy một việc giao trực tiếp một lúc ─────────────
store.set_orchestration(ROOT_B, "auto")
live = [t for t in store.list_tasks(ROOT_B) if t["status"] in ("triage", "ready")]
for t in live:          # dọn hàng để kiểm thứ tự rõ ràng
    store.move(t["id"], "cancelled", "test")
q1 = client.post("/agents/minh/jobs", params={"brain": B}, json={"text": "Việc A", "nonce": "q1"}).json()["task_id"]
q2 = client.post("/agents/minh/jobs", params={"brain": B}, json={"text": "Việc B", "nonce": "q2"}).json()["task_id"]
q3 = client.post("/agents/minh/jobs", params={"brain": B}, json={"text": "Việc C", "nonce": "q3"}).json()["task_id"]
plain = main.tasks_feature.enqueue(B, "Việc thường không gắn trợ lý", "x")
other = client.post("/agents/hoa/jobs", params={"brain": B}, json={"text": "Việc của Hoa", "nonce": "q4"}).json()["task_id"]
c1 = store.next_candidate(ROOT_B)
check("hàng chạy: việc đầu tiên của Minh đi trước", c1 and c1["id"] == q1, c1 and c1["id"])
store.claim(q1, "w1", 60)
check("Minh đang chạy một việc: không nhận việc thứ hai của Minh (kiểm trong giao dịch nhận)",
      store.claim(q2, "w2", 60) is None and store.get_task(q2)["status"] in ("triage", "ready"))
c2 = store.next_candidate(ROOT_B)
check("không bỏ đói: việc thường và việc của trợ lý khác vẫn đi tiếp", c2 and c2["id"] == plain, c2 and c2["id"])
store.claim(plain, "w3", 60)
c3 = store.next_candidate(ROOT_B)
check("việc của Hoa chạy song song với Minh", c3 and c3["id"] == other, c3 and c3["id"])
code, j = jobs("minh")
qj = next(x for x in j["jobs"] if x["id"] == f"kanban:{q2}")
check("thẻ nói rõ đang chờ việc khác của chính trợ lý xong", qj["next"] == {"code": "agent_busy"} and qj["bucket"] == "waiting",
      qj)
store.claim(other, "w4", 60)
check("hết việc khác: không lấy việc thứ hai của Minh khi Minh còn chạy", store.next_candidate(ROOT_B) is None)
store.complete(q1, "w1", "xong")
c4 = store.next_candidate(ROOT_B)
check("Minh xong việc A: việc B tới lượt (đúng thứ tự, không nhảy sang C)", c4 and c4["id"] == q2, c4 and c4["id"])
check("trần chạy chung giữ nguyên (JAVIS_KANBAN_MAX_WORKERS)", 1 <= main.tasks_feature.max_workers <= 8)

# ───────────── huy hiệu việc trên thẻ trợ lý ─────────────
r = client.get("/agents/jobs/counts", params={"brain": B})
cn = r.json()["counts"]
check("huy hiệu: đếm Đang làm và Cần bạn theo trợ lý", r.status_code == 200
      and cn.get("hoa", {}).get("running") == 1 and cn.get("minh", {}).get("running", 0) == 0
      and cn.get("lan", {}).get("running", 0) == 0, cn)
code, j = jobs("hoa")
check("huy hiệu khớp tab Công việc", cn.get("hoa", {}).get("running") == j["counts"]["running"]
      and cn.get("hoa", {}).get("needs_you", 0) == j["counts"]["needs_you"], (cn, j["counts"]))

check("0.191.1: chấm trạng thái: huy hiệu đếm cả Đang chờ, Vừa xong (24 giờ) và Hỏng", all(
      set(v) == {"running", "needs_you", "waiting", "done", "failed"} for v in cn.values()), cn)
check("0.191.1: Minh vừa xong việc A và còn việc B: có mặt với việc đang làm hay đang chờ, việc A tính vừa xong",
      cn.get("minh", {}).get("done", 0) >= 1 and (cn["minh"]["waiting"] + cn["minh"]["running"]) >= 1, cn.get("minh"))
old_cn = agent_jobs.active_counts({"minh": keys["minh"]}, ROOT_B, brain_keys=main._brain_keys(B), tasks=store,
                           sessions=main.get_store(), now=time.time() + 2 * agent_jobs.DONE_FRESH)
check("0.191.1: việc xong quá 24 giờ thì không còn tính vừa xong", old_cn.get("minh", {}).get("done", 0) == 0, old_cn)

# ───────────── vai theo đúng mã trợ lý, không theo slug ─────────────
check("vai: mã đúng của slug thì có vai", "Bạn là Minh" in main._agent_persona(ROOT_B, "minh", keys["minh"]))
check("vai: slug đã sang mã khác (dùng lại slug) thì không có vai",
      main._agent_persona(ROOT_B, "minh", "ag_tro_ly_cu") == "" and main._agent_persona(ROOT_B, "minh", keys["lan"]) == "")
forged = dict(store.get_task(q2), idempotency_key=f"agent:ag_tro_ly_cu:minh:zz")
check("việc Kanban của trợ lý cũ cùng slug không mang vai của trợ lý mới", main.tasks_feature._persona(forged, ROOT_B) == "")
check("việc của đúng trợ lý vẫn mang vai", "Bạn là Minh" in main.tasks_feature._persona(store.get_task(q2), ROOT_B))

print(("FAIL" if fails else "PASS") + f" - test_agent_jobs_0142: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
