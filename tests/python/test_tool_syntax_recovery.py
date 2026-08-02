"""Cứu lượt chat khi model YẾU bịa sai cú pháp gọi công cụ.

    python tests/run.py tool_syntax_recovery

Lỗi thật chủ repo gặp với Groq llama-3.3-70b-versatile:

    Groq 400: {"error":{"message":"Failed to call a function. Please adjust your prompt.
    See 'failed_generation' for more details.","code":"tool_use_failed",
    "failed_generation":"<function=javis_search_tools({\\"query\\": \\"nao dang duoc dung\\"}\\"</function>"}}

Model tự phát cú pháp riêng thay vì JSON tool_calls chuẩn. Người dùng thấy một khối JSON lỗi
rồi "(không có nội dung trả về)" - tệ hơn hẳn một câu trả lời thiếu công cụ.

LIÊN ĐỚI: chính việc đưa builtin vào tầng lazy (0.10.0) làm lỗi này hay xảy ra hơn. Trước đó
`javis_search_tools` chỉ xuất hiện khi có trên 40 tool MCP; giờ nó luôn có mặt, nên model yếu
gặp nó mọi lượt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-toolsyn-"))

import engine  # noqa: E402
import limit_learner  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Nhận ra ĐÚNG lỗi này, nguyên văn từ chủ repo ----
_real = ('{"error":{"message":"Failed to call a function. Please adjust your prompt. '
         'See \'failed_generation\' for more details.","type":"invalid_request_error",'
         '"code":"tool_use_failed","failed_generation":"<function=javis_search_tools('
         '{\\"query\\": \\"nao dang duoc dung\\"}\\"</function>"}}')
check("nhận ra lỗi model bịa cú pháp gọi tool",
      engine._is_tool_syntax_failure(_real) is True)
check("nhận ra qua mã code", engine._is_tool_syntax_failure('{"code":"tool_use_failed"}'))
check("không phân biệt hoa thường",
      engine._is_tool_syntax_failure("TOOL_USE_FAILED"))

# ---- 2. KHÔNG nhận nhầm các lỗi 400 khác ----
# 400 còn dùng cho cả chục lỗi mà thử lại chỉ tổ tốn thêm một lượt để nhận đúng lỗi đó.
check("model không tồn tại KHÔNG phải lỗi cú pháp tool",
      engine._is_tool_syntax_failure('{"error":{"message":"model not found"}}') is False)
check("thiếu tham số KHÔNG phải lỗi cú pháp tool",
      engine._is_tool_syntax_failure('{"error":{"message":"messages is required"}}') is False)
check("sai khoá API KHÔNG phải lỗi cú pháp tool",
      engine._is_tool_syntax_failure('{"error":{"message":"invalid api key"}}') is False)
check("body rỗng → False", engine._is_tool_syntax_failure("") is False)
check("body None → False", engine._is_tool_syntax_failure(None) is False)

# Và tuyệt đối không được lẫn với lỗi hạn mức - hai thứ cần hai cách xử lý khác hẳn.
_groq429 = ('on tokens per minute (TPM): Limit 12000, Used 8812, Requested 4701. '
            'Please try again in 7.5s.')
check("lỗi hạn mức KHÔNG bị nhận nhầm thành lỗi cú pháp tool",
      engine._is_tool_syntax_failure(_groq429) is False)
check("lỗi cú pháp tool KHÔNG bị nhận nhầm thành lỗi hạn mức",
      limit_learner.parse_limit_error(400, _real) is None)

# ---- 3. Đường cứu hộ phải có thật trong vòng gọi tool ----
_eng = (ROOT / "server" / "engine.py").read_text(encoding="utf-8")
check("vòng gọi tool có đếm số lần model vấp", "tool_fumbles" in _eng)
check("nấc 1: thử lại y nguyên (sinh chữ ngẫu nhiên, lần sau thường trúng)",
      "if _is_tool_syntax_failure(body_text) and tool_fumbles < 2:" in _eng)
check("nấc 2: BỎ TOOL để cứu lấy câu trả lời", "tools = []" in _eng)
check("nấc 2: nói cho người dùng biết vì sao không dùng công cụ",
      "javis_no_tools" in _eng)
check("có trần, không thử lại vô hạn", "tool_fumbles < 2" in _eng)

# Hai bẫy khi bỏ tool giữa chừng, cả hai đều làm request sau 400 ngay:
check("bỏ tool thì KHÔNG gửi khoá tools rỗng (vài endpoint từ chối)",
      "if tools:\n            payload[\"tools\"] = tools" in _eng)
# "requirement_pending = False" còn xuất hiện ở chỗ khác trong file, nên phải kiểm ĐÚNG khối
# cứu hộ chứ không đếm chuỗi rời - nếu không, gỡ dòng này ở đây mà test vẫn xanh.
_block = _eng[_eng.find("if _is_tool_syntax_failure(body_text)"):][:900]
check("bỏ tool thì thôi ép gọi tool đã gỡ (kiểm trong ĐÚNG khối cứu hộ)",
      "requirement_pending = False" in _block)
check("và chỗ dựng payload cũng chỉ ép khi còn tool",
      "if requirement_pending and tools:" in _eng)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_tool_syntax_recovery: tất cả pass")
