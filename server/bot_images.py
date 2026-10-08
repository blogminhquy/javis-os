"""Images a dedicated bot sends with its reply (0.84.3).

Before this, every bot turn returned `"files": []` (`main._bot_ket`), so no bot on any channel could send a picture,
even though the Telegram, Slack and WhatsApp transports already knew how to send `files`. Javis deliberately does
NOT auto-attach files the turn produced (`main._bot_tra_loi_co_tool`): with a stranger steering the model, "the file
that happened to appear" is a leak path.

So a bot sends an image only when its Agent ASKS for it, by writing a Markdown image `![caption](path)` in the reply,
and only when that path passes every gate here:

  - it resolves INSIDE the bot's own brain (symlinks resolved too), never another brain or the machine;
  - it is an existing image file (`IMAGE_EXTS`), not a document: a bot that may quote a document must still not
    hand out the raw file, and that is a separate decision from images;
  - it is at most `MAX_BYTES`, and at most `MAX_IMAGES` per reply.

A path that fails stays in the text as written, so the owner can see in the inbox what the Agent tried to send.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple
from urllib.parse import unquote

import channel_context
import channels

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MAX_IMAGES = 4
MAX_BYTES = 10 * 1024 * 1024

# What the Agent reads so it knows the capability exists. Bot prompts are Vietnamese (see chatbot_runtime).
PROMPT_HINT = ("\nGỬI ẢNH: muốn gửi ảnh cho người đang nói chuyện, chèn ![mô tả ngắn](đường-dẫn-ảnh) vào câu trả lời, "
               "đường dẫn tính từ gốc tài liệu của bạn (vd attachments/san-pham.jpg). Chỉ ảnh có thật trong tài liệu "
               "của bạn mới được gửi, tối đa " + str(MAX_IMAGES) + " ảnh mỗi lần. Không bịa đường dẫn.")


def channel_sends_files(channel: str) -> bool:
    """Whether the channel's transport sends a reply's `files` (`nang_luc.gui_file`)."""
    spec = channels.spec(str(channel or ""))
    return bool(spec and spec.nl("gui_file"))


def _resolve(raw: str, brain_root: str) -> str:
    """Absolute path of an allowed image for one Markdown target, else ""."""
    raw = str(raw or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("file:"):
        raw = re.sub(r"^file:(//[^/]*)?", "", raw, flags=re.IGNORECASE)
        if re.match(r"^/[A-Za-z]:[\\/]", raw):
            raw = raw[1:]
    try:
        root = Path(brain_root).resolve()
    except (OSError, ValueError):
        return ""
    for variant in dict.fromkeys((raw, unquote(raw))):
        cand = channel_context._vault_markdown_candidate(variant, str(root))
        if not cand:
            continue
        try:
            p = Path(cand).resolve()
            p.relative_to(root)                 # a symlink pointing outside the brain fails here
        except (OSError, ValueError):
            continue
        if p.suffix.lower() not in IMAGE_EXTS or not p.is_file():
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        return str(p)
    return ""


def pick(text: str, brain_root: str) -> Tuple[str, List[dict]]:
    """Split the images the Agent asked to send out of `text`.

    Returns `(text without those images, [{"path": absolute path, "caption": alt text}])`. Images that fail a gate,
    links that are not images, and web URLs are left in the text untouched."""
    if not text or not brain_root or "![" not in text:
        return text or "", []
    files: List[dict] = []
    seen = set()

    def repl(m):
        if m.group(1) != "!" or len(files) >= MAX_IMAGES:
            return m.group(0)
        path = _resolve(channel_context._md_link_target(m), brain_root)
        if not path:
            return m.group(0)
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            files.append({"path": path, "caption": (m.group(2) or "").strip()[:200]})
        return ""

    cleaned = channel_context._MD_LINK_RE.sub(repl, text)
    if not files:
        return text, []
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), files
