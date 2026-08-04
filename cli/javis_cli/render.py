"""Vẽ ra terminal.

Luật Unix bắt buộc của cả CLI này, và là lý do file được tách riêng:

    CÂU TRẢ LỜI ra stdout. MỌI THỨ KHÁC ra stderr.

Thiếu luật đó thì `javis "..." > ghi-chu.md` sẽ dính spinner, dòng trạng thái và tên tool vào
giữa nội dung, và cả CLI thành vô dụng cho việc kịch bản hoá - tức là mất đúng cái lý do
người ta muốn có CLI.
"""
import os
import sys

_MAU = {"tat": "\033[0m", "mo": "\033[2m", "xanh": "\033[36m",
        "vang": "\033[33m", "do": "\033[31m", "dam": "\033[1m"}


def co_mau() -> bool:
    """Chỉ tô màu khi ĐANG nói với người. Đổ vào file hay pipe thì mã màu là rác."""
    if os.getenv("NO_COLOR"):
        return False
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


def _m(ten: str, chu: str) -> str:
    return f"{_MAU[ten]}{chu}{_MAU['tat']}" if co_mau() else chu


def tra_loi(chu: str):
    """Câu trả lời. Đây là thứ DUY NHẤT được ra stdout."""
    sys.stdout.write((chu or "").rstrip() + "\n")
    sys.stdout.flush()


def trang_thai(chu: str):
    if not chu:
        return
    sys.stderr.write(_m("mo", "  " + chu) + "\n")
    sys.stderr.flush()


def loi(chu: str):
    sys.stderr.write(_m("do", "Lỗi: ") + (chu or "") + "\n")
    sys.stderr.flush()


def nhac(chu: str):
    sys.stderr.write(_m("vang", chu) + "\n")
    sys.stderr.flush()


def duong_chay(ctx_path: str):
    """Dòng nhỏ cuối lượt: lượt này đi đường nào. Cùng bộ nhãn với dashboard để hai nơi nói
    cùng một thứ tiếng."""
    ten = {"legacy": "Đầy đủ", "sources": "Tối ưu", "fast": "Tức thì",
           "readonly": "Tra cứu", "orchestrator": "Tra cứu sâu", "write": "Thực thi",
           "workflow": "Quy trình"}.get(ctx_path or "", "")
    if ten:
        sys.stderr.write(_m("mo", "  · " + ten) + "\n")
        sys.stderr.flush()


def tieu_de(chu: str):
    sys.stderr.write(_m("dam", chu) + "\n")
    sys.stderr.flush()
