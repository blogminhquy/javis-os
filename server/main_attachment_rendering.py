"""Pure attachment templates shared by ordinary main and protected trial context.

Callers own source reads, authorization, row order and completeness. ``loaded`` is
an aligned sequence of decoded text, bounded ordinary prefixes or None, preserving
separate observations of duplicate paths. The protected flag preserves every row
and requires full pinned text; it does not authorize or certify those sources.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PreparedAttachmentText:
    """Bound ordinary retention while retaining the true source character count."""

    prefix: str
    original_char_length: int

    def __post_init__(self):
        if (not isinstance(self.prefix, str) or type(self.original_char_length) is not int
                or self.original_char_length < len(self.prefix)):
            raise ValueError("invalid_prepared_attachment_text")


def render_attachment_lists(files, links, loaded, *, list_max, allowed_suffixes,
                            file_max, total_max, preserve_full_protected=False):
    """Return legacy list lines and loaded sections from already observed inputs."""
    lines, sections, remaining = [], [], total_max
    for index, item in enumerate(files if preserve_full_protected else files[:list_max]):
        name, path = item.get("name") or "", item.get("path") or ""
        # A stored path ending in "/" is a whole folder (2026-11-12). Pinned, its `loaded` text is a short tree of
        # what it holds, prepared by the caller; every file row renders exactly as before.
        is_dir = path.endswith("/")
        kind = "thư mục" if is_dir else "file"
        if not item.get("pinned"):
            lines.append(f"- [{kind}] {name} - {path}")
            continue
        if not is_dir and os.path.splitext(path)[1].lower() not in allowed_suffixes:
            lines.append(f"- [file, đã ghim nhưng là tệp nhị phân - tự mở khi cần] {name} - {path}")
            continue
        content = loaded[index] if index < len(loaded) else None
        if content is None:
            lines.append(f"- [{kind}, đã ghim nhưng đọc không được] {name} - {path}")
            continue
        if isinstance(content, PreparedAttachmentText):
            original_length = content.original_char_length
            if preserve_full_protected and original_length != len(content.prefix):
                raise ValueError("protected_attachment_requires_full_text")
            content = content.prefix
        else:
            original_length = len(content)
        chunk = content if preserve_full_protected else content[:min(file_max, max(0, remaining))]
        if not chunk and not preserve_full_protected:
            lines.append(f"- [{kind}, đã ghim nhưng hết chỗ nạp trong lượt này] {name} - {path}")
            continue
        remaining -= len(chunk)
        clipped = " (đã cắt bớt)" if len(chunk) < original_length else ""
        sections.append(f"\n## {name} - {path}{clipped}\n{chunk}")
    for item in links if preserve_full_protected else links[:list_max]:
        lines.append(f"- [link] {item.get('label') or item.get('url')} - {item.get('url')}"
                     + (" (ghim)" if item.get("pinned") else ""))
    return lines, sections


def render_project_assets(lines, sections):
    """Render the ordinary project asset headers without reading source content."""
    result = ""
    if lines:
        result += ("\n\n# === TÀI LIỆU & LINK CỦA PROJECT ===\n"
                   "Đây là DANH SÁCH, không phải nội dung: mở file bằng tool đọc file khi cần, "
                   "đừng đoán nội dung từ cái tên. Link chỉ mở được nếu lượt này có tool duyệt web; "
                   "không có thì nói thẳng chứ đừng đoán nội dung trang.\n" + "\n".join(lines))
    if sections:
        result += ("\n\n# === NỘI DUNG FILE ĐÃ GHIM (nạp sẵn, không cần mở lại) ===" + "".join(sections))
    return result


def render_session_assets(lines, sections):
    """Render the ordinary session asset headers without reading source content."""
    result = ""
    if lines:
        result += ("\n\n# === TÀI LIỆU & LINK NGƯỜI DÙNG GẮN VÀO CUỘC NÀY ===\n"
                   "Người dùng tự gắn tay ở khung \"Trong cuộc trò chuyện này\", nên đây là thứ họ "
                   "coi là quan trọng cho ĐÚNG cuộc này. Vẫn là DANH SÁCH chứ không phải nội dung: "
                   "mở file bằng tool đọc file khi cần, đừng đoán nội dung từ cái tên.\n"
                   + "\n".join(lines))
    if sections:
        result += ("\n\n# === NỘI DUNG FILE ĐÃ GHIM TRONG CUỘC NÀY (nạp sẵn, không cần mở lại) ==="
                   + "".join(sections))
    return result
