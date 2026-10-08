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
code, body = api("post", "/goals/g_khong_co/feedback", json={"kind": "goal_fit_confirmed", "expected_revision": 1})
check("brain chưa bật Resonance: phản hồi trả 403", code == 403)
code, body = api("post", "/goal-requests", json={"message_ref": "msg:x:1"})
check("brain chưa bật Resonance: lập mục tiêu mới trả 403", code == 403)
code, body = api("get", "/goals/g_khong_co")
check("brain chưa bật Resonance: xem mục tiêu không có trả 404, không lộ gì", code == 404)
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

# ───────────── đường có thẩm quyền: người dùng bỏ chỉ dẫn của mình trên thẻ (M4) ─────────────
USER_D = "Gom giúp mình ghi chú việc tuần đến ngày 20/10/2026, cần đủ 5 việc, không xoá ghi chú cũ."
mid_d = main.get_store().append_message(SID, "user", USER_D)
keep.write_text("giữ\n", encoding="utf-8")
gd = asyncio.run(R.form_goal(R.message_ref(SID, mid_d), {
    "principal": P, "brain_root": KEY, "session_id": SID, "message_id": mid_d, "user_text": USER_D,
    "constraints": ["không xoá ghi chú cũ"], "budget_calls": 4, "proposal": {
        "understanding": "Ghi chú việc tuần", "relevant_quote": "Gom giúp mình ghi chú việc tuần",
        "criteria": [{"description": "Có ghi chú", "evaluator": "artifact_contract", "params": {"path": "Inbox/tuan.md"}}],
        "horizon": {"kind": "deadline", "at_iso": "2026-10-20T23:00:00+07:00", "from_user": True,
                    "quote": "đến ngày 20/10/2026"},
        "targets": [{"text": "5 việc", "quote": "cần đủ 5 việc"}], "constraints": ["không xoá ghi chú cũ"],
        "guards": [{"description": "Ghi chú giữ còn", "evaluator": "artifact_contract", "params": {"path": "Notes/giu.md"}}],
        "stage": "delivery"}}, R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=store)))
vd = api("get", f"/goals/{gd.id}")[1]["goal"]
check("thẻ liệt kê chỉ dẫn người dùng bỏ được: hạn, chỉ tiêu, ràng buộc, guard",
      sorted(d["field"] for d in vd["directives"]) == ["constraint", "deadline", "guard", "target"])
code, body = api("post", f"/goals/{gd.id}/commands", json={"command": "drop_directive", "field": "target",
                                                            "key": "5 việc", "expected_revision": 0})
check("bỏ chỉ dẫn từ thẻ cũ (sai revision): 409, không đổi gì", code == 409 and store.get(P, gd.id).revision == 1)
check("agent không tự bỏ được chỉ dẫn người dùng",
      _perm(lambda: store.drop_directive(P, gd.id, 1, "target", "5 việc")))
code, body = api("post", f"/goals/{gd.id}/commands", json={"command": "drop_directive", "field": "target",
                                                            "key": "5 việc", "expected_revision": 1})
gd2 = store.get(P, gd.id)
ev = [e for e in store.events(P, gd.id) if e["kind"] == "reframe"][-1]
check("bỏ chỉ tiêu: revision mới, chỉ tiêu mất, sự kiện ghi nguồn là người dùng và quan hệ replace",
      code == 200 and gd2.revision == 2 and gd2.targets == () and ev["source"] == "owner"
      and ev["payload"].get("relation") == "replace" and ev["by"].startswith("owner"))
api("post", f"/goals/{gd.id}/commands", json={"command": "drop_directive", "field": "deadline", "key": "",
                                               "expected_revision": 2})
check("bỏ hạn chót: chân trời thành mốc xem lại, không còn là hạn của người dùng",
      store.get(P, gd.id).horizon["kind"] == "review" and store.get(P, gd.id).horizon["from_user"] is False)
