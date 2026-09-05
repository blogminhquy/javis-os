"""limit_resume.py - Tự chạy lại lượt chat khi gói thuê bao mở lại hạn mức.

Cảnh cụ thể nó giải: Claude Code, Codex, Grok Build hay Antigravity báo "hết lượt, mở lại
lúc 13:01". Trước module này Javis chỉ dịch câu đó ra tiếng Việt rồi dừng. Người dùng phải
tự nhớ giờ, tự quay lại, tự bấm "Gửi lại". Trên VPS hoặc trên điện thoại thì thường là quên,
và câu hỏi nằm đó không có câu trả lời.

Cách làm: mỗi lần một lượt vấp hạn mức mà nhà cung cấp NÓI RÕ mốc reset, ghi một mục chờ
ở đây kèm một closure chạy lại đúng lượt đó. Một task ngủ tới mốc reset (cộng vài giây trừ
hao lệch đồng hồ) rồi gọi closure. Lượt chạy lại là một job chat bình thường của server
(qua `chat_runtime`), nên tab đóng hay điện thoại tắt màn hình vẫn chạy, kết quả lưu vào kho
phiên và đẩy tới mọi tab đang mở như một lượt thường.

Ba ranh giới có chủ ý:
  - Chỉ chạy lại khi BIẾT mốc reset. Không biết thì thẻ chỉ có nút "Chạy lại ngay"; đoán
    một con giờ rồi gọi lại nhà cung cấp mỗi mười phút là đốt hạn mức của lần sau.
  - Tối đa MAX_ATTEMPTS lần tự chạy lại cho một câu hỏi. Mốc reset mà nhà cung cấp nói ra
    thỉnh thoảng sai (cửa sổ tuần chưa mở); không có trần thì Javis đợi mãi và người dùng
    không biết vì sao câu hỏi vẫn treo.
  - Sổ này nằm trong bộ nhớ tiến trình. Khởi động lại máy chủ là mất mục chờ; chấp nhận
    được vì closure chạy lại gắn với vòng đời tiến trình, và câu báo hết lượt đã được lưu
    vào kho phiên nên lịch sử không mất gì.

Module KHÔNG import FastAPI hay main: chỉ asyncio, để test được bằng một event loop trần.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

# Đợi thêm sau mốc reset. Nhà cung cấp làm tròn mốc về phút và đồng hồ hai bên lệch nhau,
# gọi đúng giây 0 là ăn thêm một lỗi hết lượt nữa và mất một lần thử.
GRACE_SECONDS = 45.0
# Xa quá thì không tự chạy lại. Cửa sổ tuần của Claude có khi mở lại sau bốn ngày; máy chủ
# gần như chắc chắn khởi động lại trong khoảng đó nên hứa "tự chạy lại" là hứa suông.
MAX_WAIT_SECONDS = 24 * 3600
# Số lần tự chạy lại tối đa cho MỘT câu hỏi.
MAX_ATTEMPTS = 3
# Mục chờ sống thêm bao lâu sau mốc reset khi không tự chạy (người dùng tắt tự động).
STALE_AFTER_SECONDS = 24 * 3600

# Closure chạy lại lượt. Nhận số thứ tự lần chạy lại (1, 2, 3...).
Runner = Callable[[int], Awaitable[Any]]


@dataclass
class PendingResume:
    session_id: str
    resume_at: float            # epoch giây; 0 = nhà cung cấp không nói
    engine: str
    notice: str                 # câu tiếng Việt đã hiện cho người dùng
    runner: Runner
    attempt: int = 0            # lượt vừa vấp là lần chạy lại thứ mấy (0 = lượt gốc)
    auto: bool = True           # còn hẹn tự chạy lại không
    reason: str = ""            # vì sao KHÔNG tự chạy: no_reset | too_far | max_attempts | off
    scope: str = ""
    created: float = field(default_factory=time.time)
    task: Optional[asyncio.Task] = None

    def payload(self, now: Optional[float] = None) -> dict:
        """Dạng gửi cho dashboard. Không kèm closure."""
        ts = time.time() if now is None else float(now)
        return {
            "session_id": self.session_id,
            "resume_at": self.resume_at,
            "wait_seconds": max(0, int(self.resume_at - ts)) if self.resume_at else 0,
            "engine": self.engine,
            "scope": self.scope,
            "auto": bool(self.auto),
            "reason": self.reason,
            "attempt": self.attempt,
            "max_attempts": MAX_ATTEMPTS,
            "notice": self.notice,
        }


class LimitResumeRegistry:
    """Sổ các lượt đang chờ chạy lại, mỗi phiên tối đa một mục."""

    def __init__(self, grace: float = GRACE_SECONDS, max_wait: float = MAX_WAIT_SECONDS,
                 max_attempts: int = MAX_ATTEMPTS) -> None:
        self._items: dict[str, PendingResume] = {}
        self.grace = float(grace)
        self.max_wait = float(max_wait)
        self.max_attempts = int(max_attempts)

    # ---- ghi ----
    def schedule(self, session_id: str, resume_at: float, runner: Runner, *,
                 engine: str = "", notice: str = "", scope: str = "",
                 attempt: int = 0, auto_default: bool = True,
                 now: Optional[float] = None) -> PendingResume:
        """Ghi một mục chờ cho phiên. Mục cũ của cùng phiên bị thay.

        `auto_default` là ý người dùng đã chọn (ô "tự tiếp tục"); các rào bên dưới chỉ có
        thể TẮT thêm chứ không bật lại được, và mỗi rào để lại `reason` để thẻ nói ra."""
        ts = time.time() if now is None else float(now)
        self.cancel(session_id)
        item = PendingResume(session_id=session_id, resume_at=float(resume_at or 0),
                             engine=engine, notice=notice, runner=runner,
                             attempt=int(attempt or 0), scope=scope, auto=bool(auto_default))
        if not item.resume_at:
            item.auto, item.reason = False, "no_reset"
        elif item.resume_at - ts > self.max_wait:
            item.auto, item.reason = False, "too_far"
        elif item.attempt >= self.max_attempts:
            item.auto, item.reason = False, "max_attempts"
        elif not item.auto:
            item.reason = "off"
        self._items[session_id] = item
        if item.auto:
            self._arm(item)
        return item

    def set_auto(self, session_id: str, enabled: bool) -> Optional[PendingResume]:
        """Bật/tắt hẹn tự chạy của một mục đang chờ. Tắt thì giữ mục để còn "Chạy lại ngay"."""
        item = self._items.get(session_id)
        if not item:
            return None
        if enabled:
            if item.reason in ("no_reset", "too_far", "max_attempts"):
                return item      # rào cứng, không bật được; giữ nguyên lý do để thẻ nói
            if not item.auto:
                item.auto, item.reason = True, ""
                # Mốc đã qua trong lúc tắt thì `_wait_then_run` ngủ đúng phần trừ hao rồi
                # chạy luôn, không hẹn một thời điểm trong quá khứ.
                self._arm(item)
        else:
            self._disarm(item)
            item.auto, item.reason = False, "off"
        return item

    def cancel(self, session_id: str) -> Optional[PendingResume]:
        """Bỏ mục chờ (người dùng gửi tin mới, hoặc lượt được chạy lại)."""
        item = self._items.pop(session_id, None)
        if item:
            self._disarm(item)
        return item

    async def run_now(self, session_id: str) -> Optional[PendingResume]:
        """Chạy lại ngay, không đợi mốc reset. Trả mục vừa chạy, None nếu không có."""
        item = self.cancel(session_id)
        if not item:
            return None
        await item.runner(item.attempt + 1)
        return item

    # ---- đọc ----
    def get(self, session_id: str) -> Optional[PendingResume]:
        return self._items.get(session_id)

    def snapshot(self, now: Optional[float] = None) -> list[dict]:
        """Danh sách mục chờ cho khung `hello`, đã dọn mục quá cũ."""
        ts = time.time() if now is None else float(now)
        out = []
        for sid, item in list(self._items.items()):
            moc = item.resume_at or item.created
            if not item.auto and ts - moc > STALE_AFTER_SECONDS:
                self._items.pop(sid, None)
                continue
            out.append(item.payload(ts))
        return out

    # ---- nội bộ ----
    def _arm(self, item: PendingResume) -> None:
        self._disarm(item)
        try:
            item.task = asyncio.get_running_loop().create_task(self._wait_then_run(item))
        except RuntimeError:
            # Không có event loop (gọi từ luồng đồng bộ/test): không hẹn được, nói rõ.
            item.task = None
            item.auto, item.reason = False, "no_loop"

    @staticmethod
    def _disarm(item: PendingResume) -> None:
        t, item.task = item.task, None
        if t and not t.done():
            t.cancel()

    async def _wait_then_run(self, item: PendingResume) -> None:
        delay = max(0.0, item.resume_at - time.time()) + self.grace
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        # Trong lúc ngủ, phiên có thể đã bị thay bằng mục khác hoặc bị huỷ.
        if self._items.get(item.session_id) is not item:
            return
        self._items.pop(item.session_id, None)
        item.task = None
        try:
            await item.runner(item.attempt + 1)
        except Exception as exc:   # noqa: BLE001 - task nền, không có ai bắt phía trên
            import sys
            print(f"[limit_resume] chạy lại {item.session_id[:12]} lỗi: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)


REGISTRY = LimitResumeRegistry()
