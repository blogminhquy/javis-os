"""Keep a Claude Code chat turn open while its background work runs (0.453.0, issue #898 item 1).

Lives in its own module on purpose: `claude_sdk_engine.py` is pinned byte for byte to the source the native trial path
was qualified with (docs/superpowers/evidence/2026-10-25-m5-native-qualification-cli310.json, checked by
tests/python/test_plan_limits.py and test_improvement_view_reservations.py), so the wait is wired into the owner's chat
lane (`claude_warm.py`, the lane every dashboard chat turn takes while the warm pool has room) without touching it.
The plain lane of `claude_sdk_engine.py` (background lanes, a machine with the warm pool off) keeps ending at the first
ResultMessage until it is qualified again.
"""
from __future__ import annotations

import localefmt


# 0.453.0 (issue #898, item 1): a turn that started background work (a background shell, a sub-agent) used to end at its
# first ResultMessage: Javis disconnected, Claude Code went away with its tasks, and the follow-up that should read their
# result never came. Seen first on Windows, where Javis' own adoption of leftover processes (tien_trinh_nen) does not run,
# but the disconnect is the same everywhere. Now the turn stays connected while Claude Code reports tasks still running,
# then reads the follow-up turn Claude Code starts by itself, or nudges it once when it does not.
BG_WAIT_DEFAULT = "1800"     # JAVIS_CLAUDE_BG_WAIT, seconds; 0 turns the wait off (old behaviour)
BG_NUDGE_S = 20.0            # tasks done and Claude Code silent this long: Javis asks it to carry on
BG_MAX_ROUNDS = 5            # a follow-up that starts more background work again: at most this many waits per turn
BG_NUDGE = ("[Javis] Các việc chạy nền của lượt này đã xong. Đọc kết quả của chúng, làm nốt phần việc đang dở rồi báo "
            "kết quả cho người dùng. Đừng bật thêm việc nền mới nếu không thật cần.")


class BackgroundWait:
    """Keep a turn open while Claude Code's background tasks run (see BG_WAIT_DEFAULT). Pure bookkeeping: the read loop
    asks `due` for its next timeout, tells `observe` every message and `merge` every event, and calls `keep_going` at a
    ResultMessage. Uses `_CompletionWatch.tasks`, the task ids Claude Code reported started and not yet finished."""

    def __init__(self, cap, nudge_after=None, max_rounds=None):
        self.cap = cap
        self.nudge_after = BG_NUDGE_S if nudge_after is None else nudge_after
        self.max_rounds = BG_MAX_ROUNDS if max_rounds is None else max_rounds
        self.deadline = None
        self.waiting = False
        self.resumed = False
        self.nudged = False
        self.idle_since = None
        self.rounds = 0
        self.prior = ""
        self.last_final = ""

    def keep_going(self, msg, completion, now) -> bool:
        """At a ResultMessage: True = background tasks are still running, keep reading the next turn."""
        if not self.cap or getattr(msg, "is_error", False) or not completion.tasks or self.rounds >= self.max_rounds:
            self.waiting = False
            return False
        if self.deadline is None:
            self.deadline = now + self.cap
        self.rounds += 1
        completion.deadline = None   # the first answer's end_turn timer must not cut the wait short
        self.prior = self.last_final
        self.waiting, self.resumed, self.nudged, self.idle_since = True, False, False, None
        return True

    def due(self, completion, now):
        """(seconds, reason) the loop should wait at most while waiting, or None. Reasons: "bg" (the overall cap) and
        "bg_nudge" (tasks are done and Claude Code has said nothing: time to nudge it)."""
        if not self.waiting:
            return None
        left = max(0.0, self.deadline - now)
        if completion.tasks or self.resumed or self.nudged:
            self.idle_since = None
            return left, "bg"
        if self.idle_since is None:
            self.idle_since = now
        nudge = max(0.0, self.idle_since + self.nudge_after - now)
        return (nudge, "bg_nudge") if nudge < left else (left, "bg")

    def observe(self, msg) -> bool:
        """True on the first message of the follow-up turn (the loop puts a paragraph break in the streamed text)."""
        if not self.waiting or self.resumed:
            return False
        from claude_agent_sdk import AssistantMessage, StreamEvent
        if isinstance(msg, StreamEvent):
            if (msg.event or {}).get("type") == "ping" or msg.parent_tool_use_id:
                return False
        elif not isinstance(msg, AssistantMessage) or msg.parent_tool_use_id:
            return False
        self.resumed = True
        return True

    def nudge(self) -> None:
        self.nudged = True

    def merge(self, ev: dict) -> dict:
        """The follow-up's final carries the first answer too: the chat keeps the LAST final as the saved answer."""
        if ev.get("type") == "final":
            content = str(ev.get("content") or "")
            if self.prior and content and content != self.prior:
                ev = dict(ev, content=self.prior + "\n\n" + content)
            elif self.prior and not content:
                ev = dict(ev, content=self.prior)
            self.last_final = str(ev.get("content") or "")
        return ev

    def gave_up_text(self) -> str:
        mins = int((self.cap or 0) // 60)
        return localefmt.chu(
            f"\n\n_(Javis đã chờ việc chạy nền {mins} phút mà chưa xong nên ngừng chờ. Nhắn \"làm tiếp\" khi muốn xem "
            f"kết quả; JAVIS_CLAUDE_BG_WAIT đổi thời gian chờ.)_",
            f"\n\n_(Javis waited {mins} minutes for the background work and it is still not done, so it stopped "
            f"waiting. Send \"carry on\" when you want the result; JAVIS_CLAUDE_BG_WAIT changes the wait.)_")


def bg_wait_cap():
    """Seconds a turn may stay open for background work (None = off)."""
    from claude_sdk_engine import tran_watchdog
    return tran_watchdog("JAVIS_CLAUDE_BG_WAIT", BG_WAIT_DEFAULT)
