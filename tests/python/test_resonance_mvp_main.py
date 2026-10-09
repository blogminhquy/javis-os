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

# ───────────── bật (A1: theo agent, trong lượt của agent đó) ─────────────
import _resonance_agent as RA  # noqa: E402
(Path(BRAIN) / "Javis").mkdir(parents=True, exist_ok=True)
(Path(BRAIN) / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
check("công tắc brain cũ bật mà chưa có agent nào: prompt vẫn không nhắc javis_goal (không còn cấp quyền)",
      "javis_goal" not in main.build_system_prompt(BRAIN))
AG = RA.enable(main._resonance_store(), BRAIN)


def in_turn(mid, text, fn):
    """Như run_turn: phần sau lượt chạy TRONG ngữ cảnh lượt của agent (bỏ ngữ cảnh ở finally)."""
    with RA.turn(AG, SID, mid, text, BRAIN):
        return fn()


p_on = in_turn(MID, USER, lambda: main.build_system_prompt(BRAIN))
check("bật: system prompt có dòng gợi ý javis_goal", "javis_goal op=create" in p_on)
# Trần nâng từ 450 lên 650 khi dòng gợi ý thêm ranh giới bốn loại việc và đường tìm tool theo engine.
check("bật: dòng gợi ý ngắn (dưới 650 ký tự)", 0 < len(p_on) - len(p_off) < 650)
check("ngoài lượt của agent: prompt không có dòng gợi ý lập mục tiêu",
      "javis_goal op=create" not in main.build_system_prompt(BRAIN))

t0 = time.time() - 1
d = in_turn(MID, USER, lambda: main._resonance_after_turn(SID, BRAIN, MID, t0, None))
check("bật, lượt không gọi tool: answer_now", d is not None and d.kind == "answer_now")
check("không có id tin nhắn thì không phân nhánh",
      in_turn(MID, USER, lambda: main._resonance_after_turn(SID, BRAIN, 0, t0, None)) is None)
check("lượt không thuộc agent (chat thường): không phân nhánh",
      main._resonance_after_turn(SID, BRAIN, MID, t0, None) is None)

# Bộ não gọi javis_goal trong lượt (như engine sẽ gọi qua hub), rồi main phân nhánh sau lượt
tools, route = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
out = in_turn(MID, USER, lambda: asyncio.run(route["javis_goal"]["call"]({
    "op": "create", "understanding": "Bản tổng hợp ghi chú mới trong Inbox",
    "criteria": [{"description": "Bản tổng hợp có mặt", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/tong-hop.md"}}],
    "relevant_quote": "mỗi khi có ghi chú mới thì gom vào bản tổng hợp",
    "horizon": {"kind": "event", "event": "có ghi chú mới trong Inbox"}, "mode": "maintain"})))
check("tool trong lượt: lập được mục tiêu", "Đã lập mục tiêu" in out)
d = in_turn(MID, USER, lambda: main._resonance_after_turn(SID, BRAIN, MID, t0, None))
check("sau lượt có lập mục tiêu: create_goal", d is not None and d.kind == "create_goal" and d.goal_id)
_wk = [w for w in main._resonance_store().wakes(RS.Principal("agent", "javis", main._brain_key(BRAIN)), d.goal_id)
       if w["kind"] == "work"]
check("bàn giao cuối lượt: nhả lịch việc nền đã giữ khi lập trong lượt chat (đánh giá ngay)",
      bool(_wk) and _wk[0]["due_at"] <= time.time() + 1)
g = main._resonance_store().get(RS.Principal("owner", "owner", main._brain_key(BRAIN)), d.goal_id)
check("mục tiêu thuộc đúng brain theo _brain_key", g is not None and g.request_ref == R.message_ref(SID, MID))
check("A1: mục tiêu gắn đúng agent của lượt", g is not None and g.agent_key == AG["agent_key"])
check("vùng đầu ra nằm trong brain", Path(g.output_root).resolve().is_relative_to(Path(BRAIN)))

# Việc Kanban giao trong lượt cho đúng khung chat
tid = main.tasks_feature.store.enqueue(BRAIN, "Gom ghi chú", "gom", chat_id=f"{main.WEB_CHAT_PREFIX}{SID}")
check("tạo được việc Kanban thử", bool(tid))
d2 = in_turn(MID + 1, "x", lambda: main._resonance_after_turn(SID, BRAIN, MID + 1, t0, None))
check("lượt giao việc Kanban cho đúng khung chat: task_now", d2 is not None and d2.kind == "task_now")
d3 = in_turn(MID + 2, "x", lambda: main._resonance_after_turn(SID, BRAIN, MID + 2, time.time() + 5, None))
check("việc Kanban tạo trước lượt không tính", d3 is not None and d3.kind == "answer_now")

# Lỗi trong khâu phân nhánh không được làm hỏng lượt chat
_old = main._resonance_store
main._resonance_store = lambda: (_ for _ in ()).throw(RuntimeError("kho hỏng"))
try:
    check("kho lỗi: _resonance_after_turn nuốt lỗi, trả None",
          in_turn(99, "x", lambda: main._resonance_after_turn(SID, BRAIN, 99, t0, None)) is None)
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
_out3 = in_turn(301, _USER3, lambda: asyncio.run(route["javis_goal"]["call"]({
    "op": "create", "understanding": "Ghi chú tóm tắt ba việc trong Inbox",
    "criteria": [{"description": "Ghi chú có đủ ba việc", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/tom-tat.md", "must_contain": ["máy lạnh", "báo cáo quý", "quà"]}}],
    "relevant_quote": "Viết giúp anh ghi chú Inbox/tom-tat.md",
    "horizon": {"kind": "review", "at_iso": "2027-01-01T09:00:00+07:00"}, "mode": "achieve"})))
check("M3 lời dặn của tool: nói rõ làm tiếp ở nền và kết quả tự về khung chat", "làm tiếp ở NỀN" in _out3)
_g3 = main._resonance_store().find_by_key(RS.Principal("agent", "javis", main._brain_key(BRAIN)),
                                         R.message_ref(SID, 301))
# Như run_turn: hết lượt thì bàn giao (lịch việc nền được giữ từ lúc tool lập mục tiêu tới đây).
_d3 = in_turn(301, _USER3, lambda: main._resonance_after_turn(SID, BRAIN, 301, time.time() - 1, None))
check("bàn giao lượt 301: không có Write nên không tiếp nhận, mục tiêu vẫn chờ việc nền làm",
      _d3 is not None and _d3.kind == "create_goal"
      and not [e for e in main._resonance_store().events(RS.Principal("agent", "javis", main._brain_key(BRAIN)),
                                                         _g3.id) if e["kind"] == "artifact_adopted"])

# Bộ não Write bản đạt ngay trong lượt rồi lập mục tiêu (pilot lần 3): sự kiện Write đi qua đúng helper các nhánh
# engine trong main gọi, bàn giao tiếp nhận, nhịp nền KHÔNG gọi engine cho mục tiêu này.
_USER4 = "Viết giúp anh ghi chú Inbox/ban-chat.md liệt kê hai việc: gọi thợ máy lạnh, nộp báo cáo quý."
_TXT4 = "# Việc\n\n- Gọi thợ máy lạnh\n- Nộp báo cáo quý\n"
_t4 = RA.turn(AG, SID, 302, _USER4, BRAIN)
_t4.__enter__()
main._resonance_note_write(SID, 302, BRAIN, {"type": "tool_call", "name": "Write", "id": "toolu_302",
                                             "input": {"file_path": str(Path(BRAIN) / "Inbox" / "ban-chat.md"),
                                                       "content": _TXT4}})
# Biên nhận chỉ thành khi có kết quả THÀNH CÔNG gắn đúng id lời gọi (review mã bàn giao, P1-1).
main._resonance_note_write(SID, 302, BRAIN, {"type": "tool_result", "tool_use_id": "toolu_302", "is_error": False,
                                             "content": "File created"})
(Path(BRAIN) / "Inbox").mkdir(parents=True, exist_ok=True)
(Path(BRAIN) / "Inbox" / "ban-chat.md").write_text(_TXT4, encoding="utf-8")
asyncio.run(route["javis_goal"]["call"]({
    "op": "create", "understanding": "Ghi chú hai việc trong Inbox",
    "criteria": [{"description": "Ghi chú có đủ hai việc", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/ban-chat.md", "must_contain": ["máy lạnh", "báo cáo quý"]}}],
    "relevant_quote": "Viết giúp anh ghi chú Inbox/ban-chat.md",
    "horizon": {"kind": "review", "at_iso": "2027-01-01T09:00:00+07:00"}, "mode": "achieve"}))
_P4 = RS.Principal("agent", "javis", main._brain_key(BRAIN))
_g4 = main._resonance_store().find_by_key(_P4, R.message_ref(SID, 302))
main._resonance_after_turn(SID, BRAIN, 302, time.time() - 1, None)
_t4.__exit__(None, None, None)
check("bàn giao lượt 302: bản Write trong lượt được tiếp nhận (sự kiện, bằng chứng chat_output)",
      _g4 is not None and [e["kind"] for e in main._resonance_store().events(_P4, _g4.id)].count("artifact_adopted") == 1
      and [x["kind"] for x in main._resonance_store().evidence_for(_P4, _g4.id, _g4.revision)] == ["chat_output"])
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
check("bản chat đã tiếp nhận: mục tiêu 302 đạt mà KHÔNG có lượt việc nền nào",
      main._resonance_store().get(_P4, _g4.id).status == "succeeded"
      and not [x for x in main._resonance_store().actions(_P4, _g4.id) if x["kind"] == "work"])
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
