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

# ═══════════ Review mã bàn giao: P2-1 (giữ đầu ra chưa có receipt) và P2-2 (sửa hợp lệ sau tiếp nhận) ═══════════
import asyncio  # noqa: E402
import os  # noqa: E402

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="ach-h-state-"))
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_B = Path(tempfile.mkdtemp(prefix="ach-h-brain-")).resolve()
(_B / "Javis").mkdir()
(_B / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
_ST = RS.GoalStore(Path(tempfile.mkdtemp(prefix="ach-h-db-")) / "r.sqlite3")
_P = RS.Principal("agent", "javis", str(_B))
_DL = "Docs/hd.md"


def _goal(mid, hold=False):
    return asyncio.run(R.form_goal(R.message_ref("s", mid), {
        "principal": _P, "brain_root": str(_B), "session_id": "s", "message_id": mid,
        "user_text": "Em lo giúp anh bản hướng dẫn tới khi anh thấy dùng được. Lưu ở Docs/hd.md.",
        "constraints": [], "budget_calls": 4, "hold_until": (1_800_000_000.0 + 900) if hold else None,
        "proposal": {"understanding": "Bản hướng dẫn", "relevant_quote": "Em lo giúp anh bản hướng dẫn",
                     "mode": "achieve", "stage": "delivery",
                     "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"},
                     "criteria": [{"description": "Có mục Lỗi hay gặp", "evaluator": "artifact_contract",
                                   "params": {"path": _DL, "must_contain": ["Lỗi hay gặp"]}},
                                  {"description": "Anh xác nhận", "evaluator": "human_confirmation"}]}},
        R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=_ST)))


_saved = []


def _pres(ok=True):
    def _f(src, label):
        _saved.append(label)
        return {"ok": ok, "sha256": "x", "saved": label}
    return _f


g = _goal(1)
act = _ST.begin_action(_P, g.id, g.revision, "work", lease_until=9e18, now=1.0, intent={})
Path(g.output_root).mkdir(parents=True, exist_ok=True)
(Path(g.output_root) / f"{act['id']}.md").write_text("bản việc nền đã ghi, chưa có receipt", encoding="utf-8")
_saved.clear()
res, ok = H.preserve_work_outputs(_ST, _P, g.id, _DL, "out.json", _pres())
it = res["items"][0]
check("P2-1 action đang chạy, chưa receipt, file đã ghi: VẪN được lưu, nhãn unverified, không nâng thành succeeded",
      ok and it["verified"] is False and it["status"] == "running" and _saved and _saved[0].endswith("-unverified"))
check("P2-1 lưu bản chưa receipt thất bại: không cho dọn sandbox",
      H.preserve_work_outputs(_ST, _P, g.id, _DL, "out.json", _pres(ok=False))[1] is False)
check("P2-1 thiếu nơi lưu báo cáo: không cho dọn sandbox", H.preserve_work_outputs(_ST, _P, g.id, _DL, "", _pres())[1]
      is False)
(Path(g.output_root) / "le-loi.md").write_text("đầu ra không gắn action nào", encoding="utf-8")
_saved.clear()
res, ok = H.preserve_work_outputs(_ST, _P, g.id, _DL, "out.json", _pres())
check("P2-1 file .md lạc trong vùng làm việc cũng được lưu (orphan, unverified)",
      ok and any(x.get("status") == "orphan" for x in res["items"]) and any("orphan" in x for x in _saved))
g2 = _goal(2)
a2 = _ST.begin_action(_P, g2.id, g2.revision, "work", lease_until=9e18, now=1.0, intent={})
_ST.finish_action(_P, a2["id"], "succeeded", {"output_ref": str(Path(g2.output_root) / "khong-co.md"),
                                              "status": "succeeded"})
check("P2-1 đối chứng: action succeeded mà không thấy file thì không cho dọn",
      H.preserve_work_outputs(_ST, _P, g2.id, _DL, "out.json", _pres())[1] is False)

