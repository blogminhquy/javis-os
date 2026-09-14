"""Cầu nối từ TOOL (chạy trong server) sang DASHBOARD (chạy trong trình duyệt).

Vì sao có file này
==================
Voice V1 (docs/dev/2026-09-voice-v1-spec.md, mục 6) cho model mở trang, mở file, mở việc trên
dashboard bằng tool `javis_ui`. Tool chạy ở server, còn thứ cần bấm nằm trong trình duyệt, nên
phải có một đường đi qua WebSocket `/ws` sẵn có và một chỗ ĐỢI trình duyệt trả lời: model cần
biết "đã mở" hay "không có tab nào đang mở" ngay trong lượt, không phải đoán.

Đường đi
========
    handler tool -> request()  -> runtime.publish({"type":"ui_action", id, ...})
                                   (mọi tab đang mở nhận, tab đúng phiên thực hiện)
    trình duyệt  -> /ws gửi {"action":"ui_result", id, ok, detail}
    vòng nhận WS -> resolve(id, ok, detail) -> future của request() có kết quả

Không import `main`: main GẮN runtime vào đây lúc khởi động (`attach`), plugin thì import
module này. Giống cách `javis-task` import `tasks` và gọi `tasks.current()`.

Hết giờ 4 giây: dashboard là JS chạy trong tab, tab bị treo hay đã đóng nửa chừng thì không
ai đáp; tool không được phép treo lượt chat theo.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, Optional

_runtime: Any = None
_pending: Dict[str, asyncio.Future] = {}
TIMEOUT_S = 4.0


def attach(runtime: Any) -> None:
    """main.py gọi một lần: đưa `_CHAT_RUNTIME` vào đây."""
    global _runtime
    _runtime = runtime


def has_clients() -> bool:
    """Có tab dashboard nào đang nối WebSocket không."""
    try:
        return bool(getattr(_runtime, "_clients", None))
    except Exception:
        return False


async def request(action: str, target: str = "", session_id: str = "",
                  extra: Optional[dict] = None, timeout: float = TIMEOUT_S) -> dict:
    """Bảo dashboard làm một việc rồi đợi nó trả lời.

    Trả dict `{"ok": bool, "detail": str, ...}`. Không bao giờ ném lỗi ra ngoài: tool phải
    thuật lại được mọi ngả hỏng bằng một câu.
    """
    if _runtime is None:
        return {"ok": False, "detail": "cầu nối dashboard chưa sẵn sàng (máy chủ đang khởi động?)"}
    if not has_clients():
        return {"ok": False, "detail": "không có dashboard nào đang mở để thực hiện"}
    rid = uuid.uuid4().hex[:12]
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    _pending[rid] = fut
    frame = {"type": "ui_action", "id": rid, "action": str(action or ""),
             "target": str(target or ""), "session_id": str(session_id or "")}
    if extra:
        frame.update({k: v for k, v in extra.items() if k not in frame})
    try:
        await _runtime.publish(frame)
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return {"ok": False, "detail": f"dashboard không phản hồi trong {timeout:g} giây"}
    except Exception as e:  # pragma: no cover - phòng writer lạ
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}
    finally:
        _pending.pop(rid, None)


def resolve(rid: str, ok: bool, detail: str = "", **rest: Any) -> bool:
    """Vòng nhận WS gọi khi trình duyệt trả `ui_result`. True nếu có ai đang đợi id này.

    Nhiều tab cùng nhận một `ui_action`; tab nào không phải phiên đó trả `skipped=True`, và
    câu trả lời ấy KHÔNG được phép giải future (tab đúng phiên có thể đáp sau vài mili giây).
    """
    fut = _pending.get(str(rid or ""))
    if fut is None or fut.done():
        return False
    if rest.get("skipped"):
        return False
    res = {"ok": bool(ok), "detail": str(detail or "")}
    for k, v in rest.items():
        res.setdefault(k, v)
    fut.set_result(res)
    return True


def pending_count() -> int:
    return len(_pending)
