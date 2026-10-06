"""Resonance M4: thẻ mục tiêu và phản hồi có nghĩa rõ, đi qua API thật của main.py.

    python tests/run.py resonance_mvp_feedback -v

TestClient trên main.app (http://127.0.0.1:8080), kho SQLite thật, kho phiên thật, engine GIẢ. Không gọi model.
Tên test theo Task M4 của docs/superpowers/plans/2026-10-06-resonance-00-mvp.md.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m4-")
os.environ["JAVIS_STATE_DIR"] = _STATE

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


client = TestClient(main.app, base_url="http://127.0.0.1:8080")
BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-m4-")).resolve())
OTHER = str(Path(tempfile.mkdtemp(prefix="brain-m4b-")).resolve())
KEY = main._brain_key(BRAIN)
P = RS.Principal("agent", "javis", KEY)
OWNER = RS.Principal("owner", "owner", KEY)
store = main._resonance_store()
SID = main.get_store().get_or_create(None, brain=BRAIN, engine="test", model="test")
USER = "Viết giúp anh ghi chú Inbox/ke-hoach.md liệt kê ba việc: gọi thợ, nộp báo cáo, mua quà. Anh sẽ duyệt."
GOOD = "# Kế hoạch\n\n- Gọi thợ\n- Nộp báo cáo\n- Mua quà\n"


class Eng:
    def __init__(self, text=GOOD):
        self.text, self.queries, self.max_wall_s, self.last_prompt = text, 0, None, ""

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        self.last_prompt = prompt
        yield {"type": "final", "content": self.text}


class Ev:
    def __init__(self):
        self.items = {}

    def put(self, goal, action_id, text, metadata):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": __import__("hashlib").sha256(text.encode()).hexdigest()}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


EV = Ev()


def deps(eng):
    return R.GoalDeps(engine_factory=lambda s, t: (eng, {"provider": "fake", "text_only": True}),
                      budget=R.CallBudget(0), store=store, principal=P, brain_root=KEY, evidence=EV,
                      notify=None)


_mid = {"n": 0}


def make_goal(criteria=None, guards=None, budget=4):
    _mid["n"] += 1
    mid = main.get_store().append_message(SID, "user", USER)
    d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=store)
    prop = {"understanding": "Ghi chú kế hoạch ba việc trong Inbox", "relevant_quote": "Viết giúp anh ghi chú",
            "criteria": criteria or [
                {"description": "Ghi chú có đủ ba việc", "evaluator": "artifact_contract",
                 "params": {"path": "Inbox/ke-hoach.md", "must_contain": ["Gọi thợ", "Nộp báo cáo", "Mua quà"]}},
                {"description": "Anh duyệt ghi chú", "evaluator": "human_confirmation"}],
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery"}
    if guards:
        prop["guards"] = guards
    g = asyncio.run(R.form_goal(R.message_ref(SID, mid), {
        "principal": P, "brain_root": KEY, "session_id": SID, "message_id": mid, "user_text": USER,
        "constraints": [], "budget_calls": budget, "proposal": prop}, d0))
    (Path(KEY) / "Inbox" / "ke-hoach.md").unlink(missing_ok=True)
    return g


def api(method, path, **kw):
    r = getattr(client, method)(path, params={"brain": BRAIN}, **kw)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {}


# ───────────── công tắc theo brain ─────────────
code, body = api("get", "/goals/g_khong_co")
check("brain chưa bật Resonance: API trả 403, không lộ gì", code == 403)
code, body = api("post", "/resonance/settings", json={"enabled": True})
check("bật Resonance qua API: ghi đúng Javis/resonance.json của brain", code == 200 and body.get("enabled") is True
      and R.enabled_for(KEY))
code, body = api("get", "/resonance/settings")
check("đọc công tắc trả đúng trạng thái", body.get("enabled") is True)

# ───────────── test_silence_is_unknown ─────────────
g = make_goal()
eng = Eng()
asyncio.run(R.advance(g.id, {"kind": "start"}, deps(eng)))
code, body = api("get", f"/goals/{g.id}")
v = body.get("goal") or {}
check("test_silence_is_unknown: chưa ai xác nhận thì tiêu chí người dùng là unknown, mục tiêu chờ",
      code == 200 and [c["verdict"] for c in v["criteria"]] == ["met", "unknown"] and v["status"] == "active"
      and v["block_reason"] == "human_confirmation" and v["fit"] == "unknown")
check("thẻ có đủ: cách hiểu, sản phẩm, bản đang xác nhận, dòng thời gian hành động, hạn mức",
      v["understanding"] and v["deliverable"] == "Inbox/ke-hoach.md" and len(v["artifact_ref"]) == 64
      and any(t["kind"] == "work" and t["status"] == "succeeded" for t in v["timeline"])
      and v["calls_used"] == 1 and v["budget_calls"] == 4)

# ───────────── test_goal_fit_not_outcome ─────────────
code, body = api("post", f"/goals/{g.id}/feedback", json={"kind": "goal_fit_confirmed", "expected_revision": 1})
v = body.get("goal") or {}
check("test_goal_fit_not_outcome: Đúng ý chỉ xác nhận cách hiểu, KHÔNG làm sản phẩm thành đạt",
      code == 200 and v["fit"] == "confirmed" and v["criteria"][1]["verdict"] == "unknown" and v["status"] == "active")
human = v["criteria"][1]["id"]
code, body = api("post", f"/goals/{g.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                           "criterion_id": v["criteria"][0]["id"],
                                                           "artifact_ref": v["artifact_ref"]})
check("Đạt yêu cầu cho tiêu chí host kiểm tự động bị từ chối (không xác nhận tay được)", code == 400)
code, body = api("post", f"/goals/{g.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                           "criterion_id": human, "artifact_ref": "0" * 64})
check("Đạt yêu cầu cho bản sản phẩm khác bản đang có: 409, trả trạng thái mới", code == 409 and body.get("goal"))
code, body = api("post", f"/goals/{g.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                           "criterion_id": human, "artifact_ref": v["artifact_ref"],
                                                           "idempotency_key": "k-accept-1"})
check("Đạt yêu cầu đúng tiêu chí, đúng bản: ghi nhận, hẹn đánh giá lại", code == 200 and not body.get("duplicate"))
code2, body2 = api("post", f"/goals/{g.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                             "criterion_id": human, "artifact_ref": v["artifact_ref"],
                                                             "idempotency_key": "k-accept-1"})
check("bấm lại cùng khoá: không ghi lần hai", code2 == 200 and body2.get("duplicate") is True)
check("thẻ hiện ngay xác nhận vừa bấm (đọc sống, đúng luật đánh giá), chưa cần đợi nhịp đánh giá",
      body.get("goal", {}).get("criteria", [{}, {}])[1].get("verdict") == "met"
      and body.get("goal", {}).get("status") == "active")
asyncio.run(R.advance(g.id, {"kind": "wake"}, deps(eng)))
check("sau xác nhận đúng: host đánh giá lại và kết luận thành công, không gọi model thêm",
      store.get(P, g.id).status == "succeeded" and eng.queries == 1)

# ───────────── test_feedback_old_revision ─────────────
g2 = make_goal()
asyncio.run(R.advance(g2.id, {"kind": "start"}, deps(Eng())))
code, body = api("get", f"/goals/{g2.id}")
old = body["goal"]
R.revise_goal(store, P, g2.id, 1, {"relevant_quote": "Anh sẽ duyệt", "understanding": "Ghi chú kế hoạch có hạn"},
              {"message_ref": R.message_ref(SID, 9001), "session_id": SID, "message_id": 9001, "user_text": USER})
code, body = api("post", f"/goals/{g2.id}/feedback", json={"kind": "goal_fit_confirmed", "expected_revision": 1})
check("test_feedback_old_revision: thẻ cũ (revision 1) không xác nhận được revision 2: 409",
      code == 409 and body.get("goal", {}).get("revision") == 2 and store.fit_status(OWNER, g2.id, 2) == "unknown")
code, body = api("post", f"/goals/{g2.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                            "criterion_id": old["criteria"][1]["id"],
                                                            "artifact_ref": old["artifact_ref"]})
check("Đạt yêu cầu từ thẻ revision cũ: 409", code == 409)

# ───────────── test_feedback_cross_brain ─────────────
(Path(OTHER) / "Javis").mkdir(parents=True, exist_ok=True)
(Path(OTHER) / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
r = client.get(f"/goals/{g2.id}", params={"brain": OTHER})
check("test_feedback_cross_brain: đọc mục tiêu của brain khác qua brain này: 404", r.status_code == 404)
r = client.post(f"/goals/{g2.id}/feedback", params={"brain": OTHER},
                json={"kind": "goal_fit_confirmed", "expected_revision": 2})
check("test_feedback_cross_brain: phản hồi chéo brain: 404, không ghi gì",
      r.status_code == 404 and store.fit_status(OWNER, g2.id, 2) == "unknown")
def _perm(f):
    try:
        f()
    except PermissionError:
        return True
    return False


check("agent không tự ghi xác nhận được (PermissionError)",
      _perm(lambda: store.record_feedback(P, g2.id, 2, "goal_fit_confirmed", {})))

# ───────────── Chưa đúng ý: dừng tác động tới khi có revision mới ─────────────
g3 = make_goal()
e3 = Eng()
asyncio.run(R.advance(g3.id, {"kind": "start"}, deps(e3)))
api("post", f"/goals/{g3.id}/feedback", json={"kind": "goal_fit_rejected", "expected_revision": 1,
                                               "comment": "Anh muốn chia theo ngày"})
asyncio.run(R.advance(g3.id, {"kind": "wake"}, deps(e3)))
check("Chưa đúng ý: không làm thêm, không gọi model, chờ người dùng nói rõ hơn",
      e3.queries == 1 and store.run_state(P, g3.id)["block_reason"] == "fit_rejected")
code, body = api("post", f"/goals/{g3.id}/commands", json={"command": "resume", "expected_revision": 1})
check("Tiếp tục không vượt được Chưa đúng ý (cần nói rõ hơn)", body.get("ok") is False)
R.revise_goal(store, P, g3.id, 1, {"relevant_quote": "Anh sẽ duyệt", "understanding": "Ghi chú kế hoạch chia theo ngày"},
              {"message_ref": R.message_ref(SID, 9002), "session_id": SID, "message_id": 9002, "user_text": USER})
_a3 = asyncio.run(R.advance(g3.id, {"kind": "wake"}, deps(e3)))
check("revision mới (người dùng nói rõ hơn) mở lại bình thường: làm bản cho revision mới rồi mới chờ duyệt",
      e3.queries == 2 and store.run_state(P, g3.id)["block_reason"] == "human_confirmation")

# ───────────── Cần chỉnh: làm lại có phản hồi, xác nhận cũ không áp cho bản mới ─────────────
g4 = make_goal()
e4 = Eng()
asyncio.run(R.advance(g4.id, {"kind": "start"}, deps(e4)))
v4 = api("get", f"/goals/{g4.id}")[1]["goal"]
api("post", f"/goals/{g4.id}/feedback", json={"kind": "outcome_rejected", "expected_revision": 1,
                                               "criterion_id": v4["criteria"][1]["id"], "artifact_ref": v4["artifact_ref"],
                                               "comment": "Thêm ngày cho từng việc"})
e4.text = GOOD + "\nNgày: thứ Hai, thứ Ba, thứ Tư\n"
asyncio.run(R.advance(g4.id, {"kind": "wake"}, deps(e4)))
v4b = api("get", f"/goals/{g4.id}")[1]["goal"]
check("Cần chỉnh: làm lại một lượt, lời gửi model có lời người dùng muốn chỉnh",
      e4.queries == 2 and "Thêm ngày cho từng việc" in e4.last_prompt)
check("bản mới: xác nhận cũ không còn áp dụng, lại chờ người dùng",
      v4b["artifact_ref"] != v4["artifact_ref"] and v4b["criteria"][1]["verdict"] == "unknown"
      and v4b["block_reason"] == "human_confirmation")

# ───────────── Xác nhận không vượt kiểm tra khách quan và guard ─────────────
keep = Path(KEY) / "Notes" / "giu.md"
keep.parent.mkdir(parents=True, exist_ok=True)
keep.write_text("giữ\n", encoding="utf-8")
g5 = make_goal(guards=[{"description": "Ghi chú giữ còn", "evaluator": "artifact_contract",
                        "params": {"path": "Notes/giu.md"}}])
asyncio.run(R.advance(g5.id, {"kind": "start"}, deps(Eng())))
v5 = api("get", f"/goals/{g5.id}")[1]["goal"]
keep.unlink()
api("post", f"/goals/{g5.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                               "criterion_id": v5["criteria"][1]["id"], "artifact_ref": v5["artifact_ref"]})
asyncio.run(R.advance(g5.id, {"kind": "wake"}, deps(Eng())))
check("Đạt yêu cầu không vượt guard: guard nhảy thì không thành công",
      store.get(P, g5.id).status == "active" and store.run_state(P, g5.id)["block_reason"] == "guard")
code, body = api("post", f"/goals/{g5.id}/commands", json={"command": "resume", "expected_revision": 1})
check("Tiếp tục khi guard vẫn sai: không mở lại, nói rõ vì sao", body.get("ok") is False and "bảo vệ" in body.get("reason", ""))
keep.write_text("giữ\n", encoding="utf-8")
code, body = api("post", f"/goals/{g5.id}/commands", json={"command": "resume", "expected_revision": 1})
asyncio.run(R.advance(g5.id, {"kind": "wake"}, deps(Eng())))
check("người dùng sửa xong rồi Tiếp tục: guard clear thì mở lại và kết luận được",
      body.get("ok") is True and store.get(P, g5.id).status == "succeeded")
g6 = make_goal()
asyncio.run(R.advance(g6.id, {"kind": "start"}, deps(Eng(text="# Kế hoạch\n\n- Gọi thợ\n"))))
v6 = api("get", f"/goals/{g6.id}")[1]["goal"]
code, body = api("post", f"/goals/{g6.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                            "criterion_id": v6["criteria"][1]["id"],
                                                            "artifact_ref": v6["artifact_ref"]})
asyncio.run(R.advance(g6.id, {"kind": "wake"}, deps(Eng(text="# Kế hoạch\n\n- Gọi thợ\n"))))
check("Đạt yêu cầu không ghi đè kiểm tra khách quan đã thất bại",
      store.get(P, g6.id).status == "active" and v6["criteria"][0]["verdict"] == "not_met")

# ───────────── lệnh: tạm dừng, tiếp tục, huỷ ─────────────
g7 = make_goal()
code, body = api("post", f"/goals/{g7.id}/commands", json={"command": "pause", "expected_revision": 99})
check("Tạm dừng luôn có hiệu lực, kể cả thẻ cũ", body.get("ok") is True and store.get(P, g7.id).paused)
e7 = Eng()
asyncio.run(R.advance(g7.id, {"kind": "start"}, deps(e7)))
check("đang tạm dừng: không gọi model", e7.queries == 0)
api("post", f"/goals/{g7.id}/commands", json={"command": "resume", "expected_revision": 1})
check("Tiếp tục: bỏ tạm dừng và hẹn làm ngay", not store.get(P, g7.id).paused
      and any(w["kind"] == "work" for w in store.wakes(P, g7.id)))
code, body = api("post", f"/goals/{g7.id}/commands", json={"command": "cancel", "expected_revision": 1})
check("Huỷ: mục tiêu cancelled, không còn lịch", body.get("ok") is True and store.get(P, g7.id).status == "cancelled"
      and not store.wakes(P, g7.id))
code, body = api("post", f"/goals/{g7.id}/commands", json={"command": "xoa_het"})
check("lệnh lạ: 400", code == 400)

# ───────────── test_reload_keeps_goal_action_links + test_report_replay_same_mid ─────────────
g8 = make_goal(criteria=[{"description": "Ghi chú có đủ ba việc", "evaluator": "artifact_contract",
                          "params": {"path": "Inbox/ke-hoach.md", "must_contain": ["Gọi thợ"]}}])
asyncio.run(R.advance(g8.id, {"kind": "start"}, deps(Eng())))
sent = []


async def capture_ok(owner_chat, text, **kw):
    sent.append(owner_chat)
    sid = owner_chat[len(main.WEB_CHAT_PREFIX):]
    await main.push_to_chat(sid, text, card=kw.get("card", ""))
    return True, ""

_old = main._notify_owner
main._notify_owner = capture_ok
_orig_mark = store.outbox_mark_delivered
_g8_row = [r["id"] for r in store.outbox_pending() if r["goal_id"] == g8.id and r["kind"] in R.NOTIFY_KINDS][0]


def _mark_dies_after_save(oid):
    # Tin của g8 đã LƯU vào kho phiên (push_to_chat), rồi tiến trình chết trước khi đánh dấu outbox.
    if oid == _g8_row:
        raise RuntimeError("chết giữa hai kho")
    return _orig_mark(oid)

store.outbox_mark_delivered = _mark_dies_after_save
try:
    try:
        asyncio.run(R.drain_outbox(store, main._resonance_notify, already=main._resonance_reported))
    except RuntimeError:
        pass
finally:
    store.outbox_mark_delivered = _orig_mark
n_first = len([m for m in main.get_store().get_messages(SID) if f"outbox:{_g8_row}" in (m["content"] or "")])
asyncio.run(R.drain_outbox(store, main._resonance_notify, already=main._resonance_reported))
main._notify_owner = _old
msgs = [m for m in main.get_store().get_messages(SID) if m["role"] == "assistant"]
cards = [b for m in msgs for b in R.parse_goal_blocks(m["content"]) if b["goal_id"] == g8.id]
all_reports = [b.get("report") for m in main.get_store().get_messages(SID) if m["role"] == "assistant"
               for b in R.parse_goal_blocks(m["content"]) if b.get("report", "").startswith("outbox:")]
check("test_report_replay_same_mid: chết giữa lưu tin và đánh dấu outbox thì nhịp sau KHÔNG gửi lần hai",
      n_first >= 1 and len([c for c in cards if c.get("report", "").startswith("outbox:")]) == 1
      and len(all_reports) == len(set(all_reports)) and not store.outbox_pending())
check("tin báo lưu trong kho phiên mang thẻ mục tiêu (khối JAVIS_RESONANCE) có goal_id và revision",
      cards and cards[0]["revision"] == 1)
code, body = api("get", f"/goals/{cards[0]['goal_id']}")
check("test_reload_keeps_goal_action_links: sau F5 đọc lại tin, thẻ lấy lại được mục tiêu và các hành động của nó",
      code == 200 and any(t["kind"] == "work" for t in body["goal"]["timeline"])
      and any(t["kind"] == "publish" for t in body["goal"]["timeline"]))
check("khối thẻ không lọt qua kênh chữ (bị bóc như khối điều khiển khác)",
      "JAVIS_RESONANCE" not in main.channel_context.strip_control_blocks(msgs[-1]["content"]))
check("push_to_chat chỉ nhận đúng khuôn khối thẻ, chuỗi tuỳ ý không lọt vào kho phiên",
      not asyncio.run(main.push_to_chat(SID, "x", card="<script>")) or
      "<script>" not in main.get_store().get_messages(SID)[-1]["content"])

# ───────────── POST /goal-requests ─────────────
mid_u = main.get_store().append_message(SID, "user", "Theo dõi giúp anh thư mục Inbox, gom ghi chú mới mỗi tuần.")


class Framer:
    max_wall_s = None

    def is_available(self):
        return True

    async def query(self, prompt):
        yield {"type": "final", "content": '{"understanding": "Gom ghi chú mới trong Inbox mỗi tuần", '
                                           '"criteria": [{"description": "Có bản gom", "evaluator": "artifact_contract", '
                                           '"params": {"path": "Inbox/gom.md"}}], "relevant_quote": "gom ghi chú mới", '
                                           '"horizon": {"kind": "maintain"}}'}

_old_eng = main._resonance_engine
main._resonance_engine = lambda s, t="resonance": (Framer(), {"provider": "fake", "text_only": True})
try:
    code, body = api("post", "/goal-requests", json={"message_ref": R.message_ref(SID, mid_u)})
    code2, body2 = api("post", "/goal-requests", json={"message_ref": R.message_ref(SID, mid_u)})
finally:
    main._resonance_engine = _old_eng
check("goal-requests: lập mục tiêu từ tin của người dùng (một lượt bộ lập mục tiêu)",
      code == 200 and body["goal"]["understanding"] == "Gom ghi chú mới trong Inbox mỗi tuần")
check("goal-requests: cùng tin gửi lại trả đúng mục tiêu cũ", code2 == 200 and body2["goal"]["goal_id"] == body["goal"]["goal_id"])
mid_a = main.get_store().append_message(SID, "assistant", "Đây là câu trả lời của Javis.")
code, body = api("post", "/goal-requests", json={"message_ref": R.message_ref(SID, mid_a)})
check("goal-requests: tin của trợ lý không lập được mục tiêu", code == 400)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