api("post", f"/goals/{gd.id}/commands", json={"command": "drop_directive", "field": "constraint",
                                               "key": "không xoá ghi chú cũ", "expected_revision": 3})
check("bỏ ràng buộc: ràng buộc mất khỏi khung và khỏi danh sách ràng buộc người dùng của kho",
      store.get(P, gd.id).constraints == () and store.get(P, gd.id).revision == 4)
g_after, _, _ = R.revise_goal(store, P, gd.id, 4, {"relevant_quote": "Gom giúp mình", "understanding": "Ghi chú việc tuần gọn"},
                              {"message_ref": R.message_ref(SID, 9100), "session_id": SID, "message_id": 9100,
                               "user_text": USER_D})
check("sau khi người dùng bỏ ràng buộc, bộ não cập nhật cách hiểu mà không bị kho đòi lại ràng buộc đó",
      g_after.revision == 5 and g_after.constraints == ())
keep.unlink()
asyncio.run(R.advance(gd.id, {"kind": "wake"}, deps(Eng())))
check("guard nhảy thì mục tiêu dừng", store.run_state(P, gd.id)["block_reason"] == "guard")
code, body = api("post", f"/goals/{gd.id}/commands", json={"command": "drop_directive", "field": "guard",
                                                            "key": "gd1", "expected_revision": 5})
check("người dùng bỏ guard đang chặn: mở chặn, có lịch làm tiếp, guard mất khỏi khung",
      code == 200 and store.run_state(P, gd.id)["block_reason"] == "" and store.get(P, gd.id).guards == ()
      and any(w["kind"] == "work" for w in store.wakes(P, gd.id)))
code, body = api("post", f"/goals/{gd.id}/commands", json={"command": "drop_directive", "field": "target",
                                                            "key": "không có", "expected_revision": 6})
check("bỏ chỉ dẫn không tồn tại: 400", code == 400)

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

# ───────────── Review M4 vòng 1: năm lỗi, nay là hành vi mong đợi ─────────────
import hashlib  # noqa: E402
import json  # noqa: E402
from contextlib import closing  # noqa: E402

DELIV = Path(KEY) / "Inbox" / "ke-hoach.md"


def _sha_file(f):
    return hashlib.sha256(f.read_bytes()).hexdigest()


# P1-1: artifact_ref là bytes của file người dùng đang xem, không phải hash trong receipt.
g9 = make_goal()
e9 = Eng()
asyncio.run(R.advance(g9.id, {"kind": "start"}, deps(e9)))
v9 = api("get", f"/goals/{g9.id}")[1]["goal"]
check("P1-1: artifact_ref trên thẻ đúng bằng sha256 bytes hiện tại của file sản phẩm",
      v9["artifact_ref"] == _sha_file(DELIV))
code, _ = api("post", f"/goals/{g9.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                         "criterion_id": v9["criteria"][1]["id"],
                                                         "artifact_ref": v9["artifact_ref"]})
DELIV.write_text(GOOD + "\nSửa tay sau khi duyệt, chưa ai duyệt bản này.\n", encoding="utf-8", newline="\n")
v9b = api("get", f"/goals/{g9.id}")[1]["goal"]
asyncio.run(R.advance(g9.id, {"kind": "wake"}, deps(e9)))
check("P1-1: file đổi sau khi duyệt thì thẻ đổi artifact_ref, xác nhận cũ thành unknown, mục tiêu KHÔNG thành công",
      code == 200 and v9b["artifact_ref"] == _sha_file(DELIV) != v9["artifact_ref"]
      and v9b["criteria"][1]["verdict"] == "unknown" and store.get(P, g9.id).status == "active")

g10 = make_goal()
asyncio.run(R.advance(g10.id, {"kind": "start"}, deps(Eng())))
v10 = api("get", f"/goals/{g10.id}")[1]["goal"]
DELIV.write_text(GOOD + "\nBản thay thế chưa duyệt.\n", encoding="utf-8", newline="\n")
code, body = api("post", f"/goals/{g10.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                             "criterion_id": v10["criteria"][1]["id"],
                                                             "artifact_ref": v10["artifact_ref"]})
