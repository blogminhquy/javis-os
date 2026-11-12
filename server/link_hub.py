"""Zero-token link hub: intercept link-only messages and append them to a
markdown table in the brain vault, without ever invoking the AI model.

Usage from the WebSocket receive loop and the Telegram precheck:

    urls, note = link_hub.detect(user_message)
    if urls:
        confirm = link_hub.save(brain_root, urls, note, source="Dashboard")
        # send *confirm* back and skip the AI turn
"""

from __future__ import annotations

import os
import re

import localefmt

HUB_RELPATH = "content/references/content-manager/references/hop-thu-link.md"

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

_INSTRUCTION_RE = re.compile(
    r"(?:"
    r"ph[aâ]n t[ií]ch|gi[aả]i th[ií]ch|t[oổ]ng h[oợ]p|[đd][aá]nh gi[aá]"
    r"|review|analyze|explain|summarize|compare"
    r"|so s[aá]nh|ki[eể]m tra|t[oó]m t[aắ]t"
    r"|l[aà] g[ìi]|ngh[ĩi]a l[aà]|th[eế] n[aà]o|what|how|why|v[ìi] sao"
    r")",
    re.IGNORECASE,
)

_MAX_NOTE_LEN = 60


def detect(text: str) -> tuple[list[str], str]:
    """Return (urls, note) when *text* is a link-only message, else ([], "")."""
    urls = _URL_RE.findall(text)
    if not urls:
        return [], ""
    remaining = _URL_RE.sub("", text).strip()
    if len(remaining) > _MAX_NOTE_LEN:
        return [], ""
    if "?" in remaining:
        return [], ""
    if _INSTRUCTION_RE.search(remaining):
        return [], ""
    return urls, remaining


def hub_path(brain_root: str) -> str:
    return os.path.join(brain_root, HUB_RELPATH)


def save(brain_root: str, urls: list[str], note: str,
         source: str = "Dashboard") -> str:
    """Append *urls* to the hub table. Returns a short confirmation string."""
    path = hub_path(brain_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    now = localefmt.now()
    date_str = now.strftime("%d/%m %H:%M")

    rows = []
    for url in urls:
        rows.append(f"| {date_str} | {source} | {url} | {note} |  |")

    block = "\n".join(rows) + "\n"

    if not os.path.exists(path):
        header = (
            "# Hộp thư link tham khảo\n\n"
            "| Ngày giờ | Nguồn | Link | Lời kèm | CM đã xử lý |\n"
            "| --- | --- | --- | --- | --- |\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + block)
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(block)

    n = len(urls)
    return localefmt.chu(
        f"✓ Lưu {n} link vào hộp thư tham khảo",
        f"✓ Saved {n} link{'s' if n > 1 else ''} to the reference hub",
    )
