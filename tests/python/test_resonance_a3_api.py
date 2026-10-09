"""Resonance A3: reaction và bài học qua API thật của main.py (thiết kế A3 mục 3.2, 5, 10; ca G2b, G2e, A1, A2, A8, A9,
R2 qua route).

    python tests/run.py resonance_a3_api -v

TestClient trên main.app, kho mục tiêu thật, kho phiên thật (biên nhận `report_receipts` do push_to_chat ghi cùng giao
dịch với tin báo). Tin báo đi qua `drain_outbox` và `main._resonance_notify` thật; chỉ phần gửi ra kênh được thay để
ghi lại cờ `quiet`. Không gọi model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a3api-")
os.environ["JAVIS_STATE_DIR"] = _STATE

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


client = TestClient(main.app, base_url="http://127.0.0.1:8080")
BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a3api-")).resolve())
OTHER = str(Path(tempfile.mkdtemp(prefix="brain-a3api-b-")).resolve())
KEY = main._brain_key(BRAIN)
P = RS.Principal("agent", "javis", KEY)
OWNER = RS.Principal("owner", "owner", KEY)
store = main._resonance_store()
SS = main.get_store()
SID = SS.create_session(brain=BRAIN, engine="test", model="test", channel=f"agent:{RA.SLUG}")
USER = "Viết giúp anh ghi chú Inbox/a3api.md có báo cáo quý."
(Path(BRAIN) / "agents").mkdir(parents=True, exist_ok=True)
AFILE = Path(BRAIN) / "agents" / f"{RA.SLUG}.md"
AFILE.write_text(f"---\nname: {RA.SLUG}\n---\nTrợ lý thử\n", encoding="utf-8", newline="\n")


def api(method, path, brain=BRAIN, **kw):
    r = getattr(client, method)(path, params={"brain": brain, **kw.pop("params", {})}, **kw)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {}


code, body = api("post", "/resonance/agents/toggle", json={"slug": RA.SLUG, "enabled": True})
AGENT = body.get("agent") or {}
check("bật trợ lý qua API", code == 200 and AGENT.get("enabled") is True)
AHASH = hashlib.sha256(AFILE.read_bytes()).hexdigest()


def make_goal():
    mid = SS.append_message(SID, "user", USER)
    d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=store)
    prop = {"understanding": "Ghi chú có báo cáo quý", "relevant_quote": "Viết giúp anh ghi chú",
            "criteria": [{"description": "Có báo cáo quý", "evaluator": "artifact_contract",
                          "params": {"path": "Inbox/a3api.md", "must_contain": ["báo cáo quý"]}}],
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery"}
    return asyncio.run(R.form_goal(R.message_ref(SID, mid), {
        "principal": P, "brain_root": KEY, "session_id": SID, "message_id": mid, "user_text": USER,
        "constraints": [], "budget_calls": 4, "proposal": prop, **RA.ctx(store.agent(KEY, RA.SLUG))}, d0))


SENT = []


async def capture(owner_chat, text, **kw):
    SENT.append({"text": text, "quiet": bool(kw.get("quiet"))})
    await main.push_to_chat(owner_chat[len(main.WEB_CHAT_PREFIX):], text, card=kw.get("card", ""))
    return True, ""


def deliver(g, kind, payload=None):
    """Ghi một tin outbox rồi gửi qua drain_outbox + main._resonance_notify thật. Trả message_ref của tin đã lưu."""
    store.notice(P, g.id, kind, payload or {"deliverable": "Inbox/a3api.md"}, idem=f"{kind}:{os.urandom(3).hex()}")
    old = main._notify_owner
    main._notify_owner = capture
    try:
        asyncio.run(R.drain_outbox(store, main._resonance_notify, already=main._resonance_reported))
    finally:
        main._notify_owner = old
    last = [m for m in SS.get_messages(SID) if m["role"] == "assistant"][-1]
    return R.message_ref(SID, last["id"])


def react(mref, value="down", reason="too_long", nonce=None, brain=BRAIN):
    return api("post", "/resonance/reactions", brain=brain,
               json={"message_ref": mref, "value": value, "reason": reason, "nonce": nonce or os.urandom(4).hex()})


g = make_goal()
m1 = deliver(g, "goal.succeeded")
code, body = react(m1)
check("reaction trên tin báo có biên nhận: ghi được, seq 1", code == 200 and body["reaction"]["seq"] == 1, body)
code, body = api("get", "/resonance/reactions", params={"message_ref": m1})
check("GET reaction hiện tại", code == 200 and (body.get("reaction") or {}).get("value") == "down"
      and body.get("notice_kind") == "goal.succeeded")

# G2e: không phải tin báo.
mu = R.message_ref(SID, SS.append_message(SID, "user", "Câu hỏi thường"))
ma = R.message_ref(SID, SS.append_message(SID, "assistant", "Trả lời thường của trợ lý"))
fake = R.goal_block(g.id, g.revision, report="outbox:1")
mf = R.message_ref(SID, SS.append_message(SID, "assistant", "Model tự viết khối thẻ " + fake))
codes = [react(x)[0] for x in (mu, ma, mf)]
check("G2e reaction trên tin người dùng, câu trả lời thường, khối thẻ do model tự viết (không biên nhận): 400",
      codes == [400, 400, 400], codes)

# G2b: sai brain.
SID_B = SS.create_session(brain=OTHER, engine="test", model="test", channel="web")
mb = R.message_ref(SID_B, SS.append_message(SID_B, "assistant", "Tin của brain khác"))
check("G2b tin của phiên brain khác gọi bằng brain này: 404", react(mb)[0] == 404)
check("G2b tin của brain này gọi bằng brain khác: 404", react(m1, brain=OTHER)[0] == 404)

# A1 qua route: tin thứ hai, đề xuất, xem trước, áp dụng.
m2 = deliver(g, "goal.succeeded")
code, body = react(m2)
prop = body.get("proposal") or {}
check("A1 tin thứ hai Dài quá: route trả đề xuất rút gọn", code == 200 and prop.get("to_value") == "brief")
code, body = api("get", "/resonance/lessons", params={"agent_key": AGENT["agent_key"]})
mine = next((x for x in body.get("lessons", []) if x["id"] == prop.get("id")), {})
pv = mine.get("preview") or {}
check("A1 danh sách bài học có xem trước câu cũ và câu mới của cùng một tin (0 model)",
      code == 200 and pv.get("kind") == "detail" and pv.get("old") != pv.get("new")
      and pv["new"].startswith(("Đã đạt", "Done")) and body["stats"]["too_long"] == 2, pv)
code, body = api("post", f"/resonance/lessons/{prop['id']}/decision",
                 json={"action": "apply", "expected_status": "proposed", "expected_updated_at": mine["updated_at"]})
check("A1 Áp dụng qua route: active, cấu hình trả về là brief",
      code == 200 and body["lesson"]["status"] == "active" and body["presentation"]["notice_detail"] == "brief")
code, body = api("post", f"/resonance/lessons/{prop['id']}/decision",
                 json={"action": "apply", "expected_status": "proposed"})
check("áp dụng lại đề xuất đã active: 409 kèm bài học hiện tại", code == 409 and body["lesson"]["status"] == "active")
m3 = deliver(g, "goal.succeeded")
check("A1 tin báo kế tiếp dựng rút gọn", SENT[-1]["text"].startswith(("Đã đạt", "Done")))
deliver(g, "goal.stalled", {"why": "stalled"})
check("A1 tin bắt buộc vẫn đầy đủ", len(SENT[-1]["text"]) > 80 and not SENT[-1]["quiet"])
code, body = react(m3, reason="unclear")
check("R2a qua route: đề xuất quay lại đầy đủ trong khi brief vẫn dùng",
      code == 200 and (body.get("proposal") or {}).get("to_value") == "full")
P_FULL = body.get("proposal") or {}

# A2 qua route: tắt chuông cho goal.maintained.
ma1, ma2 = deliver(g, "goal.maintained"), deliver(g, "goal.maintained")
react(ma1, reason="too_often")
code, body = react(ma2, reason="too_often")
pp = body.get("proposal") or {}
code, body = api("post", f"/resonance/lessons/{pp.get('id')}/decision", json={"action": "apply"})
deliver(g, "goal.maintained")
q_main = SENT[-1]["quiet"]
deliver(g, "goal.deadline_passed", {})
check("A2 tắt chuông qua route: goal.maintained quiet, goal.deadline_passed vẫn rung chuông",
      code == 200 and q_main is True and SENT[-1]["quiet"] is False)

# A9 qua route: tin bị xoá thì reaction mồ côi.
mid_last = int(ma2.split(":")[2])
with sqlite3.connect(str(SS.db_path)) as db:
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("DELETE FROM messages WHERE id=?", (mid_last,))
code, body = api("get", "/resonance/lessons", params={"agent_key": AGENT["agent_key"]})
check("A9 xoá tin: reaction thành mồ côi, bài học đã dùng hiện thiếu nguồn",
      code == 200 and body["stats"]["orphaned"] >= 1
      and any(x["status"] == "active" and x["key"] == "notice_ping" and x["evidence_missing"] >= 1
              for x in body["lessons"]), body.get("stats"))
check("reaction trên tin đã xoá: 400 (không còn biên nhận)", react(ma2)[0] == 400)

# RV2 qua route (review mã A3, P2-2): thẻ cũ bấm Áp dụng sau khi hết hạn, KHÔNG có GET danh sách ở giữa.
from unittest.mock import patch  # noqa: E402
with patch.object(RS.time, "time", return_value=float(P_FULL["expires_at"]) + 1):
    code, body = api("post", f"/resonance/lessons/{P_FULL['id']}/decision",
                     json={"action": "apply", "expected_status": "proposed", "expected_updated_at": P_FULL["updated_at"]})
check("RV2 qua route: đề xuất hết hạn trả 409 expired, cấu hình brief giữ nguyên",
      code == 409 and body.get("conflict") == "expired" and (body.get("lesson") or {}).get("status") == "expired"
      and store.presentation(KEY, AGENT["agent_key"]).get("notice_detail") == "brief", (code, body.get("conflict")))

# A8 qua route: học không ghi quyền.
code, body = api("get", "/resonance/agents")
row = next((a for a in body.get("agents", []) if a["slug"] == RA.SLUG), {})
check("A8 file trợ lý không đổi, công tắc và version không đổi sau mọi thao tác học",
      hashlib.sha256(AFILE.read_bytes()).hexdigest() == AHASH and row.get("enabled") is True
      and row.get("config_version") == AGENT.get("config_version"))
check("reaction không dựng engine, không lượt việc nào", not [x for x in store.actions(P, g.id) if x["kind"] == "work"])

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