check("P1-1: thẻ cũ (bản trước khi file đổi) bấm Đạt yêu cầu: 409, trả artifact_ref mới, không ghi xác nhận",
      code == 409 and body.get("goal", {}).get("artifact_ref") == _sha_file(DELIV)
      and not store.confirmation(OWNER, g10.id, 1, v10["criteria"][1]["id"]))
code, _ = api("post", f"/goals/{g10.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 1,
                                                          "criterion_id": v10["criteria"][1]["id"],
                                                          "artifact_ref": body["goal"]["artifact_ref"]})
asyncio.run(R.advance(g10.id, {"kind": "wake"}, deps(Eng())))
check("P1-1: duyệt đúng bản đang có trên đĩa thì kết luận thành công",
      code == 200 and store.get(P, g10.id).status == "succeeded")

g11 = make_goal()
asyncio.run(R.advance(g11.id, {"kind": "start"}, deps(Eng())))
R.revise_goal(store, P, g11.id, 1, {"relevant_quote": "Anh sẽ duyệt", "understanding": "Ghi chú kế hoạch bản hai"},
              {"message_ref": R.message_ref(SID, 9201), "session_id": SID, "message_id": 9201, "user_text": USER})
v11 = api("get", f"/goals/{g11.id}")[1]["goal"]
code, _ = api("post", f"/goals/{g11.id}/feedback", json={"kind": "outcome_accepted", "expected_revision": 2,
                                                          "criterion_id": v11["criteria"][1]["id"],
                                                          "artifact_ref": _sha_file(DELIV)})
check("P1-1: revision mới chưa có lượt làm thì không có bản để duyệt (file trên đĩa là của cách hiểu cũ)",
      v11["artifact_ref"] == "" and code == 400)

# P1-2: mỗi lần bấm một khoá; gửi lại cùng khoá mới là trùng.
g12 = make_goal()
for i, kind in enumerate(("goal_fit_rejected", "goal_fit_confirmed", "goal_fit_rejected")):
    code, body = api("post", f"/goals/{g12.id}/feedback", json={"kind": kind, "expected_revision": 1,
                                                                 "idempotency_key": f"{g12.id}:1:click{i}"})
check("P1-2: Chưa đúng ý -> Đúng ý -> Chưa đúng ý: lần bấm cuối được ghi, trạng thái là Chưa đúng ý",
      code == 200 and not body.get("duplicate") and store.fit_status(OWNER, g12.id, 1) == "rejected")
code, body = api("post", f"/goals/{g12.id}/feedback", json={"kind": "goal_fit_rejected", "expected_revision": 1,
                                                             "idempotency_key": f"{g12.id}:1:click2"})
check("P1-2: gửi lại đúng lần bấm cuối (mạng chập chờn): trùng, không ghi lần hai",
      body.get("duplicate") is True and store.fit_status(OWNER, g12.id, 1) == "rejected")
g12b = make_goal()
for i, kind in enumerate(("goal_fit_confirmed", "goal_fit_rejected", "goal_fit_confirmed")):
    api("post", f"/goals/{g12b.id}/feedback", json={"kind": kind, "expected_revision": 1,
                                                     "idempotency_key": f"{g12b.id}:1:click{i}"})
check("P1-2: thứ tự ngược lại (Đúng ý -> Chưa đúng ý -> Đúng ý) cũng lấy đúng lần bấm cuối",
      store.fit_status(OWNER, g12b.id, 1) == "confirmed")

# P1-3: id guard không tái dùng sau khi bỏ; dữ liệu cũ id trùng thì từ chối, không xoá cả hai.
GS = [{"description": "Giữ ghi chú một", "evaluator": "artifact_contract", "params": {"path": "Notes/mot.md"}},
      {"description": "Giữ ghi chú hai", "evaluator": "artifact_contract", "params": {"path": "Notes/hai.md"}}]
