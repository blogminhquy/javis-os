"""Ring the bell when a long chat turn finishes (the owner has usually left the screen by then).

The owner reported on 2026-11-04: a long video render or edit started from the chat finished, and nothing told them,
neither the chat nor the notifications. A background job Javis tracks already reports through `_notify_owner`, but the
answer that matters comes after it: the turn that waited for Claude Code's background task, or the follow-up turn
Javis opens when a tracked job ends (it adds the audio, checks the file, sends the link). Both are ordinary chat turns,
whose answer lands in the chat only, so a phone in a pocket never hears of it.

So a dashboard chat turn that ran at least `threshold_s()` (JAVIS_LONG_TURN_NOTIFY_S, default 180 seconds, 0 turns it
off), or that is a background job's follow-up, also leaves its answer in the bell, which sends the push notification.
The push is skipped on a device where Javis is open and in front of the owner (dashboard/sw.js, `quiet_if_visible`).

Pure functions: main.py does the delivery (`_bao_luot_dai_xong`).
"""
from __future__ import annotations

import os
import re

DEFAULT_THRESHOLD_S = 180
# The first line of the message main.py opens a follow-up turn with when a tracked background job ends.
FOLLOWUP_HEAD = "[Việc chạy nền đã xong]"
MAX_BODY = 600


def threshold_s() -> float:
    """Seconds a turn must run before its answer rings the bell. 0 = only background follow-ups ring."""
    raw = os.getenv("JAVIS_LONG_TURN_NOTIFY_S", "").strip()
    if not raw:
        return float(DEFAULT_THRESHOLD_S)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(DEFAULT_THRESHOLD_S)


def is_followup(user_message: str) -> bool:
    return str(user_message or "").lstrip().startswith(FOLLOWUP_HEAD)


def should_notify(elapsed_s: float, user_message: str, final_text: str) -> bool:
    if not str(final_text or "").strip():
        return False
    if is_followup(user_message):
        return True
    thr = threshold_s()
    return bool(thr) and float(elapsed_s or 0) >= thr


def notice_text(final_text: str) -> str:
    """The answer itself, cut for the bell: its first line becomes the notification title."""
    t = re.sub(r"\n{3,}", "\n\n", str(final_text or "").strip())
    if len(t) > MAX_BODY:
        t = t[:MAX_BODY].rstrip() + "..."
    return t


def duration_text(elapsed_s: float) -> str:
    import localefmt
    g = max(0, int(elapsed_s or 0))
    if g < 60:
        return localefmt.chu(f"{g} giây", f"{g} s")
    if g < 3600:
        return localefmt.chu(f"{g // 60} phút", f"{g // 60} min")
    return localefmt.chu(f"{g // 3600} giờ {(g % 3600) // 60} phút", f"{g // 3600} h {(g % 3600) // 60} min")


def label(elapsed_s: float, user_message: str = "") -> str:
    import localefmt
    if is_followup(user_message):
        return localefmt.chu("Việc chạy nền xong", "Background job done")
    return localefmt.chu(f"Trả lời xong sau {duration_text(elapsed_s)}",
                         f"Answered after {duration_text(elapsed_s)}")
