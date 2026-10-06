"""Resonance M2: phân luồng bốn nhánh, tự hình thành mục tiêu, kho SQLite có revision.

    python tests/run.py resonance_mvp_core -v

Không gọi model thật: engine giả cho đường framer. Bộ não quyết định tạo hay nối mục tiêu bằng
tool `javis_goal` ngay trong lượt chat; route_request chỉ ĐỌC những gì lượt đó đã thật sự làm
(sự kiện trong kho mục tiêu, việc Kanban đã giao), không gọi thêm model, không dò từ khoá.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m2-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except Exception as e:  # noqa: BLE001
        print(f"     (ném sai loại: {type(e).__name__}: {e})")
        return False
    return False


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a-")).resolve())
OTHER = str(Path(tempfile.mkdtemp(prefix="brain-b-")).resolve())
OWNER = RS.Principal(kind="owner", id="owner", brain_id=BRAIN)
JAVIS = RS.Principal(kind="agent", id="javis", brain_id=BRAIN)
STRANGER = RS.Principal(kind="owner", id="owner", brain_id=OTHER)

USER_TEXT = ("Mỗi sáng gom giúp anh các việc đang dở thành một ghi chú trong Dashboard, "
             "làm tới hết tuần này rồi báo anh.")


def proposal(**kw):
    p = {
        "understanding": "Một ghi chú tổng hợp việc đang dở, cập nhật mỗi sáng",
        "criteria": [
            {"description": "Ghi chú tổng hợp tồn tại và có danh sách việc", "evaluator": "artifact_contract",
             "params": {"path": "00 - Dashboard/viec-dang-do.md", "min_chars": 50}},
            {"description": "Anh xác nhận ghi chú dùng được", "evaluator": "human_confirmation", "params": {}},
        ],
        "relevant_quote": "gom giúp anh các việc đang dở thành một ghi chú",
        "horizon": {"kind": "deadline", "at_iso": "2026-10-11T23:00:00+07:00", "from_user": True,
                    "quote": "hết tuần này"},
        "stage": "delivery",
        "mode": "maintain",
        "assumptions": ["Dashboard là thư mục 00 - Dashboard"],
        "constraints": [],
        "targets": [],
        "open_questions": [],
    }
    p.update(kw)
    return p


store = RS.GoalStore(Path(_STATE) / "resonance.sqlite3")

# ───────────────────────────── luật SMART của host ─────────────────────────────

# test_ambiguous_goal_smart
fr = R.validate_proposal(proposal(), USER_TEXT)
check("SMART: đề xuất đủ M và T được nhận", fr["stage"] == "delivery" and len(fr["criteria"]) == 2)
check("SMART: tiêu chí có id ổn định", [c["id"] for c in fr["criteria"]] == ["c1", "c2"])
fr_amb = R.validate_proposal(proposal(understanding="", stage="delivery"), USER_TEXT)
check("test_ambiguous_goal_smart: chưa rõ kết quả (thiếu S) thì về stage discovery", fr_amb["stage"] == "discovery")
check("SMART: thiếu M (không tiêu chí kiểm được) bị từ chối",
      raises(R.GoalRejected, lambda: R.validate_proposal(proposal(criteria=[]), USER_TEXT)))
check("SMART: evaluator lạ bị loại, còn lại vẫn giữ",
      [c["evaluator"] for c in R.validate_proposal(proposal(criteria=[
          {"description": "chấm bằng model", "evaluator": "rubric", "params": {}},
          {"description": "anh xác nhận", "evaluator": "human_confirmation", "params": {}}]), USER_TEXT)["criteria"]]
      == ["human_confirmation"])
check("SMART: thiếu T bị từ chối",
      raises(R.GoalRejected, lambda: R.validate_proposal(proposal(horizon={}), USER_TEXT)))

# R: căn cứ phải nằm trong lời người dùng (chặn mục tiêu do agent tự nghĩ ra)
check("test_proposed_plan_does_not_schedule: câu căn cứ không có trong lời người dùng thì từ chối",
      raises(R.GoalRejected, lambda: R.validate_proposal(
          proposal(relevant_quote="em đề xuất tuần sau mình dọn wiki"), USER_TEXT)))
check("R: so khớp bỏ qua hoa thường và khoảng trắng thừa",
      R.validate_proposal(proposal(relevant_quote="  GOM giúp anh   các việc đang dở "), USER_TEXT)["stage"] == "delivery")

# test_no_invented_target_or_deadline
fr_dl = R.validate_proposal(proposal(), USER_TEXT)
check("hạn người dùng nêu (có trích dẫn) được giữ là deadline",
      fr_dl["horizon"]["kind"] == "deadline" and fr_dl["horizon"]["from_user"] is True)
fr_rv = R.validate_proposal(proposal(horizon={"kind": "deadline", "at_iso": "2026-10-20T09:00:00+07:00",
                                              "from_user": True, "quote": "trước thứ Hai tuần sau"}), USER_TEXT)
check("test_no_invented_target_or_deadline: hạn không trích được từ lời người dùng thành mốc xem lại",
      fr_rv["horizon"]["kind"] == "review" and fr_rv["horizon"]["from_user"] is False)
fr_tg = R.validate_proposal(proposal(targets=[{"text": "giảm 30% việc tồn", "quote": "giảm 30%"}]), USER_TEXT)
check("chỉ tiêu không có căn cứ trong lời người dùng không thành chỉ tiêu",
      fr_tg["targets"] == [] and any("giảm 30% việc tồn" in a for a in fr_tg["assumptions"]))
fr_tg2 = R.validate_proposal(proposal(targets=[{"text": "hết tuần này", "quote": "hết tuần này"}]), USER_TEXT)
check("chỉ tiêu có căn cứ thì giữ", [t["text"] for t in fr_tg2["targets"]] == ["hết tuần này"])

# test_user_unsure_discovers
fr_un = R.validate_proposal(proposal(understanding="", open_questions=["Anh muốn gom từ những nguồn nào?"]),
                            USER_TEXT, user_unsure=True)
check("test_user_unsure_discovers: người dùng chưa rõ thì vẫn lập mục tiêu khám phá",
      fr_un["stage"] == "discovery")
check("test_user_unsure_discovers: không hỏi lại câu người dùng đã nói chưa biết", fr_un["open_questions"] == [])
check("test_user_unsure_discovers: ghi lại giả định thay cho câu hỏi",
      any("chưa rõ" in a for a in fr_un["assumptions"]))

# ───────────────────────────── kho mục tiêu ─────────────────────────────

it = store.add_intent(OWNER, session_id="s1", message_id=11, text=USER_TEXT, constraints=("không xoá ghi chú cũ",))
check("intent giữ nguyên lời người dùng", it["text"] == USER_TEXT and it["constraints"] == ["không xoá ghi chú cũ"])
frame = R.validate_proposal(proposal(constraints=["không xoá ghi chú cũ"]), USER_TEXT)
g, created = store.create(JAVIS, it["id"], frame, idempotency_key="msg:s1:11", session_id="s1",
                          output_root=str(Path(BRAIN) / "Javis" / "resonance" / "x"), budget_calls=6)
check("tạo mục tiêu: revision 1, active, không cần duyệt", created and g.revision == 1 and g.status == "active")
check("tạo mục tiêu: GoalRecord mang khung SMART", g.understanding.startswith("Một ghi chú")
      and len(g.criteria) == 2 and g.horizon["kind"] == "deadline")

# test_persistent_request_creates_once
g2, created2 = store.create(JAVIS, it["id"], frame, idempotency_key="msg:s1:11", session_id="s1",
                            output_root="khac", budget_calls=99)
check("test_persistent_request_creates_once: cùng tin nhắn không tạo mục tiêu thứ hai",
      not created2 and g2.id == g.id and g2.budget_calls == 6)
check("test_persistent_request_creates_once: chỉ một sự kiện created",
      [e["kind"] for e in store.events(OWNER, g.id)].count("created") == 1)

# cross-brain
check("brain khác không đọc được mục tiêu", store.get(STRANGER, g.id) is None)
check("brain khác không sửa được mục tiêu", raises(RS.ScopeError, lambda: store.revise(
    STRANGER, g.id, 1, frame, reason="x")))
check("brain khác không liệt kê được", store.list_open(STRANGER) == [])
check("liệt kê mục tiêu mở theo phiên", [x.id for x in store.list_open(OWNER, session_id="s1")] == [g.id])

# revise: expected_revision, giữ quyền/ngân sách/pause/ràng buộc
store.set_paused(OWNER, g.id, True)
store.add_calls_used(OWNER, g.id, 2)
fr2 = R.validate_proposal(proposal(understanding="Ghi chú tổng hợp có cả lịch tuần",
                                   constraints=["không xoá ghi chú cũ"]), USER_TEXT)
g3 = store.revise(JAVIS, g.id, 1, fr2, reason="anh nói thêm lịch tuần", intent_id=it["id"])
check("revise: lên revision 2 với cách hiểu mới", g3.revision == 2 and "lịch tuần" in g3.understanding)
check("revise: giữ pause, ngân sách, số lượt đã dùng", g3.paused is True and g3.budget_calls == 6 and g3.calls_used == 2)
check("revise: revision cũ còn nguyên", store.get_revision(OWNER, g.id, 1)["understanding"].startswith("Một ghi chú"))
check("revise: expected_revision cũ thì xung đột, không đổi gì",
      raises(RS.ConflictError, lambda: store.revise(JAVIS, g.id, 1, fr2, reason="x"))
      and store.get(OWNER, g.id).revision == 2)
check("revise: agent không được bỏ ràng buộc người dùng đã nêu",
      raises(R.GoalRejected, lambda: store.revise(JAVIS, g.id, 2, R.validate_proposal(proposal(), USER_TEXT),
                                                  reason="bỏ ràng buộc")))
check("revise: sự kiện reframe ghi diff", any(e["kind"] == "reframe" and "understanding" in e["payload"].get("diff", {})
                                             for e in store.events(OWNER, g.id)))

# sự kiện: chống trùng theo khoá
e1 = store.append_event(OWNER, g.id, "note", {"x": 1}, idempotency_key="k1")
e2 = store.append_event(OWNER, g.id, "note", {"x": 1}, idempotency_key="k1")
check("sự kiện cùng khoá chỉ ghi một lần", e1 == e2)

# outbox ghi cùng giao dịch với tạo / sửa
ob = store.outbox_pending()
check("outbox có goal.created và goal.revised", [o["kind"] for o in ob if o["goal_id"] == g.id] ==
      ["goal.created", "goal.revised"])

# giao dịch: lỗi giữa chừng không để lại mục tiêu nửa vời
n_before = len(store.list_open(OWNER))
check("tạo với intent không tồn tại bị từ chối", raises(RS.ScopeError, lambda: store.create(
    JAVIS, "in_khong_co", frame, idempotency_key="msg:s1:99", session_id="s1", output_root="x")))
check("không để lại mục tiêu nửa vời", len(store.list_open(OWNER)) == n_before)

# ───────────────────────────── route_request ─────────────────────────────

t0 = time.time() - 1
MSG = "msg:s1:11"

# test_chat_does_not_create_goal
d = R.route_request("msg:s1:50", {"goal_events": [], "tasks_created": 0, "reminders_created": 0,
                                  "open_goal_ids": [g.id]})
check("test_chat_does_not_create_goal: lượt không gọi tool mục tiêu là answer_now", d.kind == "answer_now")
check("test_chat_does_not_create_goal: có mục tiêu mở cũng KHÔNG tự nối vào", d.goal_id is None)

# test_inline_job_stays_inline
d = R.route_request("msg:s1:51", {"goal_events": [], "tasks_created": 0, "reminders_created": 0,
                                  "files_written": 2})
check("test_inline_job_stays_inline: làm xong trong lượt (có ghi file) vẫn là answer_now",
      d.kind == "answer_now" and d.reason == "inline")

# task_now
d = R.route_request("msg:s1:52", {"goal_events": [], "tasks_created": 1, "reminders_created": 0})
check("giao một việc Kanban là task_now", d.kind == "task_now")
d = R.route_request("msg:s1:53", {"goal_events": [], "tasks_created": 0, "reminders_created": 1})
check("hẹn giờ đơn giản đi đường reminder, là task_now", d.kind == "task_now" and d.reason == "reminder")

# create / continue
d = R.route_request(MSG, {"goal_events": [{"goal_id": g.id, "kind": "created", "message_ref": MSG}]})
check("lượt tạo mục tiêu là create_goal", d.kind == "create_goal" and d.goal_id == g.id)
d = R.route_request("msg:s1:60", {"goal_events": [{"goal_id": g.id, "kind": "reframe", "message_ref": "msg:s1:60"}]})
check("test_followup_reuses_goal: lượt sửa mục tiêu đang mở là continue_goal", d.kind == "continue_goal"
      and d.goal_id == g.id)
d = R.route_request("msg:s1:61", {"goal_events": [{"goal_id": g.id, "kind": "reframe", "message_ref": "msg:s1:60"}]})
check("sự kiện của tin khác không được tính cho tin này", d.kind == "answer_now")

# ───────────────────────────── form_goal ─────────────────────────────


class FakeEngine:
    def __init__(self, events, available=True):
        self.events, self.available, self.queries = events, available, 0
        self.max_wall_s = None

    def is_available(self):
        return self.available

    async def query(self, prompt):
        self.queries += 1
        self.last_prompt = prompt
        for ev in self.events:
            yield ev


def deps_with(engine, calls=3, info=None):
    return R.GoalDeps(engine_factory=lambda s, t: (engine, dict(info or {"provider": "fake"})),
                      budget=R.CallBudget(calls), store=store)


def ctx(msg_id, text, **kw):
    c = {"principal": JAVIS, "brain_root": BRAIN, "session_id": "s2", "message_id": msg_id, "user_text": text,
         "constraints": [], "budget_calls": 4}
    c.update(kw)
    return c


# Đề xuất từ chính bộ não (tool javis_goal): KHÔNG gọi model thêm
eng0 = FakeEngine([])
dp0 = deps_with(eng0)
gp = asyncio.run(R.form_goal("msg:s2:1", ctx(1, USER_TEXT, proposal=proposal()), dp0))
check("form_goal với đề xuất của bộ não: tạo mục tiêu", gp.revision == 1 and gp.status == "active")
check("form_goal với đề xuất: không gọi model, không tốn lượt", eng0.queries == 0 and dp0.budget.used == 0)
check("form_goal: vùng đầu ra nằm trong brain, theo id mục tiêu",
      Path(gp.output_root).resolve().is_relative_to(Path(BRAIN)) and gp.id in gp.output_root)
gp2 = asyncio.run(R.form_goal("msg:s2:1", ctx(1, USER_TEXT, proposal=proposal()), dp0))
check("form_goal cùng tin nhắn hai lần: một mục tiêu", gp2.id == gp.id)

# Không có đề xuất: framer gọi engine một lượt chỉ chữ
eng1 = FakeEngine([{"type": "final", "content": "```json\n" + json.dumps(proposal(), ensure_ascii=False) + "\n```",
                    "tokens_in": 300, "tokens_out": 120}])
dp1 = deps_with(eng1)
gf = asyncio.run(R.form_goal("msg:s2:2", ctx(2, USER_TEXT), dp1))
check("form_goal không có đề xuất: framer tạo được mục tiêu", gf.revision == 1 and gf.id != gp.id)
check("form_goal framer: gọi model đúng một lượt", eng1.queries == 1 and dp1.budget.used == 1)
check("form_goal framer: prompt chứa lời người dùng như DỮ LIỆU", USER_TEXT in eng1.last_prompt
      and "<<<" in eng1.last_prompt)

eng2 = FakeEngine([{"type": "final", "content": "không phải json"}])
dp2 = deps_with(eng2)
check("form_goal framer trả rác: từ chối, không tạo mục tiêu",
      raises(R.GoalRejected, lambda: asyncio.run(R.form_goal("msg:s2:3", ctx(3, USER_TEXT), dp2))))
check("form_goal framer trả rác: model đã gọi nên tính một lượt", dp2.budget.used == 1)
check("form_goal framer trả rác: không có mục tiêu cho tin đó",
      not any(x.request_ref == "msg:s2:3" for x in store.list_open(OWNER)))

dp3 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "engine không chỉ chữ"}), budget=R.CallBudget(1),
                 store=store)
check("form_goal engine bị chặn: từ chối, trả lại lượt",
      raises(R.GoalRejected, lambda: asyncio.run(R.form_goal("msg:s2:4", ctx(4, USER_TEXT), dp3)))
      and dp3.budget.used == 0)

# Người dùng nêu ràng buộc: mục tiêu mang theo, đề xuất không được bỏ
gc = asyncio.run(R.form_goal("msg:s2:5", ctx(5, USER_TEXT, constraints=["không gửi tin cho ai"],
                                             proposal=proposal(constraints=[])), dp0))
check("ràng buộc của người dùng luôn nằm trong mục tiêu", "không gửi tin cho ai" in gc.constraints)

# ───────────────────────────── công tắc theo brain ─────────────────────────────
check("Resonance mặc định tắt", R.enabled_for(BRAIN) is False)
(Path(BRAIN) / "Javis").mkdir(parents=True, exist_ok=True)
(Path(BRAIN) / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
check("bật bằng Javis/resonance.json của đúng brain", R.enabled_for(BRAIN) is True and R.enabled_for(OTHER) is False)
(Path(BRAIN) / "Javis" / "resonance.json").write_text("{hỏng", encoding="utf-8")
check("file công tắc hỏng thì coi như tắt", R.enabled_for(BRAIN) is False)

# kho mở lại vẫn còn dữ liệu (bền qua restart)
store2 = RS.GoalStore(Path(_STATE) / "resonance.sqlite3")
check("mở lại kho: mục tiêu và revision còn nguyên", store2.get(OWNER, g.id).revision == 2)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
