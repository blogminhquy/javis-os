"""Sổ "làm đúng một lần" cho thao tác ra ngoài của việc nền Kanban (0.238.0).

Vì sao có file này
==================
Việc Kanban chạy lại là chạy lại TỪ ĐẦU: lỗi tạm thời được thử tối đa 3 lần, máy chủ khởi động
lại giữa chừng thì việc về hàng đợi, chủ bấm Thử lại. Mỗi lần như vậy worker gọi lại đúng những
tool nó đã gọi, kể cả tool gửi tin Zalo, đăng bài, tạo đơn. Mặc định việc chạy ở mức `full`, nên
một tin có thể tới khách hai, ba lần.

Ý tưởng lấy từ OpenMuse (CopilotKit, giấy phép MIT): mỗi thao tác của một việc mang một dấu vân
tay (mã việc + tên tool + tham số đã chuẩn hoá) ghi vào sổ TRƯỚC khi gọi, cập nhật SAU khi gọi.

- Gặp lại dấu vân tay đã `succeeded`: không gọi lại, trả kết quả cũ kèm ghi chú.
- Kẹt ở `started` (máy chủ chết đúng lúc đang gọi) hoặc lỗi kiểu hết giờ, đứt kết nối: không ai
  biết thao tác đã tới nơi hay chưa, nên chuyển `unknown` và KHÔNG tự gọi lại. Việc dừng lại hỏi
  chủ (tasks.py, cơ chế hỏi đáp của 0.235.0).
- `failed` rõ ràng (dịch vụ trả lỗi): được gọi lại.

Chỉ áp cho lượt có `job` trong `turn_context` (việc Kanban gắn vào lúc chạy). Chat thường không có
`job` nên đi thẳng như cũ. Loop không cần: vòng hỏng không được chạy lại, vòng sau là việc mới.

Sổ dùng chung công thức băm tham số với `capability_executor.arguments_hash` (json sort_keys) và
chung bộ trạng thái với sổ write của Adaptive Runtime (STARTED/SUCCEEDED/UNKNOWN), nhưng là bảng
riêng: sổ kia gắn với lease, trace và registry của một nhánh canary đang tắt, kéo cả nhánh đó vào
đường chạy của mọi việc nền là đổi một thay đổi nhỏ lấy một rủi ro lớn.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import turn_context

STARTED, SUCCEEDED, FAILED, UNKNOWN = "started", "succeeded", "failed", "unknown"
# Mỗi tiến trình một mã: một dòng `started` mang mã của tiến trình TRƯỚC là lời gọi bị máy chủ
# chết cắt ngang, không phải lời gọi đang chạy.
BOOT = secrets.token_hex(8)
_RESULT_MAX = 2000
_KEEP_S = 30 * 86400
# Lỗi kiểu này không nói được thao tác đã tới nơi hay chưa (gửi xong rồi mới mất phản hồi).
_UNCERTAIN_RE = re.compile(
    r"timeout|timed out|time-out|TimeoutError|CancelledError|connection (?:reset|aborted|closed|lost)"
    r"|RemoteProtocolError|ReadError|ServerDisconnected|BrokenPipe|hết (?:thời )?giờ|quá thời gian",
    re.IGNORECASE)
# Tham số hay dùng để chỉ "gửi cho ai": dùng để kể lại cho chủ, không dùng để chặn.
_TARGET_KEYS = ("threadId", "thread_id", "chat_id", "chatId", "to", "recipient", "email", "phone", "user_id",
                "userId", "page_id", "channel", "customer", "order_id")
_TEXT_KEYS = ("message", "text", "content", "body", "caption", "subject", "title")

DONE_NOTE = ("[Javis] Thao tác này ĐÃ làm xong ở một lần chạy trước của chính việc này nên không làm lại "
             "(tránh gửi trùng). Kết quả lần đó:\n")
UNKNOWN_NOTE = ("ERROR: Thao tác này có thể ĐÃ được thực hiện ở lần chạy trước (máy chủ dừng hoặc mất kết nối "
                "đúng lúc đang gọi), nên Javis KHÔNG làm lại để tránh gửi trùng. Đừng tìm cách khác để làm cùng "
                "việc này. Làm nốt phần còn lại rồi kết thúc; Javis sẽ hỏi chủ.")
BUSY_NOTE = "ERROR: Đúng thao tác này đang được gọi ở một nhánh khác của việc, chờ nó xong, đừng gọi lại."

_lock = threading.RLock()
_db: Optional[sqlite3.Connection] = None
_path: Optional[Path] = None
_inflight: set = set()


def configure(path) -> None:
    """Đổi chỗ để sổ (test). Đóng kết nối cũ, lần dùng sau mở lại ở chỗ mới."""
    global _db, _path
    with _lock:
        if _db is not None:
            _db.close()
        _db, _path = None, Path(path)
        _inflight.clear()


def _conn() -> sqlite3.Connection:
    global _db, _path
    if _db is None:
        if _path is None:
            from config import STATE_DIR
            _path = Path(STATE_DIR) / "once_ledger.sqlite3"
        _path.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(_path), check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA busy_timeout=5000")
        _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS writes (
                fp TEXT PRIMARY KEY,
                job TEXT NOT NULL,
                tool TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT '',
                boot TEXT NOT NULL DEFAULT '',
                started_at REAL NOT NULL,
                finished_at REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_writes_job ON writes(job, status);
            """
        )
        _db.commit()
    return _db


