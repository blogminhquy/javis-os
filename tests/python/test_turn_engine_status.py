"""Kết cục ENGINE của lượt chat đi kèm `turn_done` (pilot Resonance lần 4).

    python tests/run.py turn_engine_status -v

Lần 4: Claude Code không làm mới được token đăng nhập ("Failed to refresh OAuth token: another Claude Code process is
refreshing it..."). Câu lỗi đi ra như một câu trả lời thường, rồi `turn_done`, không có khung `error`; bộ chạy pilot
tưởng bộ não đã chạy mà không lập mục tiêu. Sửa: mapper SDK giữ `is_error`, `subtype` và cờ cuộc đua token; main ghi kết
cục engine của lượt và gửi kèm `turn_done` thành `engine_status` ("ok" | "error" | "unknown"). Không gọi model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-turn-engine-"))

import claude_sdk_engine  # noqa: E402
import claude_token_gate  # noqa: E402
import main  # noqa: E402
from claude_agent_sdk import ResultMessage  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


OAUTH = ("Failed to refresh OAuth token: another Claude Code process is refreshing it or exited mid-refresh. "
         "This is usually transient; retry in a minute, and if it persists close other Claude Code processes or "
         "sign in again")


def result(text, is_error, subtype="success"):
    return ResultMessage(subtype=subtype, duration_ms=10, duration_api_ms=0, is_error=is_error, num_turns=1,
                         session_id="sess", total_cost_usd=0.0, usage={}, result=text)


def final_of(msg):
    return [e for e in claude_sdk_engine.map_message(msg)[0] if e["type"] == "final"][0]


def outcome(events, exc=None):
    sid = "conv-test"
    main._engine_outcome_reset(sid)
    for e in events:
        main._engine_outcome_note(sid, e)
    if exc is not None:
        main._engine_outcome_exception(sid, exc)
    return main._engine_outcome_pop(sid)


# Bộ nhận dạng cuộc đua làm mới token: hẹp.
check("nhận đúng câu đua token của Claude Code bản mới", claude_token_gate.la_loi_tranh_lam_moi(OAUTH))
check("vẫn nhận mẫu cũ 'already used'", claude_token_gate.la_loi_tranh_lam_moi("Refresh token already used"))
check("lỗi thô của lần 4 neo ở đầu; câu trích lỗi ở giữa thì không phải lỗi thô",
      claude_token_gate.la_loi_tho_tranh_lam_moi("  " + OAUTH)
      and not claude_token_gate.la_loi_tho_tranh_lam_moi("Claude Code báo: " + OAUTH))
check("không nhận câu có chữ OAuth hay refresh trơn",
      not claude_token_gate.la_loi_tranh_lam_moi("Anh muốn refresh lại OAuth token của Gmail không?")
      and not claude_token_gate.la_loi_tranh_lam_moi("OAuth token could not be refreshed"))

# Mapper SDK thật: final mang cờ máy đọc được.
f_err = final_of(result(OAUTH, True))
check("mapper: lỗi đăng nhập có is_error: final mang is_error và cờ đua token",
      f_err["is_error"] is True and f_err["auth_refresh_race"] is True)
f_txt = final_of(result(OAUTH, False))
check("mapper: câu đua token mà CLI không cắm is_error: vẫn mang cờ đua token",
      f_txt["is_error"] is False and f_txt["auth_refresh_race"] is True)
f_ok = final_of(result("Bản đầu đã xong.", False))
check("mapper: trả lời thường: không cờ lỗi", f_ok["is_error"] is False and f_ok["auth_refresh_race"] is False)

# Review sửa pilot 4, P2-1: câu trả lời THÀNH CÔNG không được bị coi là lỗi đăng nhập.
_real_login = claude_token_gate.con_dang_nhap
claude_token_gate.con_dang_nhap = lambda: True          # ca tệ nhất: còn đăng nhập (nhánh dua_token cũ cũng bật)
try:
    for label, text in (("câu thường có chữ 'already used'",
                         "I have already used the supplied notes to prepare the checklist."),
                        ("câu đang GIẢI THÍCH và trích lỗi OAuth",
                         "Lượt trước lỗi vì Claude Code báo: " + OAUTH + ". Em đã viết lại bản hướng dẫn."),
                        ("câu đầu là tiêu đề, lỗi chỉ được nhắc ở sau",
                         "# Hướng dẫn\n\nGhi chú: " + OAUTH)):
        f = final_of(result(text, False))
        check(f"P2-1 {label}, is_error=False: không cờ đua token, nội dung giữ nguyên, engine_status ok",
              f["auth_refresh_race"] is False and f["dua_token"] is False and f["content"] == text
              and outcome([f])["engine_status"] == "ok")
    f_raw = final_of(result(OAUTH, False))
    check("P2-1 lỗi thô của lần 4 (mở đầu bằng thông báo CLI), không is_error: vẫn bị chặn",
          f_raw["auth_refresh_race"] is True and outcome([f_raw])["engine_status"] == "error")
    f_old = final_of(result("OAuth refresh token was already used by another request", True))
    check("P2-1 lỗi cũ 'refresh token ... already used' có is_error: vẫn nhận là đua token",
          f_old["auth_refresh_race"] is True and outcome([f_old])["engine_status"] == "error")
    f_old_ok = final_of(result("OAuth refresh token was already used by another request", False))
    check("P2-1 cùng câu cũ nhưng CLI báo thành công: không tự suy ra lỗi", f_old_ok["auth_refresh_race"] is False)
finally:
    claude_token_gate.con_dang_nhap = _real_login

# Kết cục engine của lượt.
check("lần 4: final lỗi đăng nhập (có chữ) rồi turn_done: engine_status error",
      outcome([{"type": "text", "content": OAUTH}, f_err])["engine_status"] == "error")
check("lần 4: CLI không cắm is_error nhưng là câu đua token: vẫn error (dự phòng hẹp)",
      outcome([f_txt])["engine_status"] == "error")
check("khung error rồi final thường: error", outcome([{"type": "error", "content": "Claude hết lượt"}, f_ok])
      ["engine_status"] == "error")
check("mất mạch đã mồi lại rồi final thường: ok",
      outcome([{"type": "error", "resume_failed": True, "content": "mạch cũ mất"}, f_ok])["engine_status"] == "ok")
check("ngoại lệ trong lượt: error", outcome([], exc=TimeoutError("hết giờ"))["engine_status"] == "error")
o = outcome([])
check("không có final (hết giờ, bị huỷ, nhánh engine chưa báo): unknown",
      o["engine_status"] == "unknown" and o["engine_error"] == {"source": "no_final"})
check("đối chứng: lượt thành công: ok, không chi tiết lỗi, lượt hoàn tất",
      outcome([f_ok]) == {"engine_status": "ok", "engine_error": None, "turn_status": "completed"})
check("kết cục được xoá sau khi gửi (không rò sang lượt sau)", main._engine_outcome_pop("conv-test")["engine_status"]
      == "unknown")

# Review sửa pilot 4, P2-2: chạy THÂN THẬT của run_turn (trích từ main.py) với dịch vụ giả, huỷ trước và sau final.
import asyncio  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import uuid  # noqa: E402
import localefmt  # noqa: E402
import luot_dang_chay  # noqa: E402
import nghe_sua  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import _e2e_achieve_harness as H  # noqa: E402
import _e2e_pilot_guard as G  # noqa: E402

frames = []


async def _send_raw(frame):
    frames.append(frame)


async def _noop(*a, **kw):
    pass


def _make_do_turn(mode):
    async def _do_turn(conv_sid, *a, **kw):
        if mode in ("ok", "cancel_after_final", "error_after_final"):
            main._engine_outcome_note(conv_sid, f_ok)
        if mode.startswith("cancel"):
            raise asyncio.CancelledError()
        if mode == "error_after_final":
            raise RuntimeError("lưu lượt hỏng")
        return "xong"
    return _do_turn


import turn_context  # noqa: E402  - run_turn gắn danh tính lượt cho hook tool (0.85.8)
_ns = dict(asyncio=asyncio, sys=sys, time=time, uuid=uuid, nghe_sua=nghe_sua, localefmt=localefmt, turn_context=turn_context,
           store=types.SimpleNamespace(), send_raw=_send_raw, _persist_turn=_noop,
           _CHAT_RUNTIME=types.SimpleNamespace(finish_job=lambda *a: None),
           context_runtime=types.SimpleNamespace(bind_trace=lambda *a: None, reset_trace=lambda *a: None,
                                                 event_fields=lambda *a: {}),
           _CONTEXT_RUNTIME=types.SimpleNamespace(finish=lambda *a: None, note_error=lambda *a: None),
           luot_dang_chay=luot_dang_chay, WEB_CHAT_PREFIX="web:", _brain_root=lambda b: b,
           _resonance_after_turn=lambda *a: None, _record_quality_shadow=lambda *a: None,
           tien_trinh_nen=types.SimpleNamespace(bo_tag=lambda *a: None),
           _engine_outcome_reset=main._engine_outcome_reset, _engine_outcome_exception=main._engine_outcome_exception,
           _engine_outcome_turn=main._engine_outcome_turn, _engine_outcome_pop=main._engine_outcome_pop)
_tree0 = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
_rt = next(n for n in ast.walk(_tree0) if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_turn")
exec(compile(ast.Module(body=[_rt], type_ignores=[]), "main-run_turn", "exec"), _ns)


def run_turn_as(mode):
    frames.clear()
    _ns["_do_turn"] = _make_do_turn(mode)
    try:
        asyncio.run(_ns["run_turn"]("conv-rt", "tin", "brain-x", "tag", None, user_mid=5, user_text="tin"))
    except asyncio.CancelledError:
        pass
    td = [f for f in frames if f.get("type") == "turn_done"]
    return td[-1] if td else {}, frames[:]


def through_gate(td):
    chk = H.Checks(echo=lambda *_: None)
    lg = G.TurnLedger(Path(tempfile.mkdtemp(prefix="rt-l-")) / "t.json", 2)
    try:
        H.chat_turn(chk, lg, "S1", lambda: ("sid", ["response", "turn_done"], [], "x", td))
        return True, chk
    except H.GateClosed:
        return False, chk


td, fr = run_turn_as("cancel_after_final")
check("P2-2 run_turn thật: huỷ SAU final: có tin 'Đã dừng', turn_done mang turn_status=cancelled",
      any(f.get("type") == "system" for f in fr) and td.get("turn_status") == "cancelled")
check("P2-2 huỷ sau final: engine_status vẫn nói thật là engine đã trả final (ok), nhưng lượt không hoàn tất",
      td.get("engine_status") == "ok")
ok_gate, chk = through_gate(td)
check("P2-2 huỷ sau final: cổng bộ chạy TỪ CHỐI, ghi lỗi kỹ thuật", not ok_gate and len(chk.fails) == 1)
td, _ = run_turn_as("cancel_before_final")
ok_gate, _ = through_gate(td)
check("P2-2 huỷ TRƯỚC final: engine unknown, lượt cancelled, cổng từ chối",
      td.get("engine_status") == "unknown" and td.get("turn_status") == "cancelled" and not ok_gate)
td, _ = run_turn_as("error_after_final")
ok_gate, _ = through_gate(td)
check("P2-2 ngoại lệ sau final: engine error, lượt failed, cổng từ chối",
      td.get("engine_status") == "error" and td.get("turn_status") == "failed" and not ok_gate)
td, _ = run_turn_as("ok")
ok_gate, chk = through_gate(td)
check("P2-2 đối chứng: lượt hoàn tất bình thường: ok/completed, cổng cho qua",
      td.get("engine_status") == "ok" and td.get("turn_status") == "completed" and ok_gate and not chk.fails)

# Đường nối trong main: run_turn đặt lại đầu lượt, gửi kèm turn_done; nhánh Claude ghi final và error.
src = Path(main.__file__).read_text(encoding="utf-8")
tree = ast.parse(src)
fns = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))}
rt = ast.get_source_segment(src, fns["run_turn"]) or ""
check("run_turn: đặt lại kết cục engine trước khi chạy lượt", "_engine_outcome_reset(conv_sid)" in rt)
check("run_turn: ngoại lệ được ghi vào kết cục", "_engine_outcome_exception(conv_sid, e)" in rt)
check("run_turn: huỷ được ghi vào kết cục lượt", '_engine_outcome_turn(conv_sid, "cancelled")' in rt)
check("run_turn: turn_done gửi kèm engine_status", "**_engine_outcome_pop(conv_sid)" in rt
      and rt.index("_engine_outcome_pop") > rt.index('"turn_done"'))
cc = ast.get_source_segment(src, fns["_consume_claude"]) or ""
check("nhánh Claude: ghi final và error vào kết cục engine",
      'elif etype in ("final", "error"):' in cc and "_engine_outcome_note(conv_sid, event)" in cc)

print(f"\n{'FAIL' if _fails else 'OK'}: {len(_fails)} lỗi")
raise SystemExit(1 if _fails else 0)