g13 = make_goal(guards=GS)
check("P1-3: guard đầu tiên cấp gd1, gd2", [x["id"] for x in store.get(P, g13.id).guards] == ["gd1", "gd2"])
code, _ = api("post", f"/goals/{g13.id}/commands", json={"command": "drop_directive", "field": "guard", "key": "gd1",
                                                          "expected_revision": 1})
cur = store.get(P, g13.id)
R.revise_goal(store, P, g13.id, cur.revision,
              {"relevant_quote": "Anh sẽ duyệt", "guards": [dict(x) for x in cur.guards] + [
                  {"description": "Giữ ghi chú ba", "evaluator": "artifact_contract", "params": {"path": "Notes/ba.md"}}]},
              {"message_ref": R.message_ref(SID, 9202), "session_id": SID, "message_id": 9202, "user_text": USER})
ids = [x["id"] for x in store.get(P, g13.id).guards]
check("P1-3: bỏ gd1 rồi thêm guard mới: id mới là gd3, không trùng gd2", code == 200 and ids == ["gd2", "gd3"])
cur = store.get(P, g13.id)
code, _ = api("post", f"/goals/{g13.id}/commands", json={"command": "drop_directive", "field": "guard", "key": "gd3",
                                                          "expected_revision": cur.revision})
check("P1-3: bỏ gd3 chỉ bỏ đúng gd3", code == 200 and [x["id"] for x in store.get(P, g13.id).guards] == ["gd2"])
cur = store.get(P, g13.id)
with closing(store._conn()) as c:
    row = c.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=? AND revision=?", (g13.id, cur.revision)).fetchone()
    fr = json.loads(row["frame_json"])
    fr["guards"] = [dict(fr["guards"][0]), {**fr["guards"][0], "description": "Bản ghi cũ cùng id"}]
    c.execute("UPDATE goal_revisions SET frame_json=? WHERE goal_id=? AND revision=?",
              (json.dumps(fr, ensure_ascii=False), g13.id, cur.revision))
code, _ = api("post", f"/goals/{g13.id}/commands", json={"command": "drop_directive", "field": "guard", "key": "gd2",
                                                          "expected_revision": cur.revision})
check("P1-3: dữ liệu cũ có hai guard cùng id: lệnh bỏ bị từ chối (400), không xoá mục nào",
      code == 400 and len(store.get(P, g13.id).guards) == 2 and store.get(P, g13.id).revision == cur.revision)

# P2-1: tắt Resonance không chặn người dùng xem, tạm dừng, huỷ.
g14 = make_goal()
g15 = make_goal()
api("post", "/resonance/settings", json={"enabled": False})
code_get, _ = api("get", f"/goals/{g14.id}")
code_list, _ = api("get", "/resonance/goals")
code_p, body_p = api("post", f"/goals/{g14.id}/commands", json={"command": "pause", "expected_revision": 1})
code_c, body_c = api("post", f"/goals/{g15.id}/commands", json={"command": "cancel", "expected_revision": 1})
code_f, _ = api("post", f"/goals/{g14.id}/feedback", json={"kind": "goal_fit_confirmed", "expected_revision": 1})
e14 = Eng()
asyncio.run(R.advance(g14.id, {"kind": "wake"}, deps(e14)))
check("P2-1: Resonance tắt: xem thẻ và danh sách vẫn được (200)", code_get == 200 and code_list == 200)
check("P2-1: Resonance tắt: Tạm dừng và Huỷ vẫn có hiệu lực",
      code_p == 200 and store.get(P, g14.id).paused and code_c == 200 and store.get(P, g15.id).status == "cancelled")
check("P2-1: Resonance tắt: phản hồi vẫn 403, và mục tiêu không chạy", code_f == 403 and e14.queries == 0)
api("post", "/resonance/settings", json={"enabled": True})
asyncio.run(R.advance(g14.id, {"kind": "wake"}, deps(e14)))
check("P2-1: bật lại: mục tiêu đã tạm dừng vẫn đứng yên, mục tiêu đã huỷ vẫn huỷ",
      e14.queries == 0 and store.get(P, g14.id).paused and store.get(P, g15.id).status == "cancelled")

