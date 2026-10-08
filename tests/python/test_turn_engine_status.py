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
check("đối chứng: lượt thành công: ok, không chi tiết lỗi", outcome([f_ok]) == {"engine_status": "ok", "engine_error": None})
check("kết cục được xoá sau khi gửi (không rò sang lượt sau)", main._engine_outcome_pop("conv-test")["engine_status"]
      == "unknown")

# Đường nối trong main: run_turn đặt lại đầu lượt, gửi kèm turn_done; nhánh Claude ghi final và error.
src = Path(main.__file__).read_text(encoding="utf-8")
tree = ast.parse(src)
fns = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))}
rt = ast.get_source_segment(src, fns["run_turn"]) or ""
check("run_turn: đặt lại kết cục engine trước khi chạy lượt", "_engine_outcome_reset(conv_sid)" in rt)
check("run_turn: ngoại lệ được ghi vào kết cục", "_engine_outcome_exception(conv_sid, e)" in rt)
check("run_turn: turn_done gửi kèm engine_status", "**_engine_outcome_pop(conv_sid)" in rt
      and rt.index("_engine_outcome_pop") > rt.index('"turn_done"'))
cc = ast.get_source_segment(src, fns["_consume_claude"]) or ""
check("nhánh Claude: ghi final và error vào kết cục engine",
      'elif etype in ("final", "error"):' in cc and "_engine_outcome_note(conv_sid, event)" in cc)

print(f"\n{'FAIL' if _fails else 'OK'}: {len(_fails)} lỗi")
raise SystemExit(1 if _fails else 0)
