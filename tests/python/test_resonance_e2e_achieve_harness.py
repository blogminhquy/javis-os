"""Ca âm cho bộ chạy pilot achieve (review bộ chạy, PR #579, P2-1 và P2-2). Không gọi model, không dựng server thật.

    python tests/run.py resonance_e2e_achieve_harness -v

P2-1: kiểm hỏng ở S4 (sai nguồn góp ý, mất ràng buộc, thiếu lịch) từng chỉ được GHI, luồng vẫn dựng server giai
đoạn 2. Nay cổng chi phí nằm TRONG ba thao tác tốn lượt (dựng server, gửi tin chat, bấm xác nhận). Test chạy đúng
các thao tác đó của harness với tiến trình và mạng giả, và soát script bộ chạy không còn đường tắt nào vòng qua cổng.

P2-2: tin báo của giai đoạn phải là tin MỚI của đúng loại và revision, có trong đúng phiên kèm biên nhận. Ca âm:
không gửi, chỉ có tin cũ của bản đầu, gửi nhầm phiên, có tin mà thiếu biên nhận, chỉ có cờ delivered.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _e2e_achieve_harness as H  # noqa: E402
import _e2e_pilot_guard as G  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def raises_gate(fn):
    try:
        fn()
    except H.GateClosed:
        return True
    return False


class FakeProc:
    pid = 0

    def poll(self):
        return None

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def harness():
    checks = H.Checks(echo=lambda *_: None)
    spawned = []

    def popen(*a, **kw):
        spawned.append(kw["env"]["JAVIS_RESONANCE_CALL_CEILING"])
        return FakeProc()
    srv = H.Server(root=ROOT, port=0, base=Path(tempfile.mkdtemp(prefix="ach-h-")), env0={},
                   phase_ceiling={1: 1, 2: 2}, checks=checks, popen=popen, health=lambda: True)
    return checks, srv, spawned


# ═══════════ P2-1: kiểm S4 hỏng thì không dựng giai đoạn 2, không gửi chat, không bấm xác nhận ═══════════
for case, kind in (("ý định mới không phải lời góp ý", "technical"), ("ràng buộc cũ bị mất", "contract"),
                   ("không có lịch làm lại cho revision mới", "technical")):
    checks, srv, spawned = harness()
    srv.start(1, True, {})
    srv.kill()
    checks.check(f"S4 {case}", False, kind)
    check(f"S4 hỏng ({case}): dựng server giai đoạn 2 bị chặn", raises_gate(lambda: srv.start(2, False, {})))
    check(f"S4 hỏng ({case}): không tiến trình nào được dựng với trần 2", spawned == ["1"] and len(srv.started) == 1)

checks, srv, spawned = harness()
srv.start(1, True, {})
srv.kill()
checks.check("S4 mọi kiểm đạt", True)
srv.start(2, False, {})
check("đối chứng: S4 đạt thì dựng được giai đoạn 2 với trần 2", spawned == ["1", "2"])

# Gửi tin chat: cổng đóng thì không giữ chỗ trong sổ và không gửi.
checks, _, _ = harness()
ledger = G.TurnLedger(Path(tempfile.mkdtemp(prefix="ach-l-")) / "t.json", 2)
sent = []
H.chat_turn(checks, ledger, "S1", lambda: sent.append("S1") or ("sid", ["turn_done"], [], "ok"))
checks.check("S3 trạng thái giữ sau dựng lại", False)
check("kiểm hỏng trước S4: không gửi tin góp ý",
      raises_gate(lambda: H.chat_turn(checks, ledger, "S4", lambda: sent.append("S4"))) and sent == ["S1"])
check("kiểm hỏng trước S4: sổ lượt chat không giữ thêm chỗ", ledger.used() == 1)

# Lượt chat lỗi: tính vào sổ, không thử lại.
checks, _, _ = harness()
ledger2 = G.TurnLedger(Path(tempfile.mkdtemp(prefix="ach-l2-")) / "t.json", 2)


def _boom():
    raise TimeoutError("hết giờ")


check("lượt chat lỗi: dừng bằng cổng", raises_gate(lambda: H.chat_turn(checks, ledger2, "S1", _boom)))
check("lượt chat lỗi: vẫn tính vào sổ, không giữ lại cùng lượt",
      ledger2.used() == 1 and ledger2.entries()[0]["status"].startswith("error") and not ledger2.reserve("S1"))

# Bấm xác nhận: S5 hỏng thì S6 không bấm.
posts = []


def http(method, path, **kw):
    posts.append((method, path, kw.get("json", {}).get("criterion_id")))
    return 200, {}


checks, _, _ = harness()
view = {"revision": 2, "artifact_ref": "sha"}
checks.check("S5 tin báo bản sửa về đúng phiên", False)
check("S5 hỏng: không bấm Đạt yêu cầu", raises_gate(lambda: H.accept(checks, http, "g1", view, {"id": "c2"}))
      and posts == [])
checks, _, _ = harness()
H.accept(checks, http, "g1", view, {"id": "c2"})
check("đối chứng: kiểm đều đạt thì bấm đúng tiêu chí, đúng revision", posts == [("POST", "/goals/g1/feedback", "c2")])

# Script bộ chạy: mọi thao tác tốn lượt đều đi qua harness (không còn đường tắt vòng qua cổng).
src = (Path(__file__).parent / "test_resonance_mvp_e2e_achieve.py").read_text(encoding="utf-8")
tree = ast.parse(src)
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
srv_start = [n for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "start"
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "SRV"]
check("bộ chạy: SRV.start chỉ gọi ở một chỗ (start_server), không dựng server vòng qua harness", len(srv_start) == 1)
check("bộ chạy: không tự POST outcome_accepted, chỉ qua H.accept", "outcome_accepted" not in src)
ws_calls = [n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "_ws_chat"]
check("bộ chạy: _ws_chat chỉ gọi bên trong H.chat_turn (một chỗ)", len(ws_calls) == 1
      and "H.chat_turn(CHECKS, TURNS" in src)
check("bộ chạy: check của script là Checks của harness (kiểm hỏng đóng cổng)", "check = CHECKS.check" in src)
check("bộ chạy: S2, S5, S6 đối chiếu tin báo theo giai đoạn (notice_in_session)",
      src.count("notice_in_session(sid, g.id, \"goal.waiting_human\", g.revision)") == 1
      and src.count("notice_in_session(sid, g.id, \"goal.waiting_human\", g4.revision)") == 1
      and src.count("notice_in_session(sid, g.id, \"goal.succeeded\", v[\"revision\"])") >= 1)

# ═══════════ P2-2: tin báo phải là tin mới, đúng loại, đúng revision, đúng phiên, có biên nhận ═══════════
ROWS = [{"id": 1, "goal_id": "g1", "kind": "goal.waiting_human", "revision": 1, "delivered": True},
        {"id": 2, "goal_id": "g1", "kind": "goal.revised", "revision": 2, "delivered": True},
        {"id": 3, "goal_id": "g1", "kind": "goal.waiting_human", "revision": 2, "delivered": True}]
OLD = [{"goal_id": "g1", "report": "outbox:1", "receipt": True}]
CARD = [{"goal_id": "g1", "report": "outbox:2", "receipt": True}]
NEW = [{"goal_id": "g1", "report": "outbox:3", "receipt": True}]
S = H.stage_notice
check("đối chứng: tin bản sửa mới, có biên nhận trong phiên: đạt", S(ROWS, OLD + CARD + NEW, "g1",
                                                                       "goal.waiting_human", 2)[0])
check("chỉ có tin cũ của bản đầu: không đạt", not S(ROWS, OLD + CARD, "g1", "goal.waiting_human", 2)[0])
check("chỉ có thẻ reframe của revision mới: không đạt", not S(ROWS, CARD, "g1", "goal.waiting_human", 2)[0])
check("không có tin nào trong phiên: không đạt (không còn all([]) rỗng mà đạt)",
      not S(ROWS, [], "g1", "goal.waiting_human", 2)[0])
check("outbox chưa có dòng nào của revision mới (không gửi): không đạt",
      not S(ROWS[:2], OLD + CARD, "g1", "goal.waiting_human", 2)[0])
check("outbox delivered nhưng tin nằm ở phiên khác (phiên chủ không có): không đạt",
      not S(ROWS, OLD, "g1", "goal.waiting_human", 2)[0])
check("tin có trong phiên nhưng thiếu biên nhận: không đạt",
      not S(ROWS, [{"goal_id": "g1", "report": "outbox:3", "receipt": False}], "g1", "goal.waiting_human", 2)[0])
check("tin mang khoá đúng nhưng của mục tiêu khác: không đạt",
      not S(ROWS, [{"goal_id": "g9", "report": "outbox:3", "receipt": True}], "g1", "goal.waiting_human", 2)[0])
check("dòng outbox chưa giao: không đạt",
      not S([{**ROWS[2], "delivered": False}], NEW, "g1", "goal.waiting_human", 2)[0])
SUC = ROWS + [{"id": 4, "goal_id": "g1", "kind": "goal.succeeded", "revision": 2, "delivered": True}]
check("S6: goal.succeeded delivered mà phiên không có tin thành công: không đạt",
      not S(SUC, OLD + CARD + NEW, "g1", "goal.succeeded", 2)[0])
check("S6 đối chứng: tin thành công có trong phiên, có biên nhận: đạt",
      S(SUC, NEW + [{"goal_id": "g1", "report": "outbox:4", "receipt": True}], "g1", "goal.succeeded", 2)[0])
check("chuẩn hoá dòng outbox đọc revision từ payload và cờ đã giao",
      H.outbox_rows([(5, "g1", "goal.succeeded", '{"revision": 3}', 1.0), (6, "g1", "x", "hỏng", None)])
      == [{"id": 5, "goal_id": "g1", "kind": "goal.succeeded", "revision": 3, "delivered": True},
          {"id": 6, "goal_id": "g1", "kind": "x", "revision": None, "delivered": False}])

print(f"\n{'FAIL' if _fails else 'OK'}: {len(_fails)} lỗi")
raise SystemExit(1 if _fails else 0)
