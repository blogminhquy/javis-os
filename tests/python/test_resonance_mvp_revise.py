"""Resonance M2 (sửa sau hai vòng review PR #567): cập nhật mục tiêu giữ chỉ dẫn người dùng, tiêu chí có nội dung.

    python tests/run.py resonance_mvp_revise -v

P1: hạn chót, chỉ tiêu và ràng buộc người dùng nêu ở tin trước là chỉ dẫn đang có hiệu lực; M2 không đổi hay
bỏ chúng qua bản cập nhật (vòng 3: câu trích có mặt trong tin không chứng minh người dùng muốn đổi), chỉ thêm
chỉ dẫn mới. Phần chưa áp dụng được báo lại. P2-2: tiêu chí mô tả rỗng không qua cổng M.
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

# Review vòng 2-3 (P1): hạn chót và chỉ tiêu người dùng đã nêu là chỉ dẫn đang có hiệu lực. M2 KHÔNG đổi hay
# bỏ chúng qua bản cập nhật, dù câu trích có mặt trong tin hay không: host giữ nguyên và báo phần chưa áp dụng.
def _frozen(label, mid, text, upd):
    before = store.get(P, g1.id)
    g, rel, kept = R.revise_goal(store, P, g1.id, before.revision, upd, ctx(mid, text))
    check(f"{label}: hạn chót người dùng còn nguyên cả giá trị lẫn nguồn (tin 1)", g.horizon == g1.horizon)
    check(f"{label}: chỉ tiêu người dùng còn nguyên cả giá trị lẫn nguồn (tin 1)", list(g.targets) == list(g1.targets))
    check(f"{label}: không ghi replace, báo phần chưa áp dụng cho bộ não", rel != "replace" and len(kept) >= 1)
    check(f"{label}: phần bị chặn không kéo mode hay stage đổi theo",
          g.mode == before.mode and g.stage == before.stage)
    return g, rel, kept


# Tin chỉ đổi trình bày, bộ não bỏ chỉ tiêu và tự dời hạn.
_, rel_a, kept_a = _frozen("bỏ chỉ tiêu + tự dời hạn, câu trích cũ", 22, MSG2, {
    "relevant_quote": "bảng tổng hợp", "targets": [],
    "horizon": {**DEADLINE_1, "at_iso": "2026-10-20T23:00:00+07:00"}})
check("không còn gì đổi được áp dụng: không ghi revision mới (relation none)",
      rel_a == "none" and store.get(P, g1.id).revision == 3
      and any("hạn chót" in k for k in kept_a) and any("10 hồ sơ" in k for k in kept_a))
# Đúng phép tái hiện vòng 3: câu trích CÓ MẶT trong tin hiện tại nhưng không nói bỏ gì.
_frozen("câu trích có mặt nhưng không liên quan (vòng 3)", 23, MSG2, {
    "relevant_quote": "Thêm bảng tổng hợp", "targets": [],
    "remove_targets": [{"text": "10 hồ sơ", "quote": "Thêm bảng tổng hợp"}],
    "horizon": {"kind": "maintain", "quote": "Thêm bảng tổng hợp"}})
# Người dùng THẬT SỰ dời hạn: M2 chưa áp dụng, báo rõ, không đóng vai là đã đổi.
MSG4 = "Không cần đủ 10 hồ sơ nữa, cũng không cần hạn, cứ theo dõi đều là được."
_frozen("người dùng thật sự dời hạn (chưa hỗ trợ ở M2)", 3, MSG3, proposal(
    relevant_quote="Dời hạn sang ngày 15/10/2026",
    horizon={"kind": "deadline", "at_iso": "2026-10-15T23:00:00+07:00", "from_user": True,
             "quote": "Dời hạn sang ngày 15/10/2026"}))
_frozen("người dùng thật sự bỏ chỉ tiêu và bỏ hạn (chưa hỗ trợ ở M2)", 4, MSG4, {
    "relevant_quote": "cứ theo dõi đều là được", "targets": [],
    "remove_targets": [{"text": "10 hồ sơ", "quote": "Không cần đủ 10 hồ sơ nữa"}],
    "horizon": {"kind": "maintain", "quote": "cũng không cần hạn"}})
# Chỉ gửi remove_targets (vòng 3, P2): không âm thầm "thành công" mà vẫn còn chỉ tiêu; báo rõ chưa hỗ trợ.
_, rel_rm, kept_rm = R.revise_goal(store, P, g1.id, store.get(P, g1.id).revision, {
    "relevant_quote": "Không cần đủ 10 hồ sơ nữa",
    "remove_targets": [{"text": "10 hồ sơ", "quote": "Không cần đủ 10 hồ sơ nữa"}]}, ctx(5, MSG4))
check("chỉ gửi remove_targets: không đổi gì, relation none, báo remove_targets chưa hỗ trợ",
      rel_rm == "none" and any("remove_targets" in k for k in kept_rm)
      and [t["text"] for t in store.get(P, g1.id).targets] == ["10 hồ sơ"])
# Mốc xem lại do agent đặt không đè lên deadline đang có hiệu lực.
fr_rv = R.validate_proposal({"relevant_quote": "bảng tổng hợp",
                             "horizon": {"kind": "review", "at_iso": "2026-10-09T08:00:00+07:00"}},
                            MSG2, prior=store.get(P, g1.id), notes=[])
check("mốc xem lại do agent đặt không thay deadline của người dùng", fr_rv["horizon"] == g1.horizon)
# Mượn câu trích cũ cho một chỉ tiêu MỚI: không được coi là chỉ tiêu, chỉ tiêu cũ vẫn còn.
fr_t = R.validate_proposal(proposal(relevant_quote="bảng tổng hợp", targets=[{"text": "12 hồ sơ",
                                                                             "quote": "cần đủ 10 hồ sơ"}]),
                           MSG2, prior=store.get(P, g1.id))
check("mượn câu trích cũ cho chỉ tiêu mới: không thành chỉ tiêu, ghi là giả định, chỉ tiêu cũ còn nguyên",
      [t["text"] for t in fr_t["targets"]] == ["10 hồ sơ"] and any("12 hồ sơ" in a for a in fr_t["assumptions"]))
# Người dùng nhắc lại chỉ tiêu ở tin mới: vẫn một mục, giữ nguồn cũ (không nhân đôi, không đổi chỉ dẫn).
fr_re = R.validate_proposal(proposal(relevant_quote="Dời hạn", targets=[dict(TARGET_1)]), MSG3,
                            prior=store.get(P, g1.id), source_ref=R.message_ref("rv", 6))
check("người dùng nhắc lại chỉ tiêu: một mục, nguồn vẫn là tin 1",
      [(t["text"], t["source"]) for t in fr_re["targets"]] == [("10 hồ sơ", R.message_ref("rv", 1))])
# THÊM chỉ dẫn mới vẫn được: chỉ tiêu mới trích từ tin hiện tại, chỉ tiêu cũ giữ nguyên.
MSG5 = "Thêm nữa, cần có ít nhất 3 hồ sơ ưu tiên."
g5, rel5, kept5 = R.revise_goal(store, P, g1.id, store.get(P, g1.id).revision, {
    "relevant_quote": "cần có ít nhất 3 hồ sơ ưu tiên",
    "targets": [dict(TARGET_1), {"text": "3 hồ sơ ưu tiên", "quote": "ít nhất 3 hồ sơ ưu tiên"}]}, ctx(7, MSG5))
check("thêm chỉ tiêu mới có căn cứ: được thêm với nguồn tin mới, chỉ tiêu cũ giữ, quan hệ amend",
      [(t["text"], t["source"]) for t in g5.targets] == [("10 hồ sơ", R.message_ref("rv", 1)),
                                                          ("3 hồ sơ ưu tiên", R.message_ref("rv", 7))]
      and rel5 == "amend" and kept5 == [])
# Mục tiêu CHƯA có hạn người dùng: người dùng nêu hạn ở tin sau thì được thêm (cùng luật trích như lúc tạo).
g_nd = asyncio.run(R.form_goal(R.message_ref("rv", 40), {**ctx(40, MSG1), "proposal": proposal(
    horizon={"kind": "review", "at_iso": "2026-10-09T08:00:00+07:00"})}, deps))
g_nd2, rel_nd, _ = R.revise_goal(store, P, g_nd.id, 1, proposal(
    relevant_quote="Dời hạn sang ngày 15/10/2026",
    horizon={"kind": "deadline", "at_iso": "2026-10-15T23:00:00+07:00", "from_user": True,
             "quote": "Dời hạn sang ngày 15/10/2026"}), ctx(41, MSG3))
check("chưa có hạn người dùng: hạn mới có căn cứ được thêm, nguồn tin mới",
      g_nd2.horizon["kind"] == "deadline" and g_nd2.horizon["source"] == R.message_ref("rv", 41) and rel_nd == "amend")

# expected_revision cũ: xung đột, không đổi gì
_rev = store.get(P, g1.id).revision
check("expected_revision cũ: ConflictError",
      raises(RS.ConflictError, lambda: R.revise_goal(store, P, g1.id, 2, proposal(relevant_quote="bảng tổng hợp"),
                                                      ctx(8, MSG2))))
check("xung đột không tạo revision mới", store.get(P, g1.id).revision == _rev)

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
gc4, rel_c4, _ = R.revise_goal(store, P, gc.id, 3, {"relevant_quote": "bảng tổng hợp", "constraints": []},
                          ctx(33, MSG2))
check("bộ não gửi constraints=[]: không gỡ được ràng buộc nào, không ghi revision",
      set(gc4.constraints) == set(gc3.constraints) and rel_c4 == "none")

# Ý định ghi cùng transaction với revision: kho từ chối thì không để lại ý định mồ côi.
import sqlite3  # noqa: E402

_db = Path(_STATE) / "resonance.sqlite3"


def _n_intents():
    return _counts()["intents"]


def _counts():
    from contextlib import closing
    with closing(sqlite3.connect(_db)) as c:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("intents", "goal_revisions", "goal_events", "outbox")}


_before = _n_intents()
_bad_frame = R.validate_proposal({"relevant_quote": "bảng tổng hợp"}, MSG2, prior=store.get(P, gc.id))
_bad_frame["constraints"] = []          # giả một khung thiếu ràng buộc lọt tới kho
check("kho từ chối revision thiếu ràng buộc",
      raises(R.GoalRejected, lambda: store.revise(P, gc.id, store.get(P, gc.id).revision, _bad_frame, reason="thử",
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
import _resonance_agent as RA  # noqa: E402  - A1: tool chỉ chạy trong lượt của agent đã bật
AG = RA.enable(store, BRAIN)
_, route = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
call = route["javis_goal"]["call"]


def tool(mid, text, args):
    with RA.turn(AG, "tool", mid, text, BRAIN):
        return asyncio.run(call(args))


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
check("tool: bộ não gửi targets=[] ở tin chỉ đổi trình bày thì chỉ tiêu còn, tool báo không áp dụng gì",
      list(store.get(P, gt.id).targets) == list(gt.targets) and "CHƯA áp dụng" in out
      and "KHÔNG có thay đổi nào" in out and store.get(P, gt.id).revision == 2)
out = tool(11, MSG_C, {"op": "create", **proposal(relevant_quote="Gom ghi chú họp", targets=[],
                                                  horizon={"kind": "maintain"},
                                                  constraints=["không xoá ghi chú cũ"])})
gk = store.find_by_key(P, R.message_ref("tool", 11))
out = tool(12, MSG2, {"op": "update", "goal_id": gk.id, "expected_revision": 1, "relevant_quote": "Thêm bảng tổng hợp",
                      "understanding": "Bản tổng hợp kèm bảng"})
check("tool: cập nhật từng phần trên mục tiêu có ràng buộc thành công, ràng buộc còn",
      not out.startswith("ERROR") and store.get(P, gk.id).constraints == ("không xoá ghi chú cũ",))

# ───────────── Review vòng 4: qua tool thật, phần bị chặn không đổi gì khác và được báo đúng ─────────────
out = tool(13, MSG1, {"op": "create", **proposal(mode="achieve")})
gm = store.find_by_key(P, R.message_ref("tool", 13))
_c0 = _counts()
out = tool(14, MSG2, {"op": "update", "goal_id": gm.id, "expected_revision": gm.revision,
                      "relevant_quote": "Thêm bảng tổng hợp", "targets": [],
                      "horizon": {"kind": "maintain", "quote": "Thêm bảng tổng hợp"}})
check("tool, horizon maintain bị chặn: bản ghi y nguyên (mode vẫn achieve, revision giữ)",
      gm.mode == "achieve" and store.get(P, gm.id) == gm)
check("tool, horizon maintain bị chặn: không thêm dòng intent, revision, event, outbox", _counts() == _c0)
check("tool, horizon maintain bị chặn: báo không có thay đổi và phần CHƯA áp dụng",
      "KHÔNG có thay đổi" in out and "CHƯA áp dụng" in out)
out = tool(15, MSG4, {"op": "update", "goal_id": gm.id, "expected_revision": gm.revision,
                      "relevant_quote": "Không cần đủ 10 hồ sơ nữa",
                      "remove_targets": [{"text": "10 hồ sơ", "quote": "Không cần đủ 10 hồ sơ nữa"}]})
check("tool, chỉ gửi remove_targets (trường cũ): báo chưa hỗ trợ, không đổi gì",
      "KHÔNG có thay đổi" in out and "remove_targets" in out and store.get(P, gm.id) == gm and _counts() == _c0)
MSG6 = "Thêm bảng tổng hợp. Không cần đủ 10 hồ sơ nữa."
out = tool(16, MSG6, {"op": "update", "goal_id": gm.id, "expected_revision": gm.revision,
                      "relevant_quote": "Thêm bảng tổng hợp", "understanding": "Báo cáo hồ sơ có bảng tổng hợp",
                      "remove_targets": [{"text": "10 hồ sơ", "quote": "Không cần đủ 10 hồ sơ nữa"}]})
gm2 = store.get(P, gm.id)
check("tool, pha trộn sửa hợp lệ + remove_targets: phần hợp lệ được áp dụng, chỉ tiêu vẫn giữ",
      gm2.understanding == "Báo cáo hồ sơ có bảng tổng hợp" and list(gm2.targets) == list(gm.targets)
      and gm2.revision == gm.revision + 1)
check("tool, pha trộn: báo đã cập nhật KÈM phần CHƯA áp dụng nhắc remove_targets, tóm tắt hiện chỉ tiêu còn giữ",
      "Đã cập nhật mục tiêu" in out and "CHƯA áp dụng" in out and "remove_targets" in out
      and "Chỉ tiêu người dùng nêu: 10 hồ sơ" in out)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