# P2-2: khoá báo cáo tìm trên toàn bộ phiên, không giới hạn 300 tin.
import dataclasses  # noqa: E402
g16 = make_goal()
SID2 = main.get_store().get_or_create(None, brain=BRAIN, engine="test", model="test")
store.notice(P, g16.id, "goal.blocked", {"code": "budget"}, idem="review-p22")
row16 = [r for r in store.outbox_pending(500) if r["goal_id"] == g16.id and r["kind"] == "goal.blocked"][0]
key16 = f"outbox:{row16['id']}"
asyncio.run(main.push_to_chat(SID2, "Đã báo", card=R.goal_block(g16.id, 1, report=key16)))
for i in range(350):
    main.get_store().append_message(SID2, "user", f"Tin sau {i}")
probe = dataclasses.replace(store.get(P, g16.id), session_id=SID2)
check("P2-2: báo cáo đã lưu, sau đó 350 tin khác: vẫn nhận ra là đã báo", main._resonance_reported(probe, key16))
check("P2-2: khoá báo cáo khác (chưa lưu) không bị nhận nhầm",
      not main._resonance_reported(probe, f"outbox:{row16['id'] + 100000}"))


async def _notify16(goal, kind, text, card=""):
    return await main.push_to_chat(SID2, text, card=card)


def _already16(goal, report_key):
    return main._resonance_reported(dataclasses.replace(goal, session_id=SID2), report_key)


asyncio.run(R.drain_outbox(store, _notify16, already=_already16))
copies = [m for m in main.get_store().get_messages(SID2)
          if any(b.get("report") == key16 for b in R.parse_goal_blocks(m.get("content") or ""))]
check("P2-2: nhịp đối soát sau đó không gửi lại báo cáo cũ", len(copies) == 1 and not any(
    r["id"] == row16["id"] for r in store.outbox_pending(500)))

# ───────────── Review M4 vòng 2: chuỗi khoá trong lời chat không phải bằng chứng đã gửi ─────────────
# Bằng chứng duy nhất là biên nhận report_receipts do push_to_chat ghi cùng giao dịch với tin báo cáo.


def _pending_row(goal, idem):
    store.notice(P, goal.id, "goal.blocked", {"code": "budget"}, idem=idem)
    return [r for r in store.outbox_pending(500) if r["goal_id"] == goal.id and r["kind"] == "goal.blocked"][0]


def _drain_into(sid):
    sent_kinds = []

    async def _n(goal, kind, text, card=""):
        sent_kinds.append(kind)
        return await main.push_to_chat(sid, text, card=card)

    asyncio.run(R.drain_outbox(store, _n, already=lambda goal, k: main._resonance_reported(
        dataclasses.replace(goal, session_id=sid), k)))
    return sent_kinds


def _real_reports(sid, key):
    return [m for m in main.get_store().get_messages(sid) if m["role"] == "assistant"
            and any(b.get("report") == key for b in R.parse_goal_blocks(m.get("content") or ""))]


# 1. Lời chat thường trích JSON cùng khoá, không có khối báo cáo.
g17 = make_goal()
S17 = main.get_store().get_or_create(None, brain=BRAIN, engine="test", model="test")
row17 = _pending_row(g17, "r2-quote")
key17 = f"outbox:{row17['id']}"
main.get_store().append_message(S17, "assistant", "Ví dụ trường JSON: " + json.dumps({"report": key17}))
p17 = dataclasses.replace(store.get(P, g17.id), session_id=S17)
check("vòng 2: lời chat trích JSON cùng khoá KHÔNG tính là đã gửi", main._resonance_reported(p17, key17) is False)
k17 = _drain_into(S17)
check("vòng 2: drain vẫn gửi và lưu báo cáo thật, đánh dấu đúng dòng outbox",
      k17 == ["goal.blocked"] and len(_real_reports(S17, key17)) == 1
      and not any(r["id"] == row17["id"] for r in store.outbox_pending(500)))
