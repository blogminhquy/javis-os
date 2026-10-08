"""Resonance A1: một chính sách cổng agent cho tool, hub, scheduler, bàn giao, đăng, gán và API công tắc.

    python tests/run.py resonance_a1_gates -v

Engine giả, SQLite thật, plugin javis_goal thật, hub HTTP thật (`mcp_hub.handle_http`) với khoá `X-Javis-Turn`,
API thật qua TestClient. Không gọi model. Đi theo ma trận ở thiết kế A1 mục 8:
  1 chat thường bị từ chối trước khi ghi kho          7 bật lại: không mở pause/huỷ; đầu ra giữ được đăng, 0 lượt
  2 agent A bật, B tắt; list không lẫn                    model mới, ý định đăng MỚI theo version hiện tại
  3 hai lượt của hai agent chạy xen không mượn quyền    8 xoá qua host rồi tạo lại cùng tên: không chuyển quyền
  5 giả danh, ngoài lượt, khoá giả hay đã chết          9 mục tiêu chưa gán không chạy; gán CAS; đầu ra trước gán
  6 tắt sau khi giữ lượt: không đăng, lượt vẫn tính       không được đăng
 10 công tắc trong phiên mở trước lúc cấp mã: needs_new_session (review vòng 2, P2); phiên cũ không nhận mã mới
 12 engine chưa mang khoá lượt: tool từ chối; bảng khả năng theo engine
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import contextvars
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a1g-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import mcp_hub  # noqa: E402
import plugins_host  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import turn_context  # noqa: E402
import _resonance_agent as RA  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


BRAIN = main._brain_key(str(Path(tempfile.mkdtemp(prefix="brain-a1g-")).resolve()))
OWNER = RS.Principal("owner", "owner", BRAIN)
store = main._resonance_store()
USER = "Em lo giúp anh bản hướng dẫn nhận hàng Docs/hd.md, sửa tới khi anh thấy dùng được."
DELIV = "Docs/hd.md"
GOOD = "# Hướng dẫn nhận hàng\n\n## Lỗi hay gặp\n\n- Thiếu phiếu\n"
PROPOSAL = {"understanding": "Bản hướng dẫn nhận hàng", "relevant_quote": "Em lo giúp anh bản hướng dẫn nhận hàng",
            "criteria": [{"description": "Có mục Lỗi hay gặp", "evaluator": "artifact_contract",
                          "params": {"path": DELIV, "must_contain": ["Lỗi hay gặp"]}}],
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery",
            "mode": "achieve"}

A = RA.enable(store, BRAIN, "viet-bai")
B = RA.enable(store, BRAIN, "kiem-tra")
B = RA.disable(store, BRAIN, "kiem-tra")
_, ROUTE = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
CALL = ROUTE["javis_goal"]["call"]


def counts():
    with sqlite3.connect(str(store.path)) as c:
        return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("goals", "intents", "goal_events", "goal_agents", "handoff_agents"))


def agent_now(slug):
    return store.agent(BRAIN, slug)


def tool(agent, sid, mid, args, slug, text=USER):
    with RA.turn(agent, sid, mid, text, BRAIN, slug=slug):
        return asyncio.run(CALL(args))


# ═══════════ 1. chat thường, ngoài lượt, kênh khác: từ chối trước mọi lần ghi ═══════════
c0 = counts()
tok = turn_context.bind(turn_context.make("dashboard", chat_id="plain", la_chu=True, session_id="plain",
                                          message_id=1))
out_plain = asyncio.run(CALL({"op": "create", **PROPOSAL}))
turn_context.reset(tok)
out_none = asyncio.run(CALL({"op": "create", **PROPOSAL}))
check("1 chat thường gọi javis_goal: ERROR, không ghi gì vào kho",
      out_plain.startswith("ERROR") and "trợ lý" in out_plain and counts() == c0)
check("1 gọi ngoài lượt: ERROR, không ghi gì", out_none.startswith("ERROR") and counts() == c0)

# ═══════════ 2. agent A bật, B tắt; list chỉ của đúng agent ═══════════
out_a = tool(A, "sA", 1, {"op": "create", **PROPOSAL}, "viet-bai")
gA = store.find_by_key(OWNER, R.message_ref("sA", 1))
check("2 agent A bật: lập được mục tiêu, gắn mã A", not out_a.startswith("ERROR") and gA and gA.agent_key == A["agent_key"])
check("2 có handoff_agents ghi đúng version lúc mở bàn giao",
      store.handoff_agent(OWNER, gA.id, 1) == {"agent_key": A["agent_key"], "agent_config_version": A["config_version"]})
c1 = counts()
out_b = tool(B, "sB", 1, {"op": "create", **PROPOSAL}, "kiem-tra")
check("2 agent B tắt: ERROR nêu agent_off, không ghi gì", out_b.startswith("ERROR") and "agent_off" in out_b
      and counts() == c1)
B = RA.enable(store, BRAIN, "kiem-tra")
tool(B, "sB", 2, {"op": "create", **PROPOSAL}, "kiem-tra")
gB = store.find_by_key(OWNER, R.message_ref("sB", 2))
lA = tool(A, "sA", 3, {"op": "list"}, "viet-bai")
lB = tool(B, "sB", 3, {"op": "list"}, "kiem-tra")
check("2 list của A chỉ thấy mục tiêu của A, của B chỉ thấy của B",
      gA.id in lA and gB.id not in lA and gB.id in lB and gA.id not in lB)

# ═══════════ 5. giả danh: update mục tiêu của agent khác, tham số agent lạ ═══════════
c2 = counts()
out_x = tool(A, "sA", 4, {"op": "update", "goal_id": gB.id, "expected_revision": 1, "agent_id": B["agent_key"],
                          "agent_key": B["agent_key"], **PROPOSAL, "understanding": "đổi trộm"}, "viet-bai")
check("5 A sửa mục tiêu của B (kể cả truyền agent_id của B): ERROR như không tồn tại, không lộ nội dung",
      out_x.startswith("ERROR") and "đổi trộm" not in out_x and gB.understanding not in out_x and counts() == c2
      and store.get(OWNER, gB.id).revision == 1)
stale = dict(A, config_version=A["config_version"] - 1 if A["config_version"] > 1 else 99)
out_v = tool(stale, "sA", 5, {"op": "create", **PROPOSAL}, "viet-bai")
check("5 ngữ cảnh mang version cũ (công tắc đã đổi sau khi gắn lượt): ERROR agent_changed, không ghi",
      out_v.startswith("ERROR") and "agent_changed" in out_v and counts() == c2)
fake = dict(A, agent_key="ag_0000000000000000")
out_f = tool(fake, "sA", 6, {"op": "create", **PROPOSAL}, "viet-bai")
check("5 mã agent không có trong sổ: ERROR, không ghi", out_f.startswith("ERROR") and counts() == c2)


# ═══════════ 3 + 5. hub HTTP thật với khoá X-Javis-Turn (đường của Codex), hai lượt chạy xen ═══════════
class _Req:
    def __init__(self, headers, body):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self._body = body

    async def json(self):
        return self._body


async def _hub(key, args, i=1):
    h = {"Authorization": "Bearer T"}
    if key is not None:
        h[turn_context.HEADER] = key
    body = {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": "javis_goal", "arguments": args}}
    # Tiến trình con của engine CLI: không mang gì của ngữ cảnh lượt, chỉ còn header.
    resp = await asyncio.create_task(mcp_hub.handle_http(_Req(h, body)), context=contextvars.Context())
    return json.loads(resp.body)["result"]["content"][0]["text"]


mcp_hub.hub_token = lambda: "T"


async def _fake_discover(*a, **kw):
    return [], {"javis_goal": ROUTE["javis_goal"]}
mcp_hub.discover_all = _fake_discover
keys = {}


async def _codex_turn(agent, slug, sid, mid):
    with RA.turn(agent, sid, mid, USER, BRAIN, slug=slug):
        keys[slug] = turn_context.issue_key()
        await asyncio.sleep(0)
        return await _hub(keys[slug], {"op": "create", **PROPOSAL})


async def _two():
    return await asyncio.gather(_codex_turn(A, "viet-bai", "hA", 1), _codex_turn(B, "kiem-tra", "hB", 1))


hA, hB = asyncio.run(_two())
gHA, gHB = store.find_by_key(OWNER, R.message_ref("hA", 1)), store.find_by_key(OWNER, R.message_ref("hB", 1))
check("3 hub HTTP, hai lượt của hai agent chạy xen: mỗi mục tiêu gắn đúng agent của lượt mình",
      gHA is not None and gHB is not None and gHA.agent_key == A["agent_key"] and gHB.agent_key == B["agent_key"],
      (hA[:80], hB[:80]))
c3 = counts()
r_none = asyncio.run(_hub(None, {"op": "create", **PROPOSAL}))
r_forged = asyncio.run(_hub("forged-" + "x" * 30, {"op": "create", **PROPOSAL}))
r_dead = asyncio.run(_hub(keys["viet-bai"], {"op": "create", **PROPOSAL}))
check("5 hub không có khoá / khoá giả / khoá của lượt đã xong: ERROR, không ghi gì",
      all(x.startswith("ERROR") for x in (r_none, r_forged, r_dead)) and counts() == c3)

# ═══════════ 6 + 7. tắt sau khi giữ lượt; bật lại dùng lại đầu ra bằng ý định đăng MỚI ═══════════


class Eng:
    def __init__(self, text=GOOD, on_query=None):
        self.text, self.on_query, self.queries, self.max_wall_s = text, on_query, 0, None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        if self.on_query:
            self.on_query()
        yield {"type": "final", "content": self.text}


class Ev:
    def __init__(self):
        self.items = {}

    def put(self, goal, action_id, text, metadata):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest()}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


EV = Ev()


def deps(eng):
    return R.GoalDeps(engine_factory=lambda s, t: (eng, {"provider": "fake", "text_only": True}),
                      budget=R.CallBudget(0), store=store, principal=RS.Principal("agent", "host", BRAIN),
                      brain_root=BRAIN, evidence=EV, notify=None)


def adv(gid, eng, kind="wake"):
    return asyncio.run(R.advance(gid, {"kind": kind}, deps(eng)))


def new_goal(agent, slug, sid, mid):
    d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=store)
    return asyncio.run(R.form_goal(R.message_ref(sid, mid), {
        "principal": RS.Principal("agent", agent["agent_key"], BRAIN), "brain_root": BRAIN, "session_id": sid,
        "message_id": mid, "user_text": USER, "constraints": [], "budget_calls": 4, "proposal": PROPOSAL,
        **RA.ctx(store.agent(BRAIN, slug))}, d0))


target = Path(BRAIN) / DELIV
target.unlink(missing_ok=True)
g6 = new_goal(A, "viet-bai", "s6", 1)
e6 = Eng(on_query=lambda: (RA.disable(store, BRAIN, "viet-bai"), RA.enable(store, BRAIN, "viet-bai")))
a6 = adv(g6.id, e6, "start")
w6 = [x for x in store.actions(OWNER, g6.id) if x["kind"] == "work"]
check("6 tắt rồi bật trong lúc model chạy: lượt đã giữ vẫn tính (1 lượt), KHÔNG đăng trong lượt đó",
      e6.queries == 1 and store.get(OWNER, g6.id).calls_used == 1 and not target.exists()
      and len(w6) == 1 and w6[0]["status"] == "succeeded", a6.rationale)
check("6 ý định lượt việc gốc ghi mã và version lúc giữ lượt",
      w6[0]["intent"].get("agent_key") == A["agent_key"]
      and w6[0]["intent"].get("agent_config_version") == A["config_version"])
check("6 hẹn xét lại ngay theo quyền hiện tại",
      any(w["kind"] == "work" and w["due_at"] <= time.time() + 1 for w in store.wakes(OWNER, g6.id)))
e6b = Eng()
adv(g6.id, e6b)
pubs = [x for x in store.actions(OWNER, g6.id) if x["kind"] == "publish"]
A_now = agent_now("viet-bai")
check("7 lần thức sau: đăng đầu ra đang giữ, KHÔNG gọi model lại", e6b.queries == 0 and target.is_file()
      and target.read_text(encoding="utf-8").startswith("# Hướng dẫn nhận hàng"))
check("7 ý định đăng MỚI mang version hiện tại và trỏ về lượt việc gốc; ý định gốc giữ nguyên",
      len(pubs) == 1 and pubs[0]["intent"].get("agent_config_version") == A_now["config_version"]
      and pubs[0]["intent"].get("source_action") == w6[0]["id"]
      and store.get_action(OWNER, w6[0]["id"])["intent"].get("agent_config_version") == A["config_version"])
check("7 mục tiêu đạt sau khi đăng (bằng chứng của host)", store.get(OWNER, g6.id).status == "succeeded")

# tắt hẳn sau khi giữ lượt: không đăng, bật lại thì đăng mà không gọi model
target.unlink(missing_ok=True)
A = agent_now("viet-bai")
g6c = new_goal(A, "viet-bai", "s6", 2)
e6c = Eng(on_query=lambda: RA.disable(store, BRAIN, "viet-bai"))
adv(g6c.id, e6c, "start")
check("6 tắt hẳn sau khi giữ lượt: không đăng, chặn agent_off, lượt đã dùng vẫn ghi",
      not target.exists() and store.run_state(OWNER, g6c.id)["block_reason"] == "agent_off"
      and store.get(OWNER, g6c.id).calls_used == 1)
store.set_paused(OWNER, g6c.id, True)
g_cx = new_goal(B, "kiem-tra", "s6", 3)
store.cancel(OWNER, g_cx.id, 1)
on = TestClient(main.app, base_url="http://127.0.0.1:8080").post(
    "/resonance/agents/toggle", params={"brain": BRAIN}, json={"slug": "viet-bai", "enabled": True})
e6d = Eng()
adv(g6c.id, e6d)
check("7 bật lại không mở pause: mục tiêu đang tạm dừng vẫn đứng yên, không gọi model",
      on.status_code == 200 and store.get(OWNER, g6c.id).paused and e6d.queries == 0 and not target.exists())
store.set_paused(OWNER, g6c.id, False)
adv(g6c.id, e6d)
check("7 bỏ tạm dừng: đầu ra giữ từ trước được đăng, 0 lượt model mới",
      e6d.queries == 0 and target.is_file() and store.get(OWNER, g6c.id).calls_used == 1)
check("7 mục tiêu đã huỷ vẫn huỷ", store.get(OWNER, g_cx.id).status == "cancelled")

# bàn giao trong lượt: tắt giữa lượt thì bản chat không được tiếp nhận
A = agent_now("viet-bai")
g_h = new_goal(A, "viet-bai", "s7", 1)
with sqlite3.connect(str(store.path)) as c:
    c.execute("INSERT OR REPLACE INTO handoffs(goal_id,revision,message_ref,owner,status,created_at,updated_at) "
              "VALUES(?,?,?,?,?,?,?)", (g_h.id, 1, R.message_ref("s7", 1), R.BOOT_ID, "pending", 1, 1))
    c.execute("INSERT OR REPLACE INTO handoff_agents VALUES(?,?,?,?,?)",
              (g_h.id, 1, A["agent_key"], A["config_version"], 1))
RA.disable(store, BRAIN, "viet-bai")
RA.enable(store, BRAIN, "viet-bai")
res_h = store.finish_handoff(OWNER, g_h.id, 1, R.message_ref("s7", 1),
                             {"path": DELIV, "sha256": "0" * 64, "evidence_id": "ev_x"})
check("6 bàn giao: version lúc mở khác version hiện tại thì KHÔNG tiếp nhận bản chat",
      res_h == "agent_changed" and not store.evidence_for(OWNER, g_h.id, 1, kind="chat_output"))

# ═══════════ 8. xoá qua host rồi tạo lại cùng tên ═══════════
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
A_old = agent_now("viet-bai")
g8 = new_goal(A_old, "viet-bai", "s8", 1)
r = client.post("/agents/delete", data={"slug": "viet-bai", "brain": BRAIN})
check("8 xoá trợ lý qua host: mã nghỉ", r.status_code == 200
      and store.agent_by_key(BRAIN, A_old["agent_key"])["status"] == "retired")
check("8 slug không hợp lệ bị từ chối, không xoá gì ngoài thư mục agents",
      client.post("/agents/delete", data={"slug": "../x", "brain": BRAIN}).status_code == 400)
e8 = Eng()
adv(g8.id, e8, "start")
check("8 mục tiêu của mã đã nghỉ bị chặn, không gọi model", e8.queries == 0
      and store.run_state(OWNER, g8.id)["block_reason"] == "agent_retired")
A_new = RA.enable(store, BRAIN, "viet-bai")
adv(g8.id, e8)
check("8 tạo lại cùng tên: mã mới; mục tiêu cũ KHÔNG chạy theo mã mới",
      A_new["agent_key"] != A_old["agent_key"] and e8.queries == 0 and store.get(OWNER, g8.id).agent_key
      == A_old["agent_key"])

# ═══════════ 9. mục tiêu chưa gán; gán CAS; đầu ra trước lúc gán không được đăng ═══════════
target.unlink(missing_ok=True)
d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=store)
g9 = asyncio.run(R.form_goal(R.message_ref("s9", 1), {
    "principal": RS.Principal("agent", "javis", BRAIN), "brain_root": BRAIN, "session_id": "s9", "message_id": 1,
    "user_text": USER, "constraints": [], "budget_calls": 4, "proposal": PROPOSAL}, d0))
old_act = store.begin_action(RS.Principal("agent", "javis", BRAIN), g9.id, 1, "work", lease_until=time.time() - 5,
                             now=time.time() - 600)
Path(g9.output_root).mkdir(parents=True, exist_ok=True)
(Path(g9.output_root) / f"{old_act['id']}.md").write_text(GOOD, encoding="utf-8", newline="\n")
e9 = Eng()
adv(g9.id, e9)
check("9 mục tiêu chưa gán: không chạy, không gọi model, không hẹn lịch",
      e9.queries == 0 and store.run_state(OWNER, g9.id)["block_reason"] == "unassigned"
      and not [w for w in store.wakes(OWNER, g9.id) if w["kind"] == "work"])
r = client.post(f"/goals/{g9.id}/assign", params={"brain": BRAIN},
                json={"agent_key": A_new["agent_key"], "expected_revision": 7})
check("9 gán với revision cũ: 409, không gán", r.status_code == 409 and store.get(OWNER, g9.id).agent_key == "")
r = client.post(f"/goals/{g9.id}/assign", params={"brain": BRAIN},
                json={"agent_key": A_old["agent_key"], "expected_revision": 1})
check("9 gán cho mã đã nghỉ: 400", r.status_code == 400 and store.get(OWNER, g9.id).agent_key == "")
r = client.post(f"/goals/{g9.id}/assign", params={"brain": BRAIN},
                json={"agent_key": A_new["agent_key"], "expected_revision": 1})
check("9 gán đúng: mục tiêu thuộc mã mới, có sự kiện, hẹn thức",
      r.status_code == 200 and store.get(OWNER, g9.id).agent_key == A_new["agent_key"]
      and any(e["kind"] == "agent_assigned" for e in store.events(OWNER, g9.id))
      and any(w["kind"] == "work" for w in store.wakes(OWNER, g9.id)))
r = client.post(f"/goals/{g9.id}/assign", params={"brain": BRAIN},
                json={"agent_key": B["agent_key"], "expected_revision": 1})
check("9 gán lần hai (chuyển sang trợ lý khác): 409, A1 chưa hỗ trợ", r.status_code == 409
      and store.get(OWNER, g9.id).agent_key == A_new["agent_key"])
adv(g9.id, e9)
check("9 sau khi gán: đầu ra của lượt dở TRƯỚC lúc gán không được đăng; lượt mới chạy theo trợ lý",
      e9.queries == 1 and target.is_file()
      and old_act["id"] not in [x["intent"].get("source_action") for x in store.actions(OWNER, g9.id)
                                if x["kind"] == "publish"])

# ═══════════ 10. công tắc trong phiên mở trước lúc cấp mã (review vòng 2, P2) ═══════════
ss = main.get_store()
(Path(BRAIN) / "agents" / "ban-moi.md").write_text("---\nname: ban-moi\n---\nA\n", encoding="utf-8")
first = client.post("/resonance/agents/toggle", params={"brain": BRAIN}, json={"slug": "ban-moi", "enabled": True})
old_sid = ss.create_session(brain=BRAIN, engine="test", model="test", channel="agent:ban-moi")
store.session_agent(BRAIN, old_sid, "ban-moi", ss.get_session(old_sid)["created_at"])       # phiên có lượt với A
client.post("/agents/delete", data={"slug": "ban-moi", "brain": BRAIN})
(Path(BRAIN) / "agents" / "ban-moi.md").write_text("---\nname: ban-moi\n---\nB thay thế\n", encoding="utf-8")
pre_sid = ss.create_session(brain=BRAIN, engine="test", model="test", channel="agent:ban-moi")
ss.append_message(pre_sid, "user", "Chào trợ lý mới")
time.sleep(0.02)
r = client.post("/resonance/agents/toggle", params={"brain": BRAIN},
                json={"slug": "ban-moi", "enabled": True, "session_id": pre_sid})
check("10 bật trong phiên mở TRƯỚC lúc cấp mã mới: báo needs_new_session, không báo dùng được",
      r.status_code == 200 and r.json().get("session") == "needs_new_session"
      and r.json()["agent"]["agent_key"] != first.json()["agent"]["agent_key"])
check("10 resolver vẫn bảo thủ: phiên đó không có danh tính", main._resonance_turn_agent(
    pre_sid, BRAIN, ss.get_session) is None)
new_sid = ss.create_session(brain=BRAIN, engine="test", model="test", channel="agent:ban-moi")
r2 = client.post("/resonance/agents/toggle", params={"brain": BRAIN},
                 json={"slug": "ban-moi", "enabled": True, "session_id": new_sid})
got = main._resonance_turn_agent(new_sid, BRAIN, ss.get_session)
check("10 mở phiên mới qua host rồi kiểm: ready, lượt có đúng mã mới",
      r2.json().get("session") == "ready" and got and got["key"] == r.json()["agent"]["agent_key"])
r3 = client.post("/resonance/agents/toggle", params={"brain": BRAIN},
                 json={"slug": "ban-moi", "enabled": True, "session_id": old_sid})
check("10 ca âm: phiên của trợ lý cũ không bao giờ thành ready với mã mới",
      r3.json().get("session") == "needs_new_session" and main._resonance_turn_agent(old_sid, BRAIN, ss.get_session)
      is None)
r4 = client.post("/resonance/agents/toggle", params={"brain": BRAIN},
                 json={"slug": "ban-moi", "enabled": True, "session_id": new_sid.replace("a", "b") + "x"})
check("10 phiên không thuộc trợ lý này: not_this_agent", r4.json().get("session") == "not_this_agent")
r5 = client.post("/resonance/agents/toggle", params={"brain": BRAIN}, json={"slug": "khong-co", "enabled": True})
check("10 bật trợ lý không có file: 404, không cấp mã", r5.status_code == 404 and store.agent(BRAIN, "khong-co") is None)
lst = client.get("/resonance/agents", params={"brain": BRAIN}).json()
row = next((a for a in lst.get("agents", []) if a["slug"] == "ban-moi"), {})
check("10 danh sách trợ lý khớp kho: mã, bật, trạng thái, khả năng engine",
      row.get("agent_key") == r.json()["agent"]["agent_key"] and row.get("enabled") is True
      and row.get("status") == "active" and isinstance(row.get("support"), dict))
check("10 danh sách có mục chờ gán là số đếm (không tự gán)", isinstance(lst.get("unassigned"), int))

# ═══════════ 11. đường agent trọn vòng qua thân THẬT của run_turn (engine giả) ═══════════
import ast  # noqa: E402
import localefmt  # noqa: E402
import luot_dang_chay  # noqa: E402
import nghe_sua  # noqa: E402
import types  # noqa: E402
import uuid  # noqa: E402

V = agent_now("viet-bai")
S11 = ss.create_session(brain=BRAIN, engine="test", model="test", channel="agent:viet-bai")
T11 = "# Hướng dẫn nhận hàng\n\n## Lỗi hay gặp\n\n- Thiếu phiếu giao\n"
M11 = ss.append_message(S11, "user", USER)
seen11 = {}
target.unlink(missing_ok=True)


async def _noop(*a, **kw):
    pass


async def do_turn_11(conv_sid, message, *a, user_mid=0, **kw):
    seen11["hint"] = "javis_goal op=create" in main.build_system_prompt(BRAIN)
    names = {t["fn"] for t in plugins_host.plugin_tools("full", BRAIN, scope_vault=False)[0]}
    seen11["tool_listed"] = "javis_goal" in names
    main._resonance_note_write(conv_sid, user_mid, BRAIN, {"type": "tool_call", "name": "Write", "id": "tu_11",
                                                           "input": {"file_path": str(target), "content": T11}})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(T11, encoding="utf-8", newline="\n")
    main._resonance_note_write(conv_sid, user_mid, BRAIN, {"type": "tool_result", "tool_use_id": "tu_11",
                                                           "is_error": False, "content": "ok"})
    seen11["tool"] = await CALL({"op": "create", **PROPOSAL})
    return "xong"


_ns = dict(asyncio=asyncio, sys=sys, time=time, uuid=uuid, nghe_sua=nghe_sua, localefmt=localefmt,
           turn_context=turn_context, store=ss, send_raw=_noop, _persist_turn=_noop,
           _CHAT_RUNTIME=types.SimpleNamespace(finish_job=lambda *a: None),
           context_runtime=types.SimpleNamespace(bind_trace=lambda *a: None, reset_trace=lambda *a: None,
                                                 event_fields=lambda *a: {}),
           _CONTEXT_RUNTIME=types.SimpleNamespace(finish=lambda *a: None, note_error=lambda *a: None,
                                                  record_runtime_event=lambda *a: None),
           luot_dang_chay=luot_dang_chay, WEB_CHAT_PREFIX="web:", _brain_root=main._brain_root,
           _do_turn=do_turn_11, _resonance_after_turn=main._resonance_after_turn,
           _resonance_turn_agent=main._resonance_turn_agent, _record_quality_shadow=lambda *a: None,
           tien_trinh_nen=types.SimpleNamespace(bo_tag=lambda *a: None),
           _engine_outcome_reset=lambda *a: None, _engine_outcome_exception=lambda *a: None,
           _engine_outcome_turn=lambda *a: None, _engine_outcome_pop=lambda *a: {})
_rt = next(n for n in ast.walk(ast.parse((SERVER / "main.py").read_text(encoding="utf-8")))
           if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_turn")
exec(compile(ast.Module(body=[_rt], type_ignores=[]), "main-run_turn", "exec"), _ns)
_old_ev = main._RESONANCE_EVIDENCE
main._RESONANCE_EVIDENCE = EV
try:
    asyncio.run(_ns["run_turn"](S11, USER, BRAIN, "t11", None, user_mid=M11))
finally:
    main._RESONANCE_EVIDENCE = _old_ev
g11 = store.find_by_key(OWNER, R.message_ref(S11, M11))
check("11 phiên agent: prompt có dòng gợi ý, tool có trong danh sách của lượt",
      seen11.get("hint") is True and seen11.get("tool_listed") is True)
check("11 tool trong lượt lập mục tiêu gắn đúng mã của phiên",
      g11 is not None and g11.agent_key == V["agent_key"] and not str(seen11.get("tool", "")).startswith("ERROR"),
      str(seen11.get("tool", ""))[:120])
check("11 cuối lượt: bản Write trong lượt được tiếp nhận (bàn giao theo cổng agent)",
      g11 is not None and [e["kind"] for e in store.events(OWNER, g11.id)].count("artifact_adopted") == 1)

# ═══════════ 12. engine chưa mang khoá lượt; bảng khả năng ═══════════
check("12 Grok, Antigravity: chưa lập được mục tiêu", not R.engine_support("grok-cli")["goal"]
      and not R.engine_support("antigravity-cli")["goal"])
check("12 Claude Code: lập mục tiêu và nhận bản chat", R.engine_support("anthropic-cli")["goal"]
      and R.engine_support("anthropic-cli")["chat_output"])
check("12 Codex và engine API: lập được, chưa nhận bản chat (A4)",
      R.engine_support("openai-oauth")["goal"] and not R.engine_support("openai-oauth")["chat_output"]
      and R.engine_support("openrouter")["goal"] and not R.engine_support("openrouter")["chat_output"])
check("12 engine lạ: coi như chưa hỗ trợ", not R.engine_support("la-hoat")["goal"])

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
