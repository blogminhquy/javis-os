"""share_store.py - kho LINK CHIA SẺ CÔNG KHAI của từng file trong brain.

Một link là một token ngẫu nhiên trỏ tới (brain, đường dẫn file). Ai cầm link đều xem được,
KHÔNG cần đăng nhập - đó là toàn bộ mục đích: chủ dự án làm một trang .html hay một ghi chú
.md rồi gửi cho người khác xem ngay.

Ba điều quyết định hình dạng kho này:

1. TOKEN LÀ THỨ DUY NHẤT CHẶN NGƯỜI LẠ, nên nó phải không đoán được. `secrets.token_urlsafe(18)`
   cho 144 bit ngẫu nhiên. Không dùng uuid4 (chỉ 122 bit và có phần đoán được), không dùng
   tên file băm ra (đoán được tên file là đoán được link).

2. LINK TRỎ TỚI FILE THẬT, không chụp lại nội dung (chủ dự án chọn 18/09). Sửa file thì người
   xem tải lại là thấy bản mới. Nên kho chỉ giữ ĐƯỜNG DẪN, và mọi phép kiểm quyền đọc file
   vẫn đi qua rào chống traversal chung của server lúc phục vụ, không phải lúc tạo link.

3. MỘT FILE CHỈ CÓ MỘT LINK. Bấm Chia sẻ lần hai trên cùng file thì trả lại đúng token cũ chứ
   không đẻ token mới: người ta đã gửi link đi rồi, đẻ thêm là mỗi lần bấm lại một link khác
   mà link cũ vẫn sống, không ai thu lại được.
"""
import json
import os
import secrets
import threading
import time
from pathlib import Path

from config import STATE_DIR

_LOCK = threading.RLock()
STORE = STATE_DIR / "share_links.json"

# Trần số link. Kho là một file JSON đọc/ghi nguyên khối, và nó nằm trên đường phục vụ MỌI
# lượt mở link công khai, nên không được phép phình vô hạn.
TRAN = 2000


def _doc_tho() -> dict:
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _ghi_tho(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STORE)          # thay nguyên khối: đọc song song không bao giờ thấy file dở


def _chuan_path(p: str) -> str:
    """Chuẩn hoá đường dẫn để SO SÁNH (tìm link đã có của cùng một file).

    KHÔNG phải hàng rào bảo mật: rào chống traversal nằm ở `_safe_serve_path` phía server, chạy
    lúc phục vụ. Ở đây chỉ cần hai cách viết cùng một file quy về một chuỗi.
    """
    return str(p or "").strip().replace("\\", "/").lstrip("/")


def tao(brain: str, path: str, nhan: str = "") -> dict:
    """Tạo (hoặc lấy lại) link của một file. Trả bản ghi kèm `token`."""
    brain = str(brain or "brain")
    path = _chuan_path(path)
    if not path:
        raise ValueError("Thiếu đường dẫn file")
    with _LOCK:
        d = _doc_tho()
        for tok, ban in d.items():
            if isinstance(ban, dict) and ban.get("brain") == brain and _chuan_path(ban.get("path")) == path:
                return dict(ban, token=tok)          # đã có link: trả lại đúng cái cũ
        if len(d) >= TRAN:
            raise ValueError(f"Đã đạt trần {TRAN} link chia sẻ, gỡ bớt link cũ trước")
        tok = secrets.token_urlsafe(18)
        d[tok] = {"brain": brain, "path": path, "nhan": str(nhan or ""), "tao_luc": time.time()}
        _ghi_tho(d)
        return dict(d[tok], token=tok)


def doc(token: str):
    """Bản ghi của một token, hoặc None. Đây là cửa DUY NHẤT của đường công khai."""
    tok = str(token or "").strip()
    if not tok:
        return None
    ban = _doc_tho().get(tok)
    if not isinstance(ban, dict) or not ban.get("path"):
        return None
    return dict(ban, token=tok)


def xoa(token: str) -> bool:
    """Thu hồi một link. Sau lệnh này link cũ trả 404 cho tất cả mọi người."""
    tok = str(token or "").strip()
    with _LOCK:
        d = _doc_tho()
        if tok not in d:
            return False
        d.pop(tok, None)
        _ghi_tho(d)
        return True


def danh_sach(brain: str = "") -> list:
    """Mọi link đang sống, mới nhất trước. Lọc theo brain nếu truyền."""
    d = _doc_tho()
    ra = [dict(v, token=k) for k, v in d.items()
          if isinstance(v, dict) and (not brain or v.get("brain") == brain)]
    ra.sort(key=lambda x: x.get("tao_luc") or 0, reverse=True)
    return ra


def cua_file(brain: str, path: str):
    """Link đã có của đúng file này, hoặc None. Dùng để nút Chia sẻ biết mình đang bật hay tắt."""
    brain = str(brain or "brain")
    path = _chuan_path(path)
    for tok, ban in _doc_tho().items():
        if isinstance(ban, dict) and ban.get("brain") == brain and _chuan_path(ban.get("path")) == path:
            return dict(ban, token=tok)
    return None
