"""quota_scheduler.py - Sổ cái TPM DÙNG CHUNG cho mọi nguồn gọi model.

Vấn đề nó giải: hạn mức token mỗi phút là của TÀI KHOẢN, không phải của từng đường code.
Nhưng trước module này, `admit_quota` chỉ nhìn thấy phần đặt chỗ của bốn đường canary, trong
khi `usage_store.record` được gọi từ mười chỗ - chat legacy, loop nền, task Kanban, nhắc hẹn,
Telegram, CLI, Codex. Nghĩa là mọi lượt KHÔNG phải canary đốt hạn mức thật một cách vô hình.

Hệ quả cụ thể: canary hỏi "còn bao nhiêu token trong 60 giây qua", nhận về một con số cao hơn
thực tế, rồi cho qua đúng cái request làm vỡ hạn mức. Loop chạy nền lúc người dùng đang chat
là ca kinh điển.

Ranh giới để KHÔNG đếm hai lần, đây là phần dễ sai nhất:
  - Sổ cái này ghi mức dùng THẬT của mọi lượt, không phân biệt đường nào.
  - `quota_reservations` chỉ còn đếm phần ĐANG BAY (status ADMITTED), tức là ước lượng của
    request chưa báo số thật về.
  - Cộng lại: used = thật (sổ cái) + đang bay (đặt chỗ). Một lượt canary đi qua cả hai nhưng
    ở hai thời điểm khác nhau, nên không chồng nhau.

Trạng thái nằm trong tiến trình (deque), không ghi đĩa: cửa sổ chỉ 60 giây nên mất khi khởi
động lại là chấp nhận được, và nó khiến module này không có phụ thuộc nào - ai import cũng
được, không sợ vòng lặp import.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

# Trần cửa sổ. Giữ bằng trần của admit_quota để hai bên không lệch nhau.
WINDOW_MAX_SECONDS = 3600

_lock = threading.Lock()
_ledger: dict[tuple[str, str], deque] = defaultdict(deque)


def _key(provider: str, model: str) -> tuple[str, str]:
    return (str(provider or "?").strip().casefold(), str(model or "?").strip())


def _prune(bucket: deque, cutoff: float) -> None:
    while bucket and bucket[0][0] < cutoff:
        bucket.popleft()


def observe(provider: str, model: str, tokens: int, now: float | None = None) -> None:
    """Ghi nhận mức dùng THẬT của một lượt. Gọi từ MỌI đường gọi model.

    Không bao giờ ném lỗi ra ngoài: kế toán hạn mức là việc phụ, làm hỏng một lượt chat vì
    nó là đánh đổi sai."""
    try:
        total = max(0, int(tokens or 0))
        if total <= 0:
            return
        ts = time.time() if now is None else float(now)
        with _lock:
            bucket = _ledger[_key(provider, model)]
            bucket.append((ts, total))
            _prune(bucket, ts - WINDOW_MAX_SECONDS)
    except Exception:  # noqa: BLE001 - xem docstring
        return


def used(provider: str, model: str, window_seconds: int = 60,
         now: float | None = None) -> int:
    """Tổng token thật đã dùng cho provider/model trong cửa sổ vừa qua."""
    try:
        window = max(1, min(int(window_seconds or 60), WINDOW_MAX_SECONDS))
        ts = time.time() if now is None else float(now)
        cutoff = ts - window
        with _lock:
            bucket = _ledger.get(_key(provider, model))
            if not bucket:
                return 0
            _prune(bucket, ts - WINDOW_MAX_SECONDS)
            return sum(tok for at, tok in bucket if at >= cutoff)
    except Exception:  # noqa: BLE001
        return 0


def snapshot(window_seconds: int = 60, now: float | None = None) -> dict:
    """Mức dùng theo provider/model trong cửa sổ, cho trang Chẩn đoán.

    Đây là thứ trả lời được câu "vì sao canary bị từ chối trong khi tôi có chat gì đâu":
    loop nền vừa đốt hạn mức."""
    out = {}
    try:
        ts = time.time() if now is None else float(now)
        with _lock:
            keys = list(_ledger.keys())
        for provider, model in keys:
            total = used(provider, model, window_seconds, ts)
            if total > 0:
                out[f"{provider}|{model}"] = total
    except Exception:  # noqa: BLE001
        return out
    return out


def reset() -> None:
    """Xoá sổ cái. Chỉ dùng trong test."""
    with _lock:
        _ledger.clear()
