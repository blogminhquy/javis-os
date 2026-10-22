"""A bot answer sent as several short chat messages instead of one long block (0.281.0).

Owner request 2026-10-22: "khi nhắn tin bot có thể quyết định nhắn nhiều tin ngắn cho khách chứ không gom vào 1 tin dài
rất khó đọc, phần này bot tự quyết định được". The Agent decides: it writes a line holding only `SPLIT_MARK` between the
messages, the channel sends each part as its own message. Javis never splits on its own (a blank line inside one
message is normal writing), it only honours the marker.

Only channels in `SPLIT_CHANNELS` send parts separately; everywhere else (and in the inbox, the bot log, a draft for
the owner) the marker becomes a blank line, so it can never reach a customer as text.
"""
from __future__ import annotations

import re
from typing import Any, List

SPLIT_MARK = "[TACH_TIN]"
MAX_PARTS = 4                  # more than this reads like spam: the rest is joined into the last message
SPLIT_CHANNELS = ("zalo_personal",)
_MARK_RE = re.compile(r"\s*\[\s*tach_tin\s*\]\s*", re.I)

PROMPT_HINT = f"""
## Nhắn nhiều tin ngắn

Khách đọc trên điện thoại. Khi câu trả lời có từ hai ý trở lên (ví dụ báo giá rồi gợi ý thêm), bạn được
tách thành nhiều tin ngắn như người thật nhắn: đặt một dòng chỉ có `{SPLIT_MARK}` giữa các tin, tối đa
{MAX_PARTS} tin. Mỗi tin một ý, vài câu. Câu trả lời chỉ có một ý thì gửi một tin, không cần tách.
"""


def has_mark(text: Any) -> bool:
    return bool(_MARK_RE.search(str(text or "")))


def parts(text: Any, max_parts: int = MAX_PARTS) -> List[str]:
    """The messages of one answer, empty parts dropped, at most `max_parts` (the overflow joins the last one)."""
    ds = [p.strip() for p in _MARK_RE.split(str(text or ""))]
    ds = [p for p in ds if p]
    if len(ds) > max_parts:
        ds = ds[:max_parts - 1] + ["\n\n".join(ds[max_parts - 1:])]
    return ds


def joined(text: Any) -> str:
    """The answer as ONE message: each marker becomes a blank line. For channels and records that do not split."""
    if not has_mark(text):
        return str(text or "")
    return "\n\n".join(parts(text, max_parts=10 ** 6))
