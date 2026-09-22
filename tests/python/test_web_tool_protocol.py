"""Giao thức tool qua chữ cho engine Web: bóc khối, từ chối khuôn hỏng, KHÔNG đoán.

    python tests/run.py web_tool_protocol

ChatGPT Web không có function calling, nên khuôn tool là một quy ước bằng chữ và model có
thể phá nó theo đủ kiểu. Phép thử nặng nhất ở đây không phải "ca đẹp chạy được", mà là
**ca hỏng phải trả lỗi nói được chứ không được đoán**: đoán ý model một lần là có ngày ghi
nhầm file hoặc chạy nhầm lệnh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import web_tool_protocol as wtp  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def khoi(json_text):
    """Dựng một khối rào đúng chuẩn quanh đoạn JSON cho trước."""
    return "```" + wtp.FENCE + "\n" + json_text + "\n```"


# ---- 1. Ca đẹp ----

r = wtp.parse(khoi('{"calls": [{"name": "javis_read_file", "arguments": {"path": "a.py"}}]}'))
check("một tool: bóc đúng tên", r.is_tool and r.calls[0].name == "javis_read_file")
check("một tool: bóc đúng tham số", r.calls[0].arguments == {"path": "a.py"})
check("một tool: không phải final", not r.is_final and not r.is_error)

r = wtp.parse(khoi(
    '{"calls": ['
    '{"name": "javis_read_file", "arguments": {"path": "a.py"}},'
    '{"name": "javis_read_file", "arguments": {"path": "b.py"}},'
    '{"name": "javis_git_status", "arguments": {}}'
    ']}'))
check("gộp nhiều tool một vòng (đòn giảm thời gian chính)", len(r.calls) == 3)
check("giữ đúng thứ tự và index", [c.index for c in r.calls] == [0, 1, 2])
check("tool không tham số thì arguments rỗng", r.calls[2].arguments == {})

r = wtp.parse("Theo em thì lỗi nằm ở hàm login, vì nó không kiểm token hết hạn.")
check("không có khối = câu trả lời cuối", r.is_final and not r.is_tool)
check("final giữ nguyên chữ", "hàm login" in r.final_text)

r = wtp.parse("")
check("chuỗi rỗng không nổ, coi là final rỗng", r.is_final and r.final_text == "")


# ---- 2. Khoan dung ĐÚNG MỘT chỗ: thiếu lớp bọc 'calls' ----

r = wtp.parse(khoi('{"name": "javis_now", "arguments": {}}'))
check("thiếu lớp bọc 'calls' vẫn đọc được (cấu trúc vẫn tường minh)",
      r.is_tool and r.calls[0].name == "javis_now")


# ---- 3. Khuôn hỏng: PHẢI báo lỗi, KHÔNG được đoán ----

r = wtp.parse(khoi('{"calls": [{"name": "javis_read_file", "arguments": {"path": "a.py"'))
check("JSON cụt -> lỗi, không đoán", r.is_error)
check("lỗi JSON cụt có nhắc khuôn đúng", "calls" in r.error)
check("JSON cụt KHÔNG sinh lời gọi nào", not r.calls)

r = wtp.parse(khoi('{"calls": [{"arguments": {"path": "a.py"}}]}'))
check("thiếu 'name' -> lỗi", r.is_error and "name" in r.error)

r = wtp.parse(khoi('{"calls": [{"name": "", "arguments": {}}]}'))
check("name rỗng -> lỗi", r.is_error)

r = wtp.parse(khoi('{"calls": [{"name": "javis_run_command", "arguments": "rm -rf /"}]}'))
check("arguments là CHUỖI -> lỗi, tuyệt đối không tự dựng thành object", r.is_error)
check("lời gọi nguy hiểm sai khuôn KHÔNG lọt thành call", not r.calls)

r = wtp.parse(khoi('{"calls": "javis_now"}'))
check("'calls' không phải mảng -> lỗi", r.is_error)

r = wtp.parse(khoi('{"calls": []}'))
check("'calls' rỗng -> lỗi (muốn trả lời thì đừng gửi khối)", r.is_error)

r = wtp.parse(khoi('{"toi_muon": "doc file"}'))
check("thiếu hẳn 'calls' và 'name' -> lỗi", r.is_error and "calls" in r.error)

r = wtp.parse(khoi('["javis_now"]'))
check("khối là mảng chứ không phải object -> lỗi", r.is_error)


# ---- 4. Trần: chống một khối nuốt cả file, và chống gọi quá nhiều ----

qua_dai = khoi('{"calls": [{"name": "x", "arguments": {"noi_dung": "' + "A" * 25_000 + '"}}]}')
r = wtp.parse(qua_dai)
check("khối vượt trần ký tự -> lỗi", r.is_error and str(wtp.MAX_BLOCK_CHARS) in r.error)
check("khối vượt trần vẫn giữ mẩu nguyên văn để lần lại", bool(r.raw_block))
check("mẩu nguyên văn đã bị CẮT, không ôm cả 25k ký tự", len(r.raw_block) < 1000)

nhieu = ",".join('{"name": "javis_now", "arguments": {}}' for _ in range(wtp.MAX_CALLS + 1))
r = wtp.parse(khoi('{"calls": [' + nhieu + ']}'))
check("vượt trần số tool một vòng -> lỗi", r.is_error and str(wtp.MAX_CALLS) in r.error)


# ---- 5. Nhiều khối = model phân vân, không phải nhu cầu thật ----

hai = (khoi('{"calls": [{"name": "javis_now", "arguments": {}}]}') + "\nhoặc là\n"
       + khoi('{"calls": [{"name": "javis_read_file", "arguments": {"path": "a"}}]}'))
r = wtp.parse(hai)
check("hai khối -> lỗi, bảo gộp vào mảng calls", r.is_error and "MỘT khối" in r.error)
check("hai khối KHÔNG chọn bừa khối đầu", not r.calls)


# ---- 6. Rào sai tên: nhận diện để NHẮC, nhưng không bao giờ chạy ----

r = wtp.parse('```json\n{"calls": [{"name": "javis_now", "arguments": {}}]}\n```')
check("rào ```json chứa lời gọi -> nhắc sai rào", r.is_error and wtp.FENCE in r.error)
check("rào sai KHÔNG được coi là lời gọi thật", not r.calls)

r = wtp.parse('Ví dụ cấu hình:\n```json\n{"port": 8080}\n```\nAnh sửa chỗ đó nhé.')
check("code mẫu JSON thường KHÔNG bị bắt oan thành lỗi", r.is_final)
check("code mẫu vẫn nằm trong câu trả lời cuối", "8080" in r.final_text)

r = wtp.parse('```python\nprint("hello")\n```\nĐoạn trên chạy được.')
check("code mẫu python không bị bắt oan", r.is_final)


# ---- 7. V1: có khối tool thì phần văn xuôi không được coi là câu trả lời ----

r = wtp.parse("Để em đọc file đã.\n" + khoi('{"calls": [{"name": "javis_now", "arguments": {}}]}'))
check("vừa văn xuôi vừa tool -> vẫn là lượt TOOL, không phải final", r.is_tool and not r.is_final)


# ---- 8. Biến thể rào mà model hay viết ----

r = wtp.parse("``` " + wtp.FENCE + " \n" + '{"calls": [{"name": "javis_now"}]}' + "\n```")
check("rào có khoảng trắng thừa vẫn bóc được", r.is_tool)

r = wtp.parse("```" + wtp.FENCE.upper() + "\n" + '{"calls": [{"name": "javis_now"}]}' + "\n```")
check("rào viết hoa vẫn bóc được", r.is_tool)

r = wtp.parse(khoi('{"calls": [{"name": "javis_now"}]}'))
check("thiếu hẳn 'arguments' thì mặc định rỗng, không phải lỗi",
      r.is_tool and r.calls[0].arguments == {})

r = wtp.parse(khoi('{"calls": [{"name": "javis_now", "arguments": null}]}'))
check("arguments null coi như rỗng", r.is_tool and r.calls[0].arguments == {})


# ---- 9. Tin nhắn gửi lại ----

nhac = wtp.loi_nhac_sua("thiếu 'name'")
check("lời nhắc sửa có nêu lỗi gốc", "thiếu 'name'" in nhac)
check("lời nhắc sửa có in lại khuôn đúng", wtp.FENCE in nhac and "calls" in nhac)

c1 = wtp.ToolCall(name="javis_read_file", arguments={"path": "a.py"}, index=0)
c2 = wtp.ToolCall(name="javis_git_status", arguments={}, index=1)
tin = wtp.tin_ket_qua([(c1, "nội dung a"), (c2, "nhánh main, sạch")])
check("kết quả cả lô gộp vào MỘT tin (không đốt thêm lượt web)",
      "nội dung a" in tin and "nhánh main" in tin)
check("mỗi kết quả có gắn index và tên tool", "[0] javis_read_file" in tin
      and "[1] javis_git_status" in tin)

dan = wtp.loi_dan(["javis_read_file", "javis_now"])
check("lời dặn khuôn có phiên bản giao thức", wtp.TOOL_PROTOCOL_VERSION in dan)
check("lời dặn khuôn liệt kê tool đang có", "javis_read_file" in dan)
check("lời dặn khuôn cấm vừa gọi tool vừa trả lời", "KHÔNG viết câu trả lời kèm" in dan)


# ---- 10. Ranh giới module: thuần, không kéo theo nửa server ----

_src = (SERVER / "web_tool_protocol.py").read_text(encoding="utf-8")
for cam in ("import main", "from main", "fastapi", "playwright", "import mcp_hub"):
    check(f"module thuần, không '{cam}'", cam not in _src)
check("không tự xét quyền (việc của mcp_hub)", "min_mode" not in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_web_tool_protocol: tất cả pass")
