"""Hòm thư của Javis - nơi MỌI kết quả chạy nền tìm được đường về với người dùng.

Vì sao có file này
==================
Trước bản này, việc nền báo kết quả qua đúng ba đường và đường nào cũng hụt một chỗ:

  - Việc Kanban / loop: `_notify_owner` đẩy vào ĐÚNG khung chat web đã giao việc. Tin nằm
    trong kho phiên, F5 vẫn còn - nhưng nếu người dùng đang mở một hội thoại KHÁC, hoặc đã
    đóng tab từ nửa tiếng trước, thì không có gì báo rằng kết quả đã về. Muốn biết thì phải
    tự nhớ là mình có giao việc, rồi tự đi bấm lại đúng hội thoại đó.
  - Nhắc hẹn: chỉ đi Telegram/Zalo. Chưa đấu bot thì `reminders.py` CHẶN KHÔNG CHO TẠO
    (xem `notify_ready`) - vì tạo ra một cái nhắc không có đường báo là tạo ra sự im lặng.
  - Chuông "Thông báo" trên navbar: là kênh PHÁT TIN một chiều (bản cập nhật + tin cộng
    đồng kéo từ GitHub), không phải hộp thư riêng của người dùng.

Hòm thư đóng cả ba lỗ bằng một ý duy nhất: **kết quả nào cũng để lại một mẩu thư**, bất kể
nó được gửi đi bằng kênh gì. Kênh (chat web / Telegram / Zalo / push trình duyệt) là chuông
cửa - hụt cũng không sao. Hòm thư là SỰ THẬT BỀN: còn sau F5, còn khi đóng tab, thấy được
từ máy khác vì nó nằm ở server chứ không phải localStorage.

Vì thế trạng thái đã-đọc cũng nằm ở server. Chuông "Thông báo" cũ giữ đã-đọc trong
localStorage - hợp lý với changelog (ai đọc trên máy nấy), nhưng sai với thư riêng: điện
thoại và máy tính sẽ đếm lệch nhau, xoá dữ liệu trình duyệt là mất sạch.

Mỗi mẩu thư mang theo ĐỊA CHỈ của nội dung thật (`session_id`), nên bấm vào là quay về đúng
hội thoại đã hỏi - chứ không mở một hội thoại mới rỗng không có ngữ cảnh gì.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from pathlib import Path

from config import STATE_DIR

STORE = STATE_DIR / "inbox.json"

# Ghi từ nhiều nơi (endpoint, scheduler nền, thread bot) → khoá quanh cả chu trình
# load-modify-save, đúng lối mcp_store đang dùng.
_LOCK = threading.RLock()

# Trần số thư giữ lại. Hòm thư là chỗ LIẾC xem có gì mới, không phải kho lưu trữ - nội dung
# thật vẫn nằm nguyên trong hội thoại. Giữ vô hạn thì file phình mãi mà không ai đọc tới.
MAX_ITEMS = 300

# Loại thư. Chia làm hai nhóm ở giao diện: "Của tôi" (answer/report) và "Tin tức" (system).
#   answer  - Javis trả lời một việc BẠN giao (task Kanban, câu hỏi chạy nền)
#   report  - báo cáo định kỳ tự chạy (loop, nhắc hẹn) - bạn không hỏi lúc đó
#   system  - Javis tự nói (lỗi việc nền, cảnh báo hết hạn mức...)
KINDS = ("answer", "report", "system")

# Tiêu đề cắt ngắn cho vừa một dòng thẻ; thân thư cắt cho vừa cái xem trước.
MAX_TITLE = 120
MAX_BODY = 600


def _load() -> dict:
    try:
        raw = STORE.read_text(encoding="utf-8")
    except OSError:
        return {"version": 1, "items": []}
    try:
        d = json.loads(raw)
    except Exception as e:
        # File hỏng: đừng ném lỗi lên tận endpoint làm chết cả chuông. Báo ra stderr rồi
        # coi như hòm rỗng - mất thư cũ còn hơn mất luôn hòm.
        print(f"[inbox] hỏng {STORE.name}: {type(e).__name__}: {e}", file=sys.stderr)
        return {"version": 1, "items": []}
    if not isinstance(d, dict):
        return {"version": 1, "items": []}
    d.setdefault("version", 1)
    if not isinstance(d.get("items"), list):
        d["items"] = []
    return d


def _save(d: dict) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STORE)
    except OSError as e:
        print(f"[inbox] ghi {STORE.name} lỗi: {type(e).__name__}: {e}", file=sys.stderr)


def _tieu_de(text: str) -> str:
    """Rút tiêu đề từ chính nội dung: dòng đầu CÓ CHỮ, bỏ dấu markdown mở đầu.

    Người gọi (`_notify_owner`) chỉ có một khối văn bản, không có trường tiêu đề riêng.
    Lấy dòng đầu là đủ dùng và luôn đúng ngôn ngữ của nội dung, không phải bịa ra một
    nhãn chung chung kiểu "Việc nền đã xong" cho mọi thứ.
    """
    for dong in str(text or "").splitlines():
        s = dong.strip().lstrip("#*->•").strip()
        if s:
            return s[:MAX_TITLE]
    return "Javis vừa gửi một tin"


def add(text: str, *, kind: str = "answer", session_id: str = "", brain: str = "",
        source: str = "", label: str = "", title: str = "", read: bool = False) -> dict:
    """Bỏ MỘT mẩu thư vào hòm. Trả về thư vừa tạo.

    `text` là nguyên văn nội dung đã gửi cho người dùng; hòm thư chỉ giữ bản cắt ngắn để
    xem trước, còn bản đầy đủ nằm trong hội thoại mà `session_id` trỏ tới.

    `read=True` bỏ thư vào hòm nhưng KHÔNG tính vào số chưa đọc, tức là không nổi chấm đỏ
    trên chuông. Dùng cho tin đáng LƯU nhưng không đáng gọi người dùng dậy: việc nền chạy
    xong trót lọt (kết quả đã rơi thẳng vào khung chat rồi). Chủ repo chốt 01/09/2026 sau
    khi chuông kêu liên hồi giữa lúc đang chat: chỉ việc BỊ CHẶN hoặc CHỜ DUYỆT mới đáng
    kêu, vì đó là thứ cần anh ra tay. Thư vẫn nằm nguyên trong danh sách chuông để mở ra
    xem lại được.
    """
    item = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind if kind in KINDS else "answer",
        "title": (str(title).strip()[:MAX_TITLE] or _tieu_de(text)) if title else _tieu_de(text),
        "body": str(text or "").strip()[:MAX_BODY],
        "ts": time.time(),
        "read": bool(read),
        "session_id": str(session_id or ""),
        "brain": str(brain or ""),
        "source": str(source or ""),
        "label": str(label or "")[:MAX_TITLE],
    }
    with _LOCK:
        d = _load()
        d["items"].append(item)
        if len(d["items"]) > MAX_ITEMS:
            # Cắt từ ĐẦU (cũ nhất) và chỉ cắt thư ĐÃ ĐỌC trước; thư chưa đọc là thứ người
            # dùng còn nợ, xoá nó đi là xoá đúng cái đáng giữ nhất.
            thua = len(d["items"]) - MAX_ITEMS
            giu, bo = [], 0
            for it in d["items"]:
                if bo < thua and it.get("read"):
                    bo += 1
                    continue
                giu.append(it)
            # Vẫn quá trần (toàn thư chưa đọc) thì đành cắt cũ nhất.
            d["items"] = giu[-MAX_ITEMS:]
        _save(d)
    return item


def danh_sach(limit: int = 50) -> list:
    """Thư MỚI NHẤT trước. `limit` chặn trên để panel không phải tải cả trăm mẩu."""
    with _LOCK:
        items = list(_load().get("items") or [])
    items.sort(key=lambda x: float(x.get("ts") or 0), reverse=True)
    return items[:max(1, int(limit or 50))]


def so_chua_doc() -> int:
    with _LOCK:
        return sum(1 for x in (_load().get("items") or []) if not x.get("read"))


def danh_dau_doc(item_id: str) -> bool:
    with _LOCK:
        d = _load()
        for it in d.get("items") or []:
            if str(it.get("id")) == str(item_id):
                if it.get("read"):
                    return True
                it["read"] = True
                _save(d)
                return True
    return False


def doc_het() -> int:
    """Đánh dấu đã đọc tất cả. Trả về số thư vừa đổi trạng thái."""
    with _LOCK:
        d = _load()
        n = 0
        for it in d.get("items") or []:
            if not it.get("read"):
                it["read"] = True
                n += 1
        if n:
            _save(d)
        return n


def doc_theo_phien(session_id: str) -> int:
    """Đã mở hội thoại nào thì thư của hội thoại đó coi như đã đọc.

    Không có nhát này thì một kết quả bị đếm hai lần: người dùng đọc nó trong khung chat
    rồi mà chuông vẫn nhắc, và cách duy nhất để tắt là vào hòm bấm thêm một lần nữa.
    """
    sid = str(session_id or "").strip()
    if not sid:
        return 0
    with _LOCK:
        d = _load()
        n = 0
        for it in d.get("items") or []:
            if not it.get("read") and str(it.get("session_id")) == sid:
                it["read"] = True
                n += 1
        if n:
            _save(d)
        return n


def xoa(item_id: str) -> bool:
    with _LOCK:
        d = _load()
        truoc = len(d.get("items") or [])
        d["items"] = [x for x in (d.get("items") or []) if str(x.get("id")) != str(item_id)]
        if len(d["items"]) == truoc:
            return False
        _save(d)
        return True