# P2-2: hợp đồng giai đoạn có bản tiếp nhận (lý do sửa đọc từ intent.last_verdict của từng lượt việc nền).
def _a(why, status="succeeded"):
    return {"intent": {"last_verdict": why}, "receipt": {"status": status}}


C = H.adoption_contract
check("P2-2 bản đạt, 0 lượt việc nền: đạt", C([], 1)[0])
check("P2-2 việc nền chạy khi bản đã đạt (lý do unknown): bác, làm lại vô ích", not C([_a("unknown")], 1)[0])
check("P2-2 bản chưa đạt, việc nền sửa một lượt (lý do not_met) thành công trong trần: ĐẠT", C([_a("not_met")], 1)[0])
check("P2-2 số lượt sửa vượt phần trần còn lại: bác", not C([_a("not_met"), _a("not_met")], 1)[0])
check("P2-2 lượt sửa không có receipt succeeded: bác", not C([_a("not_met", "failed")], 1)[0])
check("P2-2 một lượt có lý do, một lượt không: bác", not C([_a("not_met"), _a("met")], 2)[0])


# Đúng đường sản phẩm (ca review tái hiện): bản chat BAD được tiếp nhận, việc nền sửa một lượt rồi chờ người dùng.
class _Eng:
    max_wall_s = None
    queries = 0

    def is_available(self):
        return True

    async def query(self, prompt):
        _Eng.queries += 1
        yield {"type": "final", "content": "# HD\n\n1. Đếm.\n\n## Lỗi hay gặp\n\n- Ký sớm.\n"}


class _Ev:
    items = {}

    def put(self, goal, aid, text, meta):
        k = f"ev{len(self.items) + 1}"
        self.items[k] = {"text": text, "content_hash": R._sha(text.encode("utf-8"))}
        return k

    def valid(self, k):
        return self.items.get(k)


async def _nt(goal, kind, text, card=""):
    return True


g3 = _goal(3, hold=True)
_mref = R.message_ref("s", 3)
(_B / "Docs").mkdir(exist_ok=True)
(_B / _DL).write_text("# HD\n\n1. Đếm.\n", encoding="utf-8")
R.note_turn_event(_mref, str(_B), {"type": "tool_call", "name": "Write", "id": "w1",
                                   "input": {"file_path": str(_B / _DL), "content": "# HD\n\n1. Đếm.\n"}})
R.note_turn_event(_mref, str(_B), {"type": "tool_result", "tool_use_id": "w1", "is_error": False})
_d = R.GoalDeps(engine_factory=lambda s, t: (_Eng(), {"provider": "fake", "text_only": True}), budget=R.CallBudget(0),
                clock=lambda: 1_800_000_000.0, store=_ST, principal=_P, brain_root=str(_B), evidence=_Ev(), notify=_nt)
check("P2-2 sản phẩm: bản chat chưa đạt được tiếp nhận", R.handoff_after_turn(g3.id, _mref, _d) == "adopted")
asyncio.run(R.advance(g3.id, {"kind": "wake"}, _d))
_acts = [x for x in _ST.actions(_P, g3.id) if x["kind"] == "work" and x["revision"] == g3.revision]
_ass = [x for x in _ST.assessments(_P, g3.id) if int(x.get("revision") or 0) == g3.revision]
check("P2-2 sản phẩm: việc nền sửa đúng một lượt rồi chờ người dùng",
      _Eng.queries == 1 and len(_acts) == 1 and (_ST.run_state(_P, g3.id) or {}).get("block_reason") == "human_confirmation")
check("P2-2 hợp đồng bộ chạy CHẤP NHẬN đường sửa hợp lệ này (trước đây bị bác nhầm)", C(_acts, 1)[0])

print(f"\n{'FAIL' if _fails else 'OK'}: {len(_fails)} lỗi")
raise SystemExit(1 if _fails else 0)
