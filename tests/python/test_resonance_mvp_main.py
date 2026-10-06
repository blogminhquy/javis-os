"""Resonance M2: phần nối trong main.py. Phân nhánh sau lượt và dòng gợi ý trong system prompt.

    python tests/run.py resonance_mvp_main -v

Brain chưa bật thì không có gì chạy, không tạo kho, prompt không dài thêm chữ nào.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m2m-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import luot_dang_chay  # noqa: E402
import plugins_host  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import asyncio  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-m-")).resolve())
USER = "Theo dõi giúp anh thư mục Inbox, mỗi khi có ghi chú mới thì gom vào bản tổng hợp."
SID, MID = "sess_m2", 7

# ───────────── brain chưa bật ─────────────
check("tắt: _resonance_after_turn không làm gì", main._resonance_after_turn(SID, BRAIN, MID, time.time(), None) is None)
check("tắt: không tạo kho resonance.sqlite3", not (Path(_STATE) / "resonance.sqlite3").exists())
p_off = main.build_system_prompt(BRAIN)
check("tắt: system prompt không nhắc javis_goal", "javis_goal" not in p_off)

# ───────────── bật ─────────────
(Path(BRAIN) / "Javis").mkdir(parents=True, exist_ok=True)
(Path(BRAIN) / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
p_on = main.build_system_prompt(BRAIN)
check("bật: system prompt có dòng gợi ý javis_goal", "javis_goal op=create" in p_on)
check("bật: dòng gợi ý ngắn (dưới 450 ký tự)", 0 < len(p_on) - len(p_off) < 450)

t0 = time.time() - 1
d = main._resonance_after_turn(SID, BRAIN, MID, t0, None)
check("bật, lượt không gọi tool: answer_now", d is not None and d.kind == "answer_now")
check("không có id tin nhắn thì không phân nhánh", main._resonance_after_turn(SID, BRAIN, 0, t0, None) is None)

# Bộ não gọi javis_goal trong lượt (như engine sẽ gọi qua hub), rồi main phân nhánh sau lượt
k = luot_dang_chay.bat_dau(f"{main.WEB_CHAT_PREFIX}{SID}", BRAIN, msg_id=MID, user_text=USER)
tools, route = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
out = asyncio.run(route["javis_goal"]["call"]({
    "op": "create", "understanding": "Bản tổng hợp ghi chú mới trong Inbox",
    "criteria": [{"description": "Bản tổng hợp có mặt", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/tong-hop.md"}}],
    "relevant_quote": "mỗi khi có ghi chú mới thì gom vào bản tổng hợp",
    "horizon": {"kind": "event", "event": "có ghi chú mới trong Inbox"}, "mode": "maintain"}))
luot_dang_chay.ket_thuc(k)
check("tool trong lượt: lập được mục tiêu", "Đã lập mục tiêu" in out)
d = main._resonance_after_turn(SID, BRAIN, MID, t0, None)
check("sau lượt có lập mục tiêu: create_goal", d is not None and d.kind == "create_goal" and d.goal_id)
g = main._resonance_store().get(RS.Principal("owner", "owner", main._brain_key(BRAIN)), d.goal_id)
check("mục tiêu thuộc đúng brain theo _brain_key", g is not None and g.request_ref == R.message_ref(SID, MID))
check("vùng đầu ra nằm trong brain", Path(g.output_root).resolve().is_relative_to(Path(BRAIN)))

# Việc Kanban giao trong lượt cho đúng khung chat
tid = main.tasks_feature.store.enqueue(BRAIN, "Gom ghi chú", "gom", chat_id=f"{main.WEB_CHAT_PREFIX}{SID}")
check("tạo được việc Kanban thử", bool(tid))
d2 = main._resonance_after_turn(SID, BRAIN, MID + 1, t0, None)
check("lượt giao việc Kanban cho đúng khung chat: task_now", d2 is not None and d2.kind == "task_now")
d3 = main._resonance_after_turn(SID, BRAIN, MID + 2, time.time() + 5, None)
check("việc Kanban tạo trước lượt không tính", d3 is not None and d3.kind == "answer_now")

# Lỗi trong khâu phân nhánh không được làm hỏng lượt chat
_old = main._resonance_store
main._resonance_store = lambda: (_ for _ in ()).throw(RuntimeError("kho hỏng"))
try:
    check("kho lỗi: _resonance_after_turn nuốt lỗi, trả None", main._resonance_after_turn(SID, BRAIN, 99, t0, None) is None)
finally:
    main._resonance_store = _old

# ───────────── M3: cổng bằng chứng thật và nhịp scheduler ─────────────
_g_ev = R.GoalRecord(id="g_evtest", brain_id=BRAIN, owner="javis", revision=1, output_root=BRAIN, session_id=SID)
try:
    _eid = main._RESONANCE_EVIDENCE.put(_g_ev, "act_evtest01", "Nội dung bằng chứng thử", {"kind": "test"})
    _back = main._RESONANCE_EVIDENCE.valid(_eid)
    check("M3 cổng bằng chứng: ghi vào EvidenceStore thật rồi đọc lại đúng nội dung và hash",
          _back is not None and _back["text"] == "Nội dung bằng chứng thử"
          and _back["content_hash"] == __import__("hashlib").sha256("Nội dung bằng chứng thử".encode()).hexdigest())
except RuntimeError as _e:
    # Máy không có khoá mã hoá hoặc runtime tắt: put phải ném lỗi rõ, Resonance coi như chưa có bằng chứng.
    check(f"M3 cổng bằng chứng: không có mã hoá/runtime thì ném lỗi rõ ({_e})", "unavailable" in str(_e)
          or "disabled" in str(_e))
check("M3 cổng bằng chứng: id lạ thì không có gì", main._RESONANCE_EVIDENCE.valid("ev_khong_co") is None)
_dp = main._resonance_deps(main._brain_key(BRAIN))
check("M3 _resonance_deps: principal là agent của đúng brain, engine là engine Resonance chỉ chữ",
      _dp is not None and _dp.principal.brain_id == main._brain_key(BRAIN) and _dp.principal.kind == "agent"
      and _dp.engine_factory is main._resonance_engine and _dp.brain_root == main._brain_key(BRAIN))
check("M3 _resonance_deps: brain không tồn tại thì không dựng", main._resonance_deps(str(Path(BRAIN) / "khong-co")) is None)

# Một mục tiêu đi trọn vòng trên host: tool tạo -> tick nền làm -> sản phẩm vào brain -> báo đúng khung chat.
_USER3 = "Viết giúp anh ghi chú Inbox/tom-tat.md tóm tắt ba việc: gọi thợ máy lạnh, nộp báo cáo quý, mua quà cho mẹ."
_k3 = luot_dang_chay.bat_dau(f"{main.WEB_CHAT_PREFIX}{SID}", BRAIN, msg_id=301, user_text=_USER3)
_out3 = asyncio.run(route["javis_goal"]["call"]({
    "op": "create", "understanding": "Ghi chú tóm tắt ba việc trong Inbox",
    "criteria": [{"description": "Ghi chú có đủ ba việc", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/tom-tat.md", "must_contain": ["máy lạnh", "báo cáo quý", "quà"]}}],
    "relevant_quote": "Viết giúp anh ghi chú Inbox/tom-tat.md",
    "horizon": {"kind": "review", "at_iso": "2027-01-01T09:00:00+07:00"}, "mode": "achieve"}))
luot_dang_chay.ket_thuc(_k3)
check("M3 lời dặn của tool: nói rõ làm tiếp ở nền và kết quả tự về khung chat", "làm tiếp ở NỀN" in _out3)
_g3 = main._resonance_store().find_by_key(RS.Principal("agent", "javis", main._brain_key(BRAIN)),
                                         R.message_ref(SID, 301))
_calls, _sent = {"n": 0}, []


class _Eng:
    max_wall_s = None

    def is_available(self):
        return True

    async def query(self, prompt):
        _calls["n"] += 1
        yield {"type": "final", "content": "# Tóm tắt\n\n- Nộp báo cáo quý\n- Gọi thợ máy lạnh\n- Mua quà cho mẹ\n"}


async def _fake_notify(owner_chat, text, **kw):
    _sent.append((owner_chat, text))
    return True, ""

_old_eng, _old_notify = main._resonance_engine, main._notify_owner
main._resonance_engine = lambda s, t="resonance": (_Eng(), {"provider": "fake", "text_only": True})
main._notify_owner = _fake_notify
try:
    asyncio.run(main._resonance_tick())
finally:
    main._resonance_engine, main._notify_owner = _old_eng, _old_notify
_g3b = main._resonance_store().get(RS.Principal("agent", "javis", main._brain_key(BRAIN)), _g3.id)
_P3 = RS.Principal("agent", "javis", main._brain_key(BRAIN))
check("M3 trọn vòng: mục tiêu này được làm đúng một lượt engine (tick cũng làm mục tiêu khác đang tới hạn)",
      len([x for x in main._resonance_store().actions(_P3, _g3.id) if x["kind"] == "work"]) == 1)
check("M3 trọn vòng: sản phẩm nằm đúng chỗ trong brain", (Path(BRAIN) / "Inbox" / "tom-tat.md").is_file())
check("M3 trọn vòng: mục tiêu thành công sau khi host kiểm bằng chứng", _g3b.status == "succeeded")
check("M3 trọn vòng: báo về ĐÚNG khung chat web của phiên đã giao, có link sản phẩm",
      any(c == f"{main.WEB_CHAT_PREFIX}{SID}" and "Inbox/tom-tat.md" in t for c, t in _sent))
_calls["n"] = 0
main._resonance_engine = lambda s, t="resonance": (_Eng(), {"provider": "fake", "text_only": True})
try:
    asyncio.run(main._resonance_tick())
finally:
    main._resonance_engine = _old_eng
check("M3 trọn vòng: nhịp sau không có gì tới hạn thì không gọi engine", _calls["n"] == 0)

# ───────────── mọi nhánh web mang id tin gốc tới run_turn (review PR #567, P2-1) ─────────────
# run_turn nằm trong closure của websocket nên không gọi thẳng được; kiểm bằng AST các chỗ gọi nó.
import ast  # noqa: E402

_tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
_fns = {n.name: n for n in ast.walk(_tree) if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))}


def _calls(node, name):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == name]


def _kw(call, name):
    return next((k.value for k in call.keywords if k.arg == name), None)


_voice = _calls(_fns["run_voice_turn"], "run_turn")
check("giọng nói chuyển bộ não chính: mọi lời gọi run_turn đều truyền user_mid",
      len(_voice) >= 2 and all(_kw(c, "user_mid") is not None for c in _voice))
_goc = [c for c in _voice if any(isinstance(a, ast.BinOp) for a in c.args)]
check("đường giữ câu gốc: user_text là lời người dùng, không kèm ghi chú câu nghe của host",
      len(_goc) == 1 and _kw(_goc[0], "user_text") is not None
      and "GHI_CHU_CAU_NGHE" not in ast.unparse(_kw(_goc[0], "user_text")))
_resume = _calls(_fns["_start_resumed_turn"], "run_turn")
check("chạy lại sau hạn mức: truyền đúng user_mid và user_text của lượt gốc",
      len(_resume) == 1 and ast.unparse(_kw(_resume[0], "user_mid")) == "user_mid"
      and ast.unparse(_kw(_resume[0], "user_text")) == "user_text")
_sched = _calls(_fns["_do_turn"], "_start_resumed_turn")
check("hẹn chạy lại mang theo id và lời người dùng của lượt gốc",
      len(_sched) == 1 and _kw(_sched[0], "user_mid") is not None and _kw(_sched[0], "user_text") is not None)
_ws = _fns["_start_resumed_turn"]
_handler = next(n for n in ast.walk(_tree) if isinstance(n, ast.AsyncFunctionDef)
                and any(f is _ws for f in ast.walk(n)) and n is not _ws)
_direct = [c for c in _calls(_handler, "run_turn")
           if not any(c in list(ast.walk(f)) for f in ast.walk(_handler)
                      if isinstance(f, ast.AsyncFunctionDef) and f is not _handler)]
check("khung chat web (thường và trả lời trong phiên quy trình): run_turn nhận user_mid=_user_mid",
      len(_direct) >= 2 and all(ast.unparse(_kw(c, "user_mid") or ast.Constant(0)) == "_user_mid" for c in _direct))
_vt = _calls(_handler, "run_voice_turn")
check("khung chat web: làn nhanh giọng nói nhận user_mid=_user_mid",
      len(_vt) == 1 and ast.unparse(_kw(_vt[0], "user_mid") or ast.Constant(0)) == "_user_mid")
_follow = _calls(_fns["_start_followup_turn"], "run_turn")
check("lượt nối tiếp do host tự mở (chữ của host) KHÔNG mang id tin người dùng",
      len(_follow) == 1 and _kw(_follow[0], "user_mid") is None)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
