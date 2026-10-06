"""Resonance M2 (sửa sau hai vòng review PR #567): cập nhật mục tiêu giữ chỉ dẫn người dùng, tiêu chí có nội dung.

    python tests/run.py resonance_mvp_revise -v

P1: tin bổ sung một chi tiết khác KHÔNG làm mất hạn chót và chỉ tiêu người dùng nêu ở tin trước, kể cả khi
bộ não gửi bỏ chúng; chỉ đổi hay bỏ được khi tin hiện tại có câu trích làm căn cứ. Ràng buộc được kế thừa. P2-2: tiêu chí mô tả rỗng không qua cổng M.
Đi qua kho SQLite thật và plugin javis_goal thật (plugins_host); không gọi model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m2r-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import luot_dang_chay  # noqa: E402
import plugins_host  # noqa: E402
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
    return False


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-r-")).resolve())
P = RS.Principal("agent", "javis", BRAIN)
store = RS.GoalStore()

MSG1 = "Theo dõi hồ sơ cho anh đến ngày 11/10/2026, cần đủ 10 hồ sơ."
MSG2 = "Thêm bảng tổng hợp vào báo cáo nhé."
MSG3 = "Dời hạn sang ngày 15/10/2026 nhé, vẫn cần đủ 10 hồ sơ."
DEADLINE_1 = {"kind": "deadline", "at_iso": "2026-10-11T23:00:00+07:00", "from_user": True,
              "quote": "đến ngày 11/10/2026"}
TARGET_1 = {"text": "10 hồ sơ", "quote": "cần đủ 10 hồ sơ"}


def proposal(**kw):
    p = {"understanding": "Theo dõi hồ sơ và làm báo cáo",
         "criteria": [{"description": "Anh xác nhận báo cáo đúng yêu cầu", "evaluator": "human_confirmation"}],
         "relevant_quote": "Theo dõi hồ sơ", "horizon": dict(DEADLINE_1), "targets": [dict(TARGET_1)],
         "stage": "delivery"}
    p.update(kw)
    return p


def ctx(mid, text, **kw):
    c = {"principal": P, "brain_root": BRAIN, "session_id": "rv", "message_id": mid, "user_text": text,
         "message_ref": R.message_ref("rv", mid), "constraints": []}
    c.update(kw)
    return c


deps = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi model"}), budget=R.CallBudget(0),
                  store=store)

# ───────────── P1-1: tin bổ sung không làm mất hạn và chỉ tiêu cũ ─────────────
g1 = asyncio.run(R.form_goal(R.message_ref("rv", 1), {**ctx(1, MSG1), "proposal": proposal()}, deps))
check("tin 1: hạn người dùng nêu là deadline, ghi nguồn là tin 1",
      g1.horizon["kind"] == "deadline" and g1.horizon["from_user"] is True
      and g1.horizon["source"] == R.message_ref("rv", 1))
check("tin 1: chỉ tiêu có căn cứ, ghi nguồn là tin 1",
      [(t["text"], t["source"]) for t in g1.targets] == [("10 hồ sơ", R.message_ref("rv", 1))])

# Đúng phép tái hiện của review: bộ não giữ nguyên hạn và chỉ tiêu, chỉ đổi cách trình bày.
g2, rel2, kept2 = R.revise_goal(store, P, g1.id, 1, proposal(
    understanding="Theo dõi hồ sơ, báo cáo có bảng tổng hợp", relevant_quote="Thêm bảng tổng hợp"), ctx(2, MSG2))
check("tin 2 chỉ bổ sung: lên revision 2", g2.revision == 2)
check("tin 2 chỉ bổ sung: hạn chót giữ nguyên cả giá trị lẫn nguồn (tin 1)", g2.horizon == g1.horizon)
check("tin 2 chỉ bổ sung: chỉ tiêu giữ nguyên cả giá trị lẫn nguồn (tin 1)", list(g2.targets) == list(g1.targets))
check("tin 2 chỉ bổ sung: không biến chỉ tiêu cũ thành giả định",
      not any("10 hồ sơ" in a for a in g2.assumptions))
check("tin 2 chỉ bổ sung: host ghi quan hệ là bổ sung (amend), không phải giữ hộ gì", rel2 == "amend" and kept2 == [])
it2 = store.get_intent(P, g2.intent_id)
check("tin 2: ý định mới nối về ý định của revision trước",
      it2 is not None and it2["prev_intent_id"] == g1.intent_id and it2["relation"] == "amend")
ev2 = [e for e in store.events(P, g1.id) if e.get("kind") == "reframe"]
check("tin 2: sự kiện reframe mang quan hệ amend",
      bool(ev2) and (ev2[-1].get("payload") or {}).get("relation") == "amend")

# Bản cập nhật chỉ gửi trường thay đổi: phần còn lại kế thừa.
g2b, rel2b, _ = R.revise_goal(store, P, g1.id, 2, {"relevant_quote": "bảng tổng hợp",
                                                    "understanding": "Báo cáo hồ sơ kèm bảng tổng hợp"},
                              ctx(21, MSG2))
check("cập nhật chỉ gửi trường đổi: hạn, chỉ tiêu, tiêu chí kế thừa nguyên vẹn",
      g2b.horizon == g1.horizon and list(g2b.targets) == list(g1.targets)
      and [c["description"] for c in g2b.criteria] == [c["description"] for c in g1.criteria]
      and g2b.understanding == "Báo cáo hồ sơ kèm bảng tổng hợp" and rel2b == "amend")

# Review vòng 2 (P1): tin chỉ đổi trình bày, bộ não bỏ chỉ tiêu và tự dời hạn. Host GIỮ chỉ dẫn cũ.
g_bad, rel_bad, kept_bad = R.revise_goal(store, P, g1.id, 3, {
    "relevant_quote": "bảng tổng hợp", "targets": [],
    "horizon": {**DEADLINE_1, "at_iso": "2026-10-20T23:00:00+07:00"}}, ctx(22, MSG2))
check("tin chỉ đổi trình bày + bộ não gửi targets=[]: chỉ tiêu người dùng vẫn còn, nguồn tin 1",
      list(g_bad.targets) == list(g1.targets))
check("tin chỉ đổi trình bày + bộ não tự dời hạn: hạn 11/10 của người dùng vẫn là deadline, nguồn tin 1",
      g_bad.horizon == g1.horizon)
check("chỉ dẫn được giữ: không ghi replace, và báo lại cho bộ não biết đã giữ gì",
      rel_bad == "amend" and len(kept_bad) == 2 and any("10 hồ sơ" in k for k in kept_bad)
      and any("hạn chót" in k for k in kept_bad))
# Bộ não muốn mốc xem lại nội bộ: không được đè lên hạn đang có hiệu lực của người dùng.
fr_rv = R.validate_proposal({"relevant_quote": "bảng tổng hợp",
                             "horizon": {"kind": "review", "at_iso": "2026-10-09T08:00:00+07:00"}},
                            MSG2, prior=store.get(P, g1.id), notes=[])
check("mốc xem lại do agent đặt không thay deadline của người dùng", fr_rv["horizon"] == g1.horizon)
# Bỏ chỉ tiêu bằng câu trích KHÔNG có trong tin hiện tại: vẫn giữ.
fr_rm = R.validate_proposal({"relevant_quote": "bảng tổng hợp", "targets": [],
                             "remove_targets": [{"text": "10 hồ sơ", "quote": "không cần đủ 10 hồ sơ nữa"}]},
                            MSG2, prior=store.get(P, g1.id))
check("remove_targets với câu trích không có trong tin hiện tại: chỉ tiêu vẫn giữ",
      [t["text"] for t in fr_rm["targets"]] == ["10 hồ sơ"])
# Mượn câu trích cũ cho một chỉ tiêu MỚI: không được coi là chỉ tiêu cũ, chỉ tiêu cũ vẫn còn.
fr_t = R.validate_proposal(proposal(relevant_quote="bảng tổng hợp", targets=[{"text": "12 hồ sơ",
                                                                             "quote": "cần đủ 10 hồ sơ"}]),
                           MSG2, prior=store.get(P, g1.id))
check("mượn câu trích cũ cho chỉ tiêu mới: không thành chỉ tiêu, ghi là giả định, chỉ tiêu cũ còn nguyên",
      [t["text"] for t in fr_t["targets"]] == ["10 hồ sơ"] and any("12 hồ sơ" in a for a in fr_t["assumptions"]))

# Người dùng THẬT SỰ sửa hạn: hạn mới thắng, nguồn là tin mới, quan hệ là thay chỉ dẫn.
g3, rel3, _ = R.revise_goal(store, P, g1.id, 4, proposal(
    relevant_quote="Dời hạn sang ngày 15/10/2026",
    horizon={"kind": "deadline", "at_iso": "2026-10-15T23:00:00+07:00", "from_user": True,
             "quote": "Dời hạn sang ngày 15/10/2026"}), ctx(3, MSG3))
check("người dùng sửa hạn: hạn mới là deadline của người dùng, nguồn là tin 3",
      g3.horizon["kind"] == "deadline" and g3.horizon["from_user"] is True
      and g3.horizon["source"] == R.message_ref("rv", 3)
      and g3.horizon["at"] == R._iso_ts("2026-10-15T23:00:00+07:00"))
check("người dùng sửa hạn: không đóng băng ở hạn cũ", g3.horizon["at"] != g1.horizon["at"])
check("người dùng sửa hạn: host ghi quan hệ là thay chỉ dẫn (replace)", rel3 == "replace")
check("người dùng nhắc lại chỉ tiêu: một chỉ tiêu, nguồn mới là tin 3, không nhân đôi",
      [(t["text"], t["source"]) for t in g3.targets] == [("10 hồ sơ", R.message_ref("rv", 3))])

# Người dùng THẬT SỰ bỏ chỉ tiêu và bỏ hạn, có câu trích ở tin hiện tại.
MSG4 = "Không cần đủ 10 hồ sơ nữa, cũng không cần hạn, cứ theo dõi đều là được."
g4, rel4, kept4 = R.revise_goal(store, P, g1.id, 5, {
    "relevant_quote": "cứ theo dõi đều là được", "targets": [],
    "remove_targets": [{"text": "10 hồ sơ", "quote": "Không cần đủ 10 hồ sơ nữa"}],
    "horizon": {"kind": "maintain", "quote": "cũng không cần hạn"}}, ctx(4, MSG4))
check("người dùng bỏ chỉ tiêu có câu trích: chỉ tiêu được bỏ", g4.targets == () and kept4 == [])
check("người dùng bỏ hạn có câu trích: chân trời mới ghi đúng câu và tin làm căn cứ",
      g4.horizon["kind"] == "maintain" and g4.horizon["quote"] == "cũng không cần hạn"
      and g4.horizon["source"] == R.message_ref("rv", 4))
check("bỏ chỉ dẫn có căn cứ: ghi quan hệ replace", rel4 == "replace"
      and store.get_intent(P, g4.intent_id)["relation"] == "replace")

# expected_revision cũ: xung đột, không đổi gì
check("expected_revision cũ: ConflictError",
      raises(RS.ConflictError, lambda: R.revise_goal(store, P, g1.id, 2, proposal(relevant_quote="bảng tổng hợp"),
                                                      ctx(5, MSG2))))
check("xung đột không tạo revision mới", store.get(P, g1.id).revision == 6)

# ───────────── Review vòng 2 (P2): ràng buộc người dùng được kế thừa ─────────────
MSG_C = "Gom ghi chú họp vào một bản tổng hợp, không xoá ghi chú cũ."
gc = asyncio.run(R.form_goal(R.message_ref("rv", 30), {
    **ctx(30, MSG_C, constraints=["không xoá ghi chú cũ"]),
    "proposal": proposal(relevant_quote="Gom ghi chú họp", targets=[], horizon={"kind": "maintain"})}, deps))
check("tạo mục tiêu có ràng buộc người dùng", gc.constraints == ("không xoá ghi chú cũ",))
gc2, _, _ = R.revise_goal(store, P, gc.id, 1, {"relevant_quote": "bảng tổng hợp",
                                               "understanding": "Bản tổng hợp kèm bảng"}, ctx(31, MSG2))
check("cập nhật từng phần trên mục tiêu có ràng buộc: thành công, ràng buộc giữ nguyên",
      gc2.revision == 2 and gc2.constraints == ("không xoá ghi chú cũ",))
gc3, _, _ = R.revise_goal(store, P, gc.id, 2, {"relevant_quote": "chỉ đọc", "constraints": ["chỉ đọc"]},
                          ctx(32, "Từ giờ chỉ đọc thôi nhé.", constraints=["chỉ đọc"]))
check("bổ sung ràng buộc mới: giữ cả ràng buộc cũ", set(gc3.constraints) == {"không xoá ghi chú cũ", "chỉ đọc"})
gc4, _, _ = R.revise_goal(store, P, gc.id, 3, {"relevant_quote": "bảng tổng hợp", "constraints": []},
                          ctx(33, MSG2))
check("bộ não gửi constraints=[]: không gỡ được ràng buộc nào", set(gc4.constraints) == set(gc3.constraints))

# Ý định ghi cùng transaction với revision: kho từ chối thì không để lại ý định mồ côi.
import sqlite3  # noqa: E402

_db = Path(_STATE) / "resonance.sqlite3"


def _n_intents():
    with sqlite3.connect(_db) as c:
        return c.execute("SELECT COUNT(*) FROM intents").fetchone()[0]


_before = _n_intents()
_bad_frame = R.validate_proposal({"relevant_quote": "bảng tổng hợp"}, MSG2, prior=store.get(P, gc.id))
_bad_frame["constraints"] = []          # giả một khung thiếu ràng buộc lọt tới kho
check("kho từ chối revision thiếu ràng buộc",
      raises(R.GoalRejected, lambda: store.revise(P, gc.id, 4, _bad_frame, reason="thử",
                                                  intent=store.new_intent(P, "rv", 34, MSG2))))
check("revision bị từ chối không để lại ý định mồ côi", _n_intents() == _before)

# ───────────── P2-2: tiêu chí phải nói rõ cần kiểm điều gì ─────────────
for label, crit in (("rỗng", ""), ("chỉ khoảng trắng", "   \n\t ")):
    check(f"tiêu chí mô tả {label}: bị từ chối",
          raises(R.GoalRejected, lambda crit=crit: R.validate_proposal(
              proposal(criteria=[{"description": crit, "evaluator": "human_confirmation"}]), MSG1)))
fr_mix = R.validate_proposal(proposal(criteria=[
    {"description": "", "evaluator": "human_confirmation"},
    {"description": "  Báo cáo có   đủ 10 hồ sơ ", "evaluator": "artifact_contract", "params": {"path": "bc.md"}},
    {"description": " ", "evaluator": "artifact_contract"}]), MSG1)
check("danh sách pha trộn: chỉ giữ tiêu chí có nội dung, id đánh lại từ c1",
      [(c["id"], c["description"]) for c in fr_mix["criteria"]] == [("c1", "Báo cáo có đủ 10 hồ sơ")])

# Qua tool thật: đề xuất delivery với tiêu chí rỗng không để lại mục tiêu nào.
(Path(BRAIN) / "Javis").mkdir(parents=True, exist_ok=True)
(Path(BRAIN) / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
_, route = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
call = route["javis_goal"]["call"]


def tool(mid, text, args):
    k = luot_dang_chay.bat_dau("web:tool", BRAIN, msg_id=mid, user_text=text)
    try:
        return asyncio.run(call(args))
    finally:
        luot_dang_chay.ket_thuc(k)


out = tool(7, MSG1, {"op": "create", **proposal(criteria=[{"description": "", "evaluator": "human_confirmation"}])})
check("tool: tiêu chí rỗng trả ERROR nói rõ vì sao", out.startswith("ERROR") and "description" in out)
check("tool: tiêu chí rỗng không lưu mục tiêu", store.find_by_key(P, R.message_ref("tool", 7)) is None)

# Qua tool thật: đúng kịch bản review, tin 2 bổ sung định dạng thì hạn và chỉ tiêu còn nguyên.
out = tool(8, MSG1, {"op": "create", **proposal()})
gt = store.find_by_key(P, R.message_ref("tool", 8))
check("tool: tạo mục tiêu có hạn và chỉ tiêu", gt is not None and gt.horizon["kind"] == "deadline")
out = tool(9, MSG2, {"op": "update", "goal_id": gt.id, "expected_revision": 1,
                     **proposal(understanding="Theo dõi hồ sơ, báo cáo có bảng tổng hợp",
                                relevant_quote="Thêm bảng tổng hợp")})
gt2 = store.get(P, gt.id)
check("tool update tin bổ sung: thành công, revision 2", not out.startswith("ERROR") and gt2.revision == 2)
check("tool update tin bổ sung: hạn chót còn nguyên và tóm tắt vẫn ghi là hạn người dùng nêu",
      gt2.horizon == gt.horizon and "người dùng nêu" in out)
check("tool update tin bổ sung: chỉ tiêu còn nguyên", list(gt2.targets) == list(gt.targets))
out = tool(10, MSG2, {"op": "update", "goal_id": gt.id, "expected_revision": 2, "relevant_quote": "Thêm bảng tổng hợp",
                      "targets": []})
check("tool: bộ não gửi targets=[] ở tin chỉ đổi trình bày thì chỉ tiêu còn, và tool báo đã giữ lại",
      list(store.get(P, gt.id).targets) == list(gt.targets) and "Host giữ lại chỉ dẫn cũ" in out)
out = tool(11, MSG_C, {"op": "create", **proposal(relevant_quote="Gom ghi chú họp", targets=[],
                                                  horizon={"kind": "maintain"},
                                                  constraints=["không xoá ghi chú cũ"])})
gk = store.find_by_key(P, R.message_ref("tool", 11))
out = tool(12, MSG2, {"op": "update", "goal_id": gk.id, "expected_revision": 1, "relevant_quote": "Thêm bảng tổng hợp",
                      "understanding": "Bản tổng hợp kèm bảng"})
check("tool: cập nhật từng phần trên mục tiêu có ràng buộc thành công, ràng buộc còn",
      not out.startswith("ERROR") and store.get(P, gk.id).constraints == ("không xoá ghi chú cũ",))

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