def current_job() -> str:
    """Mã việc nền của lượt đang chạy ("kanban:<id>"), "" ngoài việc nền."""
    return str((turn_context.current() or {}).get("job") or "")


def fingerprint(job: str, tool: str, args: Any) -> str:
    raw = json.dumps({"job": job, "tool": tool, "args": args}, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def describe(tool: str, args: Any) -> str:
    """Một dòng kể thao tác cho chủ đọc: tool, gửi tới đâu, đầu nội dung."""
    a = args if isinstance(args, dict) else {}
    phan = [str(tool)]
    for k in _TARGET_KEYS:
        if a.get(k) not in (None, ""):
            phan.append(f"tới {a[k]}")
            break
    for k in _TEXT_KEYS:
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            phan.append(f"\"{v[:80]}{'...' if len(v) > 80 else ''}\"")
            break
    return " ".join(phan)[:240]


def _set(fp: str, **cols) -> None:
    keys = ", ".join(f"{k}=?" for k in cols)
    _conn().execute(f"UPDATE writes SET {keys} WHERE fp=?", (*cols.values(), fp))
    _conn().commit()


async def run(tool: str, args: Any, call: Callable[[Any], Awaitable[Any]], job: Optional[str] = None) -> Any:
    """Gọi `call(args)` đúng một lần cho mỗi (việc, tool, tham số). Ngoài việc nền thì gọi thẳng."""
    job = current_job() if job is None else job
    if not job:
        return await call(args)
    fp = fingerprint(job, tool, args)
    now = time.time()
    with _lock:
        row = _conn().execute("SELECT status, result, boot FROM writes WHERE fp=?", (fp,)).fetchone()
        if row is not None:
            st = row["status"]
            if st == SUCCEEDED:
                return DONE_NOTE + str(row["result"] or "")
            if st == STARTED and fp in _inflight:
                return BUSY_NOTE
            if st in (STARTED, UNKNOWN):
                _set(fp, status=UNKNOWN, finished_at=now)
                return UNKNOWN_NOTE
        _conn().execute(
            """INSERT INTO writes(fp, job, tool, target, status, boot, started_at) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(fp) DO UPDATE SET status=excluded.status, boot=excluded.boot,
               started_at=excluded.started_at, finished_at=0, result=''""",
            (fp, job, str(tool), describe(tool, args), STARTED, BOOT, now))
        _conn().execute("DELETE FROM writes WHERE finished_at > 0 AND finished_at < ?", (now - _KEEP_S,))
        _conn().commit()
        _inflight.add(fp)
    try:
        res = await call(args)
    except BaseException:
        # Bị huỷ hay nổ GIỮA lúc gọi: không biết thao tác đã tới nơi chưa.
        with _lock:
            _inflight.discard(fp)
            _set(fp, status=UNKNOWN, finished_at=time.time())
        raise
    text = str(res)
    if text.startswith("ERROR:"):
        status = UNKNOWN if _UNCERTAIN_RE.search(text) else FAILED
    else:
        status = SUCCEEDED
    with _lock:
        _inflight.discard(fp)
        _set(fp, status=status, result=text[:_RESULT_MAX], finished_at=time.time())
    return res


def unknowns(job: str) -> list[dict]:
    """Thao tác của việc chưa rõ đã tới nơi hay chưa. Dòng `started` của tiến trình trước (máy chủ
    chết giữa lúc gọi) được chốt thành `unknown` ở đây."""
    if not job:
        return []
    with _lock:
        _conn().execute(
            "UPDATE writes SET status=?, finished_at=? WHERE job=? AND status=? AND boot<>?",
            (UNKNOWN, time.time(), job, STARTED, BOOT))
        _conn().commit()
        rows = _conn().execute(
            "SELECT fp, tool, target, started_at FROM writes WHERE job=? AND status=? ORDER BY started_at",
            (job, UNKNOWN)).fetchall()
    return [dict(r) for r in rows]


def resolve(job: str, done: bool) -> int:
    """Chủ đã kiểm: `done=True` coi như đã làm (lần sau bỏ qua), `False` xoá khỏi sổ để làm lại."""
    with _lock:
        if done:
            n = _conn().execute(
                "UPDATE writes SET status=?, result=?, finished_at=? WHERE job=? AND status=?",
                (SUCCEEDED, "Chủ xác nhận thao tác này đã được thực hiện.", time.time(), job, UNKNOWN)).rowcount
        else:
            n = _conn().execute("DELETE FROM writes WHERE job=? AND status=?", (job, UNKNOWN)).rowcount
        _conn().commit()
    return int(n or 0)


# Câu trả lời của chủ cho câu hỏi "đã gửi chưa". Chỉ những câu MỞ ĐẦU bằng ý "chưa / làm lại" mới
# cho làm lại; mọi câu khác coi như đã làm. Sai về phía "đã làm" thì cùng lắm thiếu một tin, chủ tự
# gửi; sai về phía "chưa" là khách nhận hai tin, đúng thứ sổ này sinh ra để chặn.
_REDO_RE = re.compile(r"^\s*(chua|no\b|not\b|nope|lam lai|gui lai|chay lai|dang lai|redo|resend)")


def _norm(text: str) -> str:
    import unicodedata
    raw = str(text or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return " ".join("".join(c for c in raw if not unicodedata.combining(c)).split())


def answer_means_redo(text: str) -> bool:
    return bool(_REDO_RE.search(_norm(text)))
