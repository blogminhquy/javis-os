"""Resonance M2 (sửa sau review PR #567): cập nhật mục tiêu giữ căn cứ cũ, và tiêu chí phải có nội dung.

    python tests/run.py resonance_mvp_revise -v

P1-1: tin bổ sung một chi tiết khác KHÔNG làm mất hạn chót và chỉ tiêu người dùng nêu ở tin trước,
nhưng người dùng thật sự sửa hạn thì hạn mới thắng. P2-2: tiêu chí mô tả rỗng không qua cổng M.
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
g2, rel2 = R.revise_goal(store, P, g1.id, 1, proposal(understanding="Theo dõi hồ sơ, báo cáo có bảng tổng hợp",
                                                      relevant_quote="Thêm bảng tổng hợp"), ctx(2, MSG2))
check("tin 2 chỉ bổ sung: lên revision 2", g2.revision == 2)
check("tin 2 chỉ bổ sung: hạn chót giữ nguyên cả giá trị lẫn nguồn (tin 1)", g2.horizon == g1.horizon)
check("tin 2 chỉ bổ sung: chỉ tiêu giữ nguyên cả giá trị lẫn nguồn (tin 1)", list(g2.targets) == list(g1.targets))
check("tin 2 chỉ bổ sung: không biến chỉ tiêu cũ thành giả định",
      not any("10 hồ sơ" in a for a in g2.assumptions))
check("tin 2 chỉ bổ sung: host ghi quan hệ là bổ sung (amend)", rel2 == "amend")
it2 = store.get_intent(P, g2.intent_id)
check("tin 2: ý định mới nối về ý định của revision trước",
      it2 is not None and it2["prev_intent_id"] == g1.intent_id and it2["relation"] == "amend")
ev2 = [e for e in store.events(P, g1.id) if e.get("kind") == "reframe"]
check("tin 2: sự kiện reframe mang quan hệ amend",
      bool(ev2) and (ev2[-1].get("payload") or {}).get("relation") == "amend")

# Bản cập nhật chỉ gửi trường thay đổi: phần còn lại kế thừa.
g2b, rel2b = R.revise_goal(store, P, g1.id, 2, {"relevant_quote": "bảng tổng hợp",
                                                 "understanding": "Báo cáo hồ sơ kèm bảng tổng hợp"},
                           ctx(21, MSG2))
check("cập nhật chỉ gửi trường đổi: hạn, chỉ tiêu, tiêu chí kế thừa nguyên vẹn",
      g2b.horizon == g1.horizon and list(g2b.targets) == list(g1.targets)
      and [c["description"] for c in g2b.criteria] == [c["description"] for c in g1.criteria]
      and g2b.understanding == "Báo cáo hồ sơ kèm bảng tổng hợp" and rel2b == "amend")

# Bộ não tự dời hạn mà người dùng không nói: không được kế thừa nguồn người dùng, thành mốc xem lại.
moved = proposal(relevant_quote="bảng tổng hợp", horizon={**DEADLINE_1, "at_iso": "2026-10-20T23:00:00+07:00"})
fr_moved = R.validate_proposal(moved, MSG2, prior=store.get(P, g1.id), source_ref=R.message_ref("rv", 22))
check("agent tự dời hạn không có lời người dùng: thành mốc xem lại, không giữ from_user",
      fr_moved["horizon"]["kind"] == "review" and fr_moved["horizon"]["from_user"] is False)
# Mượn câu trích cũ cho một chỉ tiêu MỚI: không được coi là chỉ tiêu cũ.
fr_t = R.validate_proposal(proposal(relevant_quote="bảng tổng hợp", targets=[{"text": "12 hồ sơ",
                                                                             "quote": "cần đủ 10 hồ sơ"}]),
                           MSG2, prior=store.get(P, g1.id))
check("mượn câu trích cũ cho chỉ tiêu mới: không thành chỉ tiêu, ghi là giả định",
      fr_t["targets"] == [] and any("12 hồ sơ" in a for a in fr_t["assumptions"]))

# Người dùng THẬT SỰ sửa hạn: hạn mới thắng, nguồn là tin mới, quan hệ là thay chỉ dẫn.
g3, rel3 = R.revise_goal(store, P, g1.id, 3, proposal(
    relevant_quote="Dời hạn sang ngày 15/10/2026",
    horizon={"kind": "deadline", "at_iso": "2026-10-15T23:00:00+07:00", "from_user": True,
             "quote": "Dời hạn sang ngày 15/10/2026"}), ctx(3, MSG3))
check("người dùng sửa hạn: hạn mới là deadline của người dùng, nguồn là tin 3",
      g3.horizon["kind"] == "deadline" and g3.horizon["from_user"] is True
      and g3.horizon["source"] == R.message_ref("rv", 3)
      and g3.horizon["at"] == R._iso_ts("2026-10-15T23:00:00+07:00"))
check("người dùng sửa hạn: không đóng băng ở hạn cũ", g3.horizon["at"] != g1.horizon["at"])
check("người dùng sửa hạn: host ghi quan hệ là thay chỉ dẫn (replace)", rel3 == "replace")
check("người dùng sửa hạn: chỉ tiêu vẫn còn", [t["text"] for t in g3.targets] == ["10 hồ sơ"])

# Bộ não bỏ chỉ tiêu cũ: không chặn (người dùng có thể đã bỏ), nhưng ghi rõ là thay chỉ dẫn để soát được.
g4, rel4 = R.revise_goal(store, P, g1.id, 4, proposal(relevant_quote="bảng tổng hợp", targets=[],
                                                      horizon=dict(g3.horizon)), ctx(4, MSG2))
check("bỏ chỉ tiêu cũ: ghi quan hệ replace, hạn vẫn giữ nguồn tin 3",
      rel4 == "replace" and g4.targets == () and g4.horizon == g3.horizon)

# expected_revision cũ: xung đột, không đổi gì
check("expected_revision cũ: ConflictError",
      raises(RS.ConflictError, lambda: R.revise_goal(store, P, g1.id, 2, proposal(relevant_quote="bảng tổng hợp"),
                                                      ctx(5, MSG2))))
check("xung đột không tạo revision mới", store.get(P, g1.id).revision == 5)

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

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