check("vòng 2: báo cáo thật vừa gửi có biên nhận, nhịp sau nhận ra là đã gửi", main._resonance_reported(p17, key17))

# 2. Khối hỏng, khoá khác, khối của mục tiêu khác, và cả một khối hợp lệ do model tự viết (không qua host).
g18 = make_goal()
g18b = make_goal()
S18 = main.get_store().get_or_create(None, brain=BRAIN, engine="test", model="test")
row18 = _pending_row(g18, "r2-neg")
key18 = f"outbox:{row18['id']}"
for txt in ('<!-- JAVIS_RESONANCE: {"goal_id": "' + g18.id + '", "report": "' + key18 + '", -->',
            R.goal_block(g18.id, 1, report=key18 + "9"),
            R.goal_block(g18b.id, 1, report=key18),
            "Model chép lại tin cũ:\n" + R.goal_block(g18.id, 1, report=key18)):
    main.get_store().append_message(S18, "assistant", txt)
asyncio.run(main.push_to_chat(S18, "Báo của mục tiêu khác", card=R.goal_block(g18b.id, 1, report=key18)))
p18 = dataclasses.replace(store.get(P, g18.id), session_id=S18)
check("vòng 2: khối hỏng, khoá khác, khối của mục tiêu khác, khối model tự viết: không cái nào tính là đã gửi",
      main._resonance_reported(p18, key18) is False)
check("vòng 2: kho phiên tra biên nhận theo đúng mục tiêu (cùng khoá, khác mục tiêu thì không trả)",
      main.get_store().report_receipt(S18, key18, g18.id) is None
      and main.get_store().report_receipt(S18, key18, g18b.id) is not None)
check("vòng 2: biên nhận gắn đúng mục tiêu: mục tiêu kia là đã gửi, mục tiêu này thì không",
      main._resonance_reported(dataclasses.replace(store.get(P, g18b.id), session_id=S18), key18) is True)
k18 = _drain_into(S18)
check("vòng 2: sau các ca âm, drain vẫn gửi báo cáo thật cho đúng mục tiêu, có biên nhận riêng của mục tiêu này",
      "goal.blocked" in k18 and main._resonance_reported(p18, key18) is True)

# 3. Tin thường có chuỗi trùng nằm TRƯỚC tin báo cáo thật: vẫn nhận ra tin thật, không phát lại.
g19 = make_goal()
S19 = main.get_store().get_or_create(None, brain=BRAIN, engine="test", model="test")
row19 = _pending_row(g19, "r2-before")
key19 = f"outbox:{row19['id']}"
main.get_store().append_message(S19, "assistant", "Nhật ký: " + json.dumps({"report": key19}))
asyncio.run(main.push_to_chat(S19, "Đã báo", card=R.goal_block(g19.id, 1, report=key19)))
for i in range(320):
    main.get_store().append_message(S19, "user", f"Tin sau {i}")
k19 = _drain_into(S19)
check("vòng 2: chuỗi trùng đứng trước tin thật, thêm 320 tin sau: nhận ra tin thật, không gửi lại",
      k19 == [] and len(_real_reports(S19, key19)) == 1
      and not any(r["id"] == row19["id"] for r in store.outbox_pending(500)))

# ───────────── Review e2e P1-1: trần chung tính cả bộ lập mục tiêu (POST /goal-requests) ─────────────
import sqlite3 as _sq  # noqa: E402
import threading  # noqa: E402


def _total_calls():
    c = _sq.connect(str(main._resonance_store().path))
    v = int(c.execute("SELECT COALESCE(SUM(calls_used),0) FROM goals").fetchone()[0])
    v += int(c.execute("SELECT COUNT(*) FROM call_ledger WHERE status='used'").fetchone()[0])
    c.close()
    return v


