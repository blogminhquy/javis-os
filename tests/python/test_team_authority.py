"""Nhóm chat team T3: trưởng nhóm Toàn quyền (spec mục 13, 15.2; ca TC31 tới TC36).

    python tests/run.py team_authority -v

Kho và bộ chạy thật trên SQLite tạm, engine giả theo kịch bản, lệnh quản trị qua khối JAVIS_TEAM. Thao tác của host
(tạo agent, sửa lời nhắc, bật Cộng hưởng, cấp mã) là bản giả ghi lại lời gọi. Không gọi model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import threading
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-auth-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-auth-w-"))

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


class Admin:
    """Thao tác của host mà lệnh quản trị cần, bản giả: agent là dict slug -> {name, prompt}."""

    def __init__(self):
        self.agents = {"lan": {"name": "Lan", "prompt": "Bạn là Lan."}, "minh": {"name": "Minh", "prompt": "Minh"},
                       "hoa": {"name": "Hoa", "prompt": "Hoa"}, "tu": {"name": "Tú", "prompt": "Tú"}}
        self.keys = {s: f"ag_{s}" for s in self.agents}
        self.calls = []
        self.resonance = {}

    def register(self, root, slug):
        self.keys.setdefault(slug, f"ag_{slug}")
        return {"agent_key": self.keys[slug], "slug": slug}

    def exists(self, root, slug):
        return slug in self.agents

    def create_agent(self, root, name, role, prompt):
        slug = name.lower().replace(" ", "-")
        base, n = slug, 2
        while slug in self.agents:
            slug, n = f"{base}-{n}", n + 1
        self.agents[slug] = {"name": name, "prompt": prompt, "role": role}
        self.calls.append(("create", slug))
        return slug

    def edit_prompt(self, root, slug, prompt):
        self.agents[slug]["prompt"] = prompt
        self.calls.append(("edit", slug))

    def set_resonance(self, root, slug, on, by):
        self.resonance[slug] = (on, by)
        self.calls.append(("resonance", slug, on))


class Fake:
    def __init__(self):
        self.script = {}
        self.calls = []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run_(req):
            self.calls.append(req)
            q = self.script.get((agent_key, role)) or []
            ans = q.pop(0) if q else f"{agent_key} {role} xong"
            if callable(ans):
                ans = await ans(req)
            return {"text": ans}
        return "aux", "fake-model", run_


_n = [0]


def world(label):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake, admin = Fake(), Admin()

    def agent_info(root, key):
        slug = next((s for s, k in admin.keys.items() if k == key), None)
        if not slug or slug not in admin.agents:
            return None
        a = admin.agents[slug]
        return {"slug": slug, "name": a["name"], "system": a["prompt"], "model": "", "model_provider": ""}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info, admin=admin)
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
    tm.create_team(str(d), label, "", sid, team_id=tid)
    for s in ("lan", "minh"):
        tm.add_member(tid, admin.keys[s], s)
    tm.set_leader(tid, "ag_lan")
    return r, tm, ts, ss, fake, admin, tm.get(tid)


def run(coro):
    return asyncio.run(coro)


def msgs(ss, t):
    return ss.get_team_messages_page(t["session_id"], limit=200)["messages"]


def reply(r, t, text, cid):
    return run(r.run_replies(r.submit(t["team_id"], text, client_msg_id=cid)))


FULL = {"caps": {"task_turns": {"unlimited": True}},
        "ceilings": {"task_turns": {"unlimited": True}, "daily_turns": 200, "task_steps": 20, "help_depth": 3},
        "can_interrupt": False, "providers_unlimited": ["aux"], "billing": "subscription"}

# ═════ TC31: trưởng nhóm không tự bật; chủ bật thì ghi; lệnh quản trị có sự kiện ═════
r, tm, ts, ss, fake, admin, T = world("tc31")
fake.say("ag_lan", "leader_reply", "Tôi tự bật Toàn quyền." + directive(op="set_authority", mode="full")
         + directive(op="add_member", slug="hoa"))
reply(r, T, "Chào", "c1")
check("TC31 giới hạn: trưởng nhóm không tự bật Toàn quyền (không có op nào làm được)",
      tm.active_authority(T["team_id"]) is None)
check("TC31 giới hạn: lệnh quản trị bị bỏ, có ghi chú, không thêm thành viên",
      not tm.is_active_member(T["team_id"], "ag_hoa") and any("Toàn quyền" in n for n in msgs(ss, T)[-1]["meta"]["notes"]),
      msgs(ss, T)[-1]["meta"]["notes"])
check("TC31 giới hạn: lời nhắc của trưởng nhóm không có khối Toàn quyền", "## Toàn quyền" not in fake.calls[-1]["prompt"])
a = r.grant_authority(T["team_id"], FULL, by="owner")
reply(r, T, "Có gì mới?", "c1b")
lp = fake.calls[-1]["prompt"]
check("TC31 Toàn quyền: lời nhắc của trưởng nhóm liệt kê lệnh quản trị và trần (không có ngắt việc khi chưa cho)",
      "## Toàn quyền" in lp and '"op": "open_job"' in lp and '"op": "add_member"' in lp and '"op": "interrupt"' not in lp
      and "lượt mỗi việc: Không giới hạn" in lp, lp[-1500:])
row = tm.active_authority(T["team_id"])
check("TC31 chủ bật: ghi team_authority gắn đúng trưởng nhóm, có sự kiện", row and row["leader_key"] == "ag_lan"
      and row["granted_by"] == "owner" and any(e["kind"] == "authority_granted" for e in tm.events(T["team_id"])), row)
fake.say("ag_lan", "leader_reply", "Thêm Hoa, tạo người viết, ưu tiên việc." + directive(op="add_member", slug="hoa")
         + directive(op="create_agent", name="Viet Bai", role="Người viết", prompt="Bạn viết bài ngắn."))
reply(r, T, "Sắp xếp nhóm giúp", "c2")
check("TC31 Toàn quyền: trưởng nhóm thêm thành viên có sẵn", tm.is_active_member(T["team_id"], "ag_hoa"))
created = [c for c in admin.calls if c[0] == "create"]
check("TC31 Toàn quyền: trưởng nhóm tạo agent mới, agent vào nhóm và do nhóm quản lý",
      created and tm.is_active_member(T["team_id"], admin.keys[created[0][1]])
      and tm.member(T["team_id"], admin.keys[created[0][1]])["managed_by_team"] == 1, admin.calls)
ev = [e for e in tm.events(T["team_id"]) if e["by"] == "leader:ag_lan"]
check("TC31 mọi thao tác quản trị có sự kiện by=leader:<key>", {e["kind"] for e in ev} >= {"member_added", "agent_created"},
      [e["kind"] for e in ev])
check("TC31 thao tác quản trị hiện trong nhóm (tin hệ thống)", any(m["author_kind"] == "system" and "Hoa" in m["content"]
                                                                 for m in msgs(ss, T)), [m["content"] for m in msgs(ss, T)])
r.submit(T["team_id"], "Việc A", as_job=True, client_msg_id="ja")
jb = r.submit(T["team_id"], "Việc B", as_job=True, client_msg_id="jb")["task_id"]
fake.say("ag_lan", "leader_reply", "Ưu tiên B." + directive(op="reprioritize", task_id=jb, on=True))
reply(r, T, "B gấp hơn", "c3")
q = ts.team_queue(T["team_id"])
check("TC31 Toàn quyền: trưởng nhóm đổi thứ tự việc chờ (CAS như chủ)", [t["id"] for t in q["waiting"]][0] == jb,
      [t["title"] for t in q["waiting"]])
fake.say("ag_lan", "leader_reply", "Mở việc." + directive(op="open_job", title="Viết thông cáo", brief="Ngắn gọn"))
reply(r, T, "Có việc gì cần làm?", "c4")
check("TC31 Toàn quyền: trưởng nhóm mở việc không cần chủ bấm", any(t["title"] == "Viết thông cáo"
                                                                   for t in ts.team_queue(T["team_id"])["waiting"]))
fake.say("ag_lan", "leader_reply", "Mở lại." + directive(op="open_job", title="Viết thông cáo", brief="Ngắn gọn"))
reply(r, T, "Còn gì?", "c5")
check("TC31 mở việc trùng trong lượt khác vẫn là việc khác (khoá theo lượt), không trùng trong cùng lượt",
      len([t for t in ts.team_queue(T["team_id"])["waiting"] if t["title"] == "Viết thông cáo"]) == 2)

# ═════ TC32: Không giới hạn là null + cờ; trần máy chủ, nhà cung cấp vẫn hiện ═════
caps = r.effective_caps(T["team_id"], provider="aux")
check("TC32 Không giới hạn lưu null + cờ, không phải số lớn", caps["task_turns"] is None
      and tm.active_authority(T["team_id"])["grant"]["caps"]["task_turns"] == {"unlimited": True}, caps)
check("TC32 trần trần là số thì trưởng nhóm chưa đặt vẫn theo mặc định", caps["task_steps"] == 8, caps)
check("TC32 trần tối đa daily_turns trong hộp cấp quyền không áp (17/11/2026: không còn trần ngày)",
      caps["daily_turns"] is None and "daily_turns" not in tm.active_authority(T["team_id"])["grant"]["ceilings"], caps)
check("TC32 provider không được tích (D6): Không giới hạn lượt model không áp, dùng mặc định",
      r.effective_caps(T["team_id"], provider="anthropic-api")["task_turns"] == 12)
view = r.authority_view(T["team_id"])
check("TC32 hộp cấp quyền luôn hiện các trần không bỏ được", {"server_call_ceiling", "provider_quota", "account",
                                                             "technical"} <= set(view["fixed_limits"]), view)
fake.say("ag_lan", "leader_reply", "Nâng trần." + directive(op="set_cap", cap="task_turns", value=30)
         + directive(op="set_cap", cap="daily_turns", value=150)
         + directive(op="set_cap", cap="task_steps", value=50) + directive(op="set_cap", cap="help_depth", unlimited=True))
reply(r, T, "Đặt trần", "c6")
caps = r.effective_caps(T["team_id"], provider="aux")
check("TC32 trưởng nhóm đặt trần trong trần trần", caps["task_turns"] == 30, caps)
check("TC32 trưởng nhóm không đặt được trần ngày (đã bỏ), vẫn không giới hạn", caps["daily_turns"] is None, caps)
check("TC32 vượt trần trần bị từ chối (task_steps 50 > 20), Không giới hạn ngoài trần trần bị từ chối",
      caps["task_steps"] == 8 and caps["help_depth"] == 2, caps)
tu = [tm.reserve_turn(T["team_id"], "t_x", None, "ag_lan", "work", daily_cap=None, day_start=0, task_cap=None)
      for _ in range(15)]
check("TC32 trần None = không có trần khi giữ chỗ (15 lượt > 12 mặc định)", len(tu) == 15)

# ═════ TC33: không sửa cấu hình agent không do nhóm quản lý; agent do nhóm quản lý thì báo nhóm khác ═════
tid2 = team_store.new_team_id()
sid2 = ss.create_session(brain="B", channel=f"team:{tid2}")
tm.create_team(T["brain_id"], "Nhóm khác", "", sid2, team_id=tid2)
new_slug = created[0][1]
tm.add_member(tid2, admin.keys[new_slug], new_slug)
tm.add_member(tid2, "ag_minh", "minh")
fake.say("ag_lan", "leader_reply", "Sửa." + directive(op="edit_agent", agent="minh", prompt="Minh mới")
         + directive(op="set_resonance", agent="minh", on=True)
         + directive(op="edit_agent", agent=new_slug, prompt="Viết thật ngắn"))
reply(r, T, "Chỉnh trợ lý", "c7")
check("TC33 agent không do nhóm quản lý: không sửa được lời nhắc hay Cộng hưởng (D5)",
      admin.agents["minh"]["prompt"] == "Minh" and "minh" not in admin.resonance)
check("TC33 agent do nhóm quản lý: sửa được lời nhắc", admin.agents[new_slug]["prompt"] == "Viết thật ngắn")
last = msgs(ss, T)
check("TC33 sửa agent đang ở nhóm khác: tin báo liệt kê nhóm bị ảnh hưởng",
      any(m["author_kind"] == "system" and "Nhóm khác" in m["content"] for m in last), [m["content"] for m in last][-4:])
r.set_managed(T["team_id"], "ag_minh", True, by="owner")
try:
    r.set_managed(tid2, "ag_minh", True, by="owner")
    two = True
except team_store.TeamError:
    two = False
check("TC33 chủ giao agent cho nhóm quản lý; mỗi agent tối đa một nhóm quản lý", not two
      and tm.member(T["team_id"], "ag_minh")["managed_by_team"] == 1)

# ═════ TC34: thu hồi giữa lượt ═════
r, tm, ts, ss, fake, admin, T = world("tc34")
r.grant_authority(T["team_id"], FULL, by="owner")


async def revoke_mid_turn(req):
    r.revoke_authority(T["team_id"], by="owner", reason="chủ thu hồi")
    return "Nội dung vẫn đúng." + directive(op="add_member", slug="hoa")


fake.say("ag_lan", "leader_reply", revoke_mid_turn)
reply(r, T, "Thêm người", "r1")
m = msgs(ss, T)[-1]
check("TC34 thu hồi giữa lượt: lệnh quản trị sau mốc thu hồi bị từ chối", not tm.is_active_member(T["team_id"], "ag_hoa"))
check("TC34 nội dung vẫn đăng như ở Quyền giới hạn", m["content"].startswith("Nội dung vẫn đúng") and m["meta"]["applied"])
check("TC34 trần về mức giới hạn", r.effective_caps(T["team_id"], provider="aux")["task_turns"] == 12)
r.grant_authority(T["team_id"], FULL, by="owner")
job = r.submit(T["team_id"], "Việc dài", mentions=["ag_minh"], as_job=True, client_msg_id="long")["task_id"]
ts.claim_team_next(T["team_id"], "w")
for _ in range(13):
    x = tm.reserve_turn(T["team_id"], job, None, "ag_minh", "work")
    tm.mark_engine(x, "aux", "m")
    tm.settle_turn(x, "ok")
ts.team_requeue(job)
r.revoke_authority(T["team_id"], by="owner", reason="chủ thu hồi")
run(r.dispatch_once())
t = ts.get_task(job)
check("TC34 việc đang chạy vượt trần mới vào cap_reached, chờ chủ", t["status"] == "team_blocked"
      and t["block_kind"] == "cap_reached", t)
r.grant_authority(T["team_id"], FULL, by="owner")
tm.set_leader(T["team_id"], "ag_minh")
check("TC34 đổi trưởng nhóm: Toàn quyền không chuyển theo (M11)", tm.active_authority(T["team_id"]) is None
      and any(e["kind"] == "authority_revoked" for e in tm.events(T["team_id"])))

# ═════ TC35: không có "Được ngắt việc" thì không ngắt được việc đang chạy ═════
r, tm, ts, ss, fake, admin, T = world("tc35")
r.grant_authority(T["team_id"], FULL, by="owner")
job = r.submit(T["team_id"], "Việc", mentions=["ag_minh"], as_job=True, client_msg_id="j")["task_id"]
ts.claim_team_next(T["team_id"], "w")
fake.say("ag_lan", "leader_reply", "Ngắt." + directive(op="interrupt", task_id=job, reason="đổi hướng"))
reply(r, T, "Dừng việc kia", "i1")
check("TC35 không có quyền ngắt: việc đang chạy vẫn chạy", ts.get_task(job)["status"] == "team_running")
grant = dict(FULL, can_interrupt=True)
r.grant_authority(T["team_id"], grant, by="owner")
fake.say("ag_lan", "leader_reply", "Ngắt." + directive(op="interrupt", task_id=job, reason="đổi hướng"))
reply(r, T, "Dừng việc kia", "i2")
ev = [e for e in tm.events(T["team_id"]) if e["kind"] == "job_interrupted"]
check("TC35 có quyền ngắt: việc bị huỷ, lý do ghi vào sự kiện và hiện trong nhóm", ts.get_task(job)["status"] == "cancelled"
      and ev and ev[0]["after"]["reason"] == "đổi hướng"
      and any(m["author_kind"] == "system" and "đổi hướng" in m["content"] for m in msgs(ss, T)))

# ═════ TC36: vòng không tiến triển ở Không giới hạn: tạm dừng và báo ═════
r, tm, ts, ss, fake, admin, T = world("tc36")
inbox = []
r._notify_fn = lambda team_id, text: inbox.append(text)
ALL = {"task_turns": {"unlimited": True}, "task_steps": {"unlimited": True}, "help_depth": {"unlimited": True},
       "daily_turns": {"unlimited": True}}
grant = dict(FULL, caps=dict(ALL), ceilings=dict(ALL))
r.grant_authority(T["team_id"], grant, by="owner")
for k in ("task_turns", "task_steps", "help_depth", "daily_turns"):
    r._apply_admin(T["team_id"], "ag_lan", {"op": "set_cap", "cap": k, "unlimited": True}, [], "test")
check("TC36 mọi trần lượt đều Không giới hạn", all(v is None for k, v in r.effective_caps(T["team_id"], provider="aux").items()
                                                  if k in ("task_turns", "task_steps", "help_depth", "daily_turns")))
same = "Vẫn kết quả cũ" + directive(op="request_help", agent="ag_lan", question="giúp")
fake.say("ag_minh", "work", same, same)
fake.say("ag_lan", "help", "Đây")
job = r.submit(T["team_id"], "Việc lặp", mentions=["ag_minh"], as_job=True, client_msg_id="loop")["task_id"]
run(r.dispatch_once())
t = ts.get_task(job)
check("TC36 không tiến triển ở Không giới hạn: việc tạm dừng (chặn no_progress) và báo, không chạy tiếp âm thầm",
      t["status"] == "team_blocked" and t["block_kind"] == "no_progress" and inbox, (t["status"], t["block_kind"], inbox))
check("TC36 số lượt có hạn dù Không giới hạn", len(tm.turns(T["team_id"])) <= 4, len(tm.turns(T["team_id"])))

# ═════ Review T3 ═════
# #1: bỏ thành viên thì bỏ cờ "do nhóm quản lý"; thêm lại không tự sống lại; nhóm khác giao quản lý được.
r, tm, ts, ss, fake, admin, T = world("rv1")
tidB = team_store.new_team_id()
tm.create_team(T["brain_id"], "B", "", ss.create_session(brain="B", channel=f"team:{tidB}"), team_id=tidB)
r.set_managed(T["team_id"], "ag_minh", True)
tm.remove_member(T["team_id"], "ag_minh")
tm.add_member(tidB, "ag_minh", "minh")
try:
    r.set_managed(tidB, "ag_minh", True)
    moved = True
except team_store.TeamError:
    moved = False
check("review #1: bỏ khỏi nhóm A thì nhóm B giao quản lý được", moved)
tm.add_member(T["team_id"], "ag_minh", "minh")
check("review #1: thêm lại vào A không tự sống lại cờ quản lý", tm.member(T["team_id"], "ag_minh")["managed_by_team"] == 0)

# #2: provider của lượt lấy đúng như engine thật (engine_for), không suy riêng.
r, tm, ts, ss, fake, admin, T = world("rv2")
labels = {"ag_lan": "anthropic-cli"}
orig = fake.engine_for
fake.engine_for = lambda team, key, role: (labels.get(key, "aux"),) + tuple(orig(team, key, role)[1:])
r.engine_for = fake.engine_for
r.grant_authority(T["team_id"], dict(FULL, caps={"task_turns": {"unlimited": True}},
                                     ceilings={"task_turns": {"unlimited": True}}, providers_unlimited=["aux"]))
check("review #2: agent chạy anthropic-cli (theo engine) không được Không giới hạn khi chủ chỉ tích aux",
      r._caps(tm.get(T["team_id"]), "ag_lan")["task_turns"] == 12 and r._caps(tm.get(T["team_id"]), "ag_minh")["task_turns"] is None)

# #3: 17/11/2026 không còn trần lượt mỗi ngày: số 1 gửi lên (trang cũ) không lưu, tin thứ hai của chủ vẫn có trả lời,
# không cần Toàn quyền hay provider được tích.
r, tm, ts, ss, fake, admin, T = world("rv3")
orig3 = fake.engine_for
r.engine_for = lambda team, key, role: ("anthropic-cli",) + tuple(orig3(team, key, role)[1:])
tm.set_caps(T["team_id"], {"daily_turns": 1})
check("review #3: set_caps nhận daily_turns nhưng trần ngày vẫn không giới hạn", tm.get(T["team_id"])["caps"]["daily_turns"]
      is None)
reply(r, T, "Một", "d1")
sub = r.submit(T["team_id"], "Hai", client_msg_id="d2")
check("review #3: không còn trần ngày chặn tin của chủ", sub["replies"] == ["ag_lan"]
      and "daily_cap" not in sub["notes"], sub)

# #4: việc trưởng nhóm mở không trỏ nhầm tin nguồn.
r, tm, ts, ss, fake, admin, T = world("rv4")
r.grant_authority(T["team_id"], FULL)
fake.say("ag_lan", "leader_reply", "Mở." + directive(op="open_job", title="Việc mở", brief="x", agent="minh"))
reply(r, T, "Mở việc đi", "o1")
jt = [t for t in ts.team_queue(T["team_id"])["waiting"] if t["title"] == "Việc mở"][0]
check("review #4: nguồn của việc trưởng nhóm mở không thành số tin giả", r._source_id(jt) == [], jt["source_ref"])

# #7: chủ đặt trần cố định (không có trần tối đa) được; trưởng nhóm không đổi được trần đó.
r, tm, ts, ss, fake, admin, T = world("rv7")
r.grant_authority(T["team_id"], dict(FULL, caps={"task_steps": 4}, ceilings={}))
check("review #7: chủ đặt trần không kèm trần tối đa", r.effective_caps(T["team_id"])["task_steps"] == 4)
notes = []
with r.accept_lock:
    r._apply_admin(T["team_id"], "ag_lan", {"op": "set_cap", "cap": "task_steps", "value": 6}, notes, "x")
check("review #7: trưởng nhóm không đổi được trần không có trần tối đa", r.effective_caps(T["team_id"])["task_steps"] == 4
      and notes, notes)

# #8: tối đa 10 lệnh quản trị mỗi lượt.
r, tm, ts, ss, fake, admin, T = world("rv8")
r.grant_authority(T["team_id"], FULL)
fake.say("ag_lan", "leader_reply", "Nhiều." + "".join(directive(op="open_job", title=f"V{i}", brief="x") for i in range(14)))
reply(r, T, "Nhiều việc", "m1")
check("review #8: tối đa 10 lệnh quản trị mỗi lượt, phần thừa có ghi chú", len(ts.team_queue(T["team_id"])["waiting"]) == 10
      and any("10 lệnh" in n for n in msgs(ss, T)[-1]["meta"]["notes"]), len(ts.team_queue(T["team_id"])["waiting"]))

print(f"\n{'FAIL' if fails else 'PASS'} - test_team_authority: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
