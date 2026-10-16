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

Mỗi mẩu thư mang theo ĐỊA CHỈ của nội dung thật (`session_id` + `channel`), nên bấm vào là
quay về đúng hội thoại đã hỏi, ở ĐÚNG TRANG của nó - chứ không mở một hội thoại mới rỗng
không có ngữ cảnh gì, và cũng không đổ hội thoại của một trợ lý vào khung chat của bộ não
chính.
"""
from __future__ import annotations

import json
import re
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
    """Rút tiêu đề từ chính nội dung: dòng đầu CÓ CHỮ, bỏ dấu markdown.

    Người gọi (`_notify_owner`) chỉ có một khối văn bản, không có trường tiêu đề riêng.
    Lấy dòng đầu là đủ dùng và luôn đúng ngôn ngữ của nội dung, không phải bịa ra một
    nhãn chung chung kiểu "Việc nền đã xong" cho mọi thứ.

    Bỏ dấu nhấn markdown ở CẢ HAI ĐẦU chứ không riêng đầu dòng: tiêu đề này đi thẳng ra
    thông báo đẩy của hệ điều hành, nơi không ai dịch markdown cả. Câu trả lời của Javis hay
    mở đầu bằng "**Nhắc bạn:** ..." nên cắt kiểu cũ (chỉ lstrip) để lại đúng cái đuôi "**"
    lơ lửng giữa tiêu đề trên màn hình khoá điện thoại.
    """
    for dong in str(text or "").splitlines():
        s = dong.strip().lstrip("#*->•").strip()
        # Chỉ gỡ KÝ HIỆU nhấn (đậm, nghiêng dạng __, mã inline), không đụng dấu câu: một
        # tiêu đề mất dấu hai chấm hay dấu ngoặc thì đọc còn khó hơn là thừa hai ngôi sao.
        s = re.sub(r"\*\*|__|`", "", s).strip()
        if s:
            return s[:MAX_TITLE]
    import localefmt
    return localefmt.chu("Javis vừa gửi một tin", "Javis just sent a message")


def add(text: str, *, kind: str = "answer", session_id: str = "", brain: str = "",
        source: str = "", label: str = "", title: str = "", read: bool = False,
        channel: str = "", dedup: str = "", routing: str = "") -> dict:
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
        # KÊNH của hội thoại đích ("web", "telegram", "agent:<slug>", "workflow:<slug>"...).
        # Có nó thì lúc bấm vào mẩu thư, dashboard mở ĐÚNG TRANG chứa hội thoại đó: hội thoại
        # của một trợ lý phải mở ở trang Cộng sự, không phải đổ vào khung chat của bộ não
        # chính - đổ nhầm thì tin gõ tiếp bay vào phiên của trợ lý mà người dùng không hay
        # (đúng lỗi bản 0.59.15 đã chữa cho đường rời trang).
        "channel": str(channel or ""),
    }
    # `dedup` (0.186.0): a retried report (a reminder sent again after a crash, a job reported twice) carries the
    # same key; the first item stands and the caller learns it was a repeat (`duplicate`), so no channel rings twice.
    # `routing` (0.186.0): why the report could not be delivered to a chat ("no_target": no chat and no source brain),
    # kept so the owner sees it in the bell instead of Javis guessing a recipient.
    if dedup:
        item["dedup"] = str(dedup)[:200]
    if routing:
        item["routing"] = str(routing)[:40]
    with _LOCK:
        d = _load()
        if dedup:
            cu = next((it for it in d["items"] if it.get("dedup") == item["dedup"]), None)
            if cu is not None:
                return {**cu, "duplicate": True}
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


# ── read state of the shared news (releases, announcements), 0.187.0 ─────────────────────────────────────────────
#
# The "News" tab is computed for everyone (`GET /notifications`), so the items are not stored once per person; only
# WHICH of them this account has read is. It used to live in each browser's localStorage, so the phone and the
# laptop disagreed. One instance has one account (the owner), so one file holds that account's read set; reading on
# one device clears it on every device, and switching brains changes nothing.
NEWS_STORE = STATE_DIR / "news_read.json"
NEWS_MAX = 500


def _news_load() -> dict:
    try:
        d = json.loads(NEWS_STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    ids = d.get("read") if isinstance(d, dict) else None
    return {"read": [str(x) for x in ids] if isinstance(ids, list) else [],
            "initialized": bool(isinstance(d, dict) and d.get("initialized"))}


def news_state() -> dict:
    with _LOCK:
        return _news_load()


def news_mark(ids, *, initialized: bool = False) -> dict:
    """Add `ids` to the read set (newest kept, capped). `initialized` records that the first-run pass is done."""
    with _LOCK:
        d = _news_load()
        seen = set(d["read"])
        for x in ids or []:
            x = str(x or "").strip()[:200]
            if x and x not in seen:
                d["read"].append(x)
                seen.add(x)
        d["read"] = d["read"][-NEWS_MAX:]
        if initialized:
            d["initialized"] = True
        tmp = NEWS_STORE.with_name(NEWS_STORE.name + ".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(NEWS_STORE)
        return d


def get(item_id: str):
    """One inbox item by id, or None."""
    with _LOCK:
        return next((it for it in _load()["items"] if it.get("id") == str(item_id or "")), None)