class CountFramer(Framer):
    def __init__(self, fail=False):
        self.queries, self.fail = 0, fail

    async def query(self, prompt):
        self.queries += 1
        if self.fail:
            yield {"type": "error", "content": "framer lỗi mô phỏng"}
            return
        async for ev in Framer.query(self, prompt):
            yield ev


def _req(text, framer=None, blocked=False):
    mid_x = main.get_store().append_message(SID, "user", text)
    old = main._resonance_engine
    main._resonance_engine = (lambda s_, t="resonance": (None, {"blocked": "chặn"})) if blocked else \
        (lambda s_, t="resonance": (framer, {"provider": "fake", "text_only": True}))
    try:
        return api("post", "/goal-requests", json={"message_ref": R.message_ref(SID, mid_x)})
    finally:
        main._resonance_engine = old


os.environ["JAVIS_RESONANCE_CALL_CEILING"] = "0"
f0 = CountFramer()
c0, _ = _req("Theo dõi giúp anh thư mục Inbox, gom ghi chú mới mỗi tuần (trần 0).", f0)
check("e2e P1-1: trần 0 chặn bộ lập mục tiêu TRƯỚC khi gọi engine", c0 == 400 and f0.queries == 0)
os.environ["JAVIS_RESONANCE_CALL_CEILING"] = str(_total_calls() + 1)
f1, f2 = CountFramer(), CountFramer()
c1, _ = _req("Theo dõi giúp anh thư mục Inbox, gom ghi chú mới mỗi tuần (lượt 1).", f1)
c2, _ = _req("Theo dõi giúp anh thư mục Inbox, gom ghi chú mới mỗi tuần (lượt 2).", f2)
check("e2e P1-1: trong trần gọi đúng một lần và được ghi vào sổ bền; lượt kế bị chặn trước khi gọi",
      c1 == 200 and f1.queries == 1 and c2 == 400 and f2.queries == 0)
main._RESONANCE_STORE = None          # mô phỏng khởi động lại: kho mở mới
f3 = CountFramer()
c3, _ = _req("Theo dõi giúp anh thư mục Inbox, gom ghi chú mới mỗi tuần (sau khởi động lại).", f3)
check("e2e P1-1: mở lại kho vẫn chặn bộ lập mục tiêu", c3 == 400 and f3.queries == 0)
os.environ["JAVIS_RESONANCE_CALL_CEILING"] = str(_total_calls() + 1)
before = _total_calls()
ff = CountFramer(fail=True)
cf, _ = _req("Theo dõi giúp anh thư mục Inbox, gom ghi chú mới mỗi tuần (framer lỗi).", ff)
check("e2e P1-1: framer đã gọi mà lỗi vẫn bị tính vào trần", cf == 400 and ff.queries == 1
      and _total_calls() == before + 1)
os.environ["JAVIS_RESONANCE_CALL_CEILING"] = str(_total_calls() + 1)
before = _total_calls()
cb, _ = _req("Theo dõi giúp anh thư mục Inbox, gom ghi chú mới mỗi tuần (engine bị chặn).", blocked=True)
check("e2e P1-1: engine bị chặn trước khi gọi thì hoàn chỗ trong sổ", cb == 400 and _total_calls() == before)
os.environ["JAVIS_RESONANCE_CALL_CEILING"] = str(_total_calls() + 1)
_st = main._resonance_store()
_got = []
_ths = [threading.Thread(target=lambda: _got.append(_st.reserve_ledger_call(P, "framer", "dong-thoi")))
        for _ in range(6)]
for t_ in _ths:
    t_.start()
for t_ in _ths:
    t_.join()
check("e2e P1-1: sáu yêu cầu giữ chỗ đồng thời với trần còn một: đúng một qua",
      len([x for x in _got if x is not None]) == 1)
del os.environ["JAVIS_RESONANCE_CALL_CEILING"]

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
