"""Một dòng mô tả lệnh gọi công cụ cho khối tiến trình trong khung chat (0.64.44).

    python tests/python/test_tool_label.py

Chủ repo báo 2026-09-24: khối "Đang chạy công cụ" chỉ ghi "Đang gọi: Bash", "Đang gọi: Read"
lặp lại, không biết lệnh nào, file nào. `tool_label.chi_tiet` rút từ tham số lệnh gọi ra một
dòng người đọc được; main.py gửi nó xuống dashboard trong trường `detail`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import re
import sys

import tool_label  # noqa: E402

fails = []


def check(ten, dk, them=""):
    print(("ok   " if dk else "FAIL ") + ten + ("" if dk or not them else f"  [{them}]"))
    if not dk:
        fails.append(ten)


ct = tool_label.chi_tiet

# Claude Code: input có cấu trúc
check("Bash: ưu tiên description (câu model viết cho người đọc)",
      ct({"name": "Bash", "input": {"command": "git status", "description": "Xem trạng thái repo"}}) == "Xem trạng thái repo")
check("Bash không description: lấy command",
      ct({"name": "Bash", "input": {"command": "ls -la"}}) == "ls -la")
check("Read: đường dẫn file", ct({"name": "Read", "input": {"file_path": "wiki/a.md"}}) == "wiki/a.md")
dai = ct({"name": "Read", "input": {"file_path": "/root/.javis/brains/cua-hang/wiki/khach-hang/danh-sach.md"}})
check("đường dẫn tuyệt đối dài: chỉ giữ 3 đoạn cuối", dai == "…/wiki/khach-hang/danh-sach.md", dai)
check("Grep: mẫu tìm", ct({"name": "Grep", "input": {"pattern": "doanh thu"}}) == "doanh thu")
check("WebFetch: URL", ct({"name": "WebFetch", "input": {"url": "https://x.vn/a"}}) == "https://x.vn/a")

# Codex: item thô
check("Codex command mảng bash -lc: lấy lệnh bên trong",
      ct({"name": "command_execution", "item": {"command": ["bash", "-lc", "cat a.md"]}}) == "cat a.md")
check("Codex command chuỗi bash -lc",
      ct({"item": {"command": "bash -lc 'npm test'"}}) == "npm test")
check("Codex apply_patch: liệt kê file đổi",
      ct({"item": {"changes": [{"path": "a.md"}, {"path": "b.md"}]}}) == "a.md, b.md")
check("Codex function_call: arguments là chuỗi JSON",
      ct({"item": {"name": "pos_order", "arguments": "{\"query\": \"đơn hôm nay\"}"}}) in ("pos_order", "đơn hôm nay"))
check("MCP input lồng: vẫn rút được",
      ct({"input": {"arguments": {"query": "đơn hôm nay"}}}) == "đơn hôm nay")

# Không đoán, không nổ
check("không có tham số: chuỗi rỗng", ct({"name": "Bash"}) == "")
check("payload rác: chuỗi rỗng", ct(None) == "" and ct("x") == "" and ct({"input": 5}) == "")
check("tham số chỉ có số: chuỗi rỗng", ct({"input": {"limit": 10}}) == "")

# Một dòng, có trần
nhieu = ct({"input": {"command": "a\n\n   b\tc"}})
check("nhiều dòng gộp thành một", nhieu == "a b c", nhieu)
qua = ct({"input": {"command": "x" * 500}})
check("dài quá thì cắt theo trần", len(qua) == tool_label.TRAN and qua.endswith("…"), str(len(qua)))

# main.py gửi `detail` ở mọi chỗ đẩy tool_call xuống khung chat từ engine có tham số
MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("main.py import tool_label", re.search(r"^import tool_label", MAIN, re.M) is not None)
check("main.py gửi detail ở >= 7 chỗ", MAIN.count('"detail": tool_label.chi_tiet(') >= 7,
      str(MAIN.count('"detail": tool_label.chi_tiet(')))
ENG = (SERVER / "engine.py").read_text(encoding="utf-8")
check("engine API kèm input trong sự kiện tool_call",
      ENG.count('"type": "tool_call", "name": fn, "input": args') == 1
      and ENG.count('"input": args}') >= 3)

# Không có gạch dài trong file mới
SRC = (SERVER / "tool_label.py").read_text(encoding="utf-8")
check("tool_label.py không có gạch dài", "\u2014" not in SRC and "\u2013" not in SRC)

print(f"\n{len(fails)} FAIL" if fails else "\nTất cả xanh")
sys.exit(1 if fails else 0)
