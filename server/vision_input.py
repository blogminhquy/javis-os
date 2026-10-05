"""vision_input.py - put a customer's photo INTO the chat turn, so the bot's own model looks at it (0.81.0).

Owner decision (2026-10-05): no second model "describing" the photo for the bot (that was ChatGPT in 0.74.1, and it meant no ChatGPT
= no eyes for any brain). The photo is downloaded into the bot's brain (inbox/ or attachments/, swept by media_gc after 30 days or
300 MB) and sent as image input in the SAME turn to whatever model runs the bot. A model that cannot see images gets the old honest
label instead and never guesses.

The neutral shape inside Javis is the OpenAI Chat Completions content list, because six providers already speak it natively
(OpenAI, Gemini's OpenAI endpoint, Groq, Ollama, OpenAI-compatible, OpenRouter):
    [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]
Only the last user message of a turn ever carries it; history keeps plain text, so nothing heavy is resent on later turns.
`to_anthropic` / `to_responses` / `split_last_images` convert for the providers with another shape.

Stdlib only, plus Pillow when present (to shrink big photos); without Pillow a photo under the size cap is sent as is.
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import List, Optional, Tuple

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MAX_IMAGES = 4               # per turn; customers rarely send more, and each image costs real tokens
MAX_SIDE = 1568              # Anthropic's recommended long side; larger only costs tokens, never accuracy
MAX_RAW_BYTES = 4_500_000    # under Anthropic's 5 MB per-image limit, also when Pillow is missing
MAX_INPUT_BYTES = 25_000_000 # never read a file bigger than this into memory

# Providers whose bot path can carry image input today. The two remaining CLI brains (Antigravity, Grok Build) take one prompt
# string with no image channel, so they get the honest label instead.
SUPPORTED = ("openai", "openrouter", "gemini", "groq", "ollama", "ollama-local", "openai-compat",
             "anthropic-api", "anthropic", "openai-oauth", "anthropic-cli")

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
_DATA_URL = re.compile(r"^data:(image/[\w.+-]+);base64,(.+)$", re.S)


def supported(prov: str) -> bool:
    """Can this provider's bot path send image input. Unknown names fall to the Anthropic API path in `_api_stream`, so treat
    an empty provider like that."""
    return str(prov or "anthropic-api") in SUPPORTED


def is_image_path(p) -> bool:
    return Path(str(p or "")).suffix.lower() in IMAGE_EXTS


def load(path) -> Optional[Tuple[str, str]]:
    """(mime, base64) for one image file, shrunk to `MAX_SIDE` and re-encoded when Pillow is available. None when the file is
    missing, too big, or not an image Pillow can open."""
    p = Path(str(path or ""))
    try:
        size = p.stat().st_size
    except OSError:
        return None
    if not size or size > MAX_INPUT_BYTES or not is_image_path(p):
        return None
    raw = p.read_bytes()
    try:
        from PIL import Image
    except Exception:      # noqa: BLE001 - no Pillow: send small files as they are
        if size > MAX_RAW_BYTES:
            return None
        return _MIME.get(p.suffix.lower(), "image/jpeg"), base64.b64encode(raw).decode("ascii")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        if getattr(im, "is_animated", False):
            im.seek(0)       # a GIF: the first frame is what a person would describe
        w, h = im.size
        small_enough = max(w, h) <= MAX_SIDE and size <= MAX_RAW_BYTES
        if small_enough and p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            return _MIME[p.suffix.lower()], base64.b64encode(raw).decode("ascii")
        if max(w, h) > MAX_SIDE:
            k = MAX_SIDE / float(max(w, h))
            im = im.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
        if im.mode in ("RGBA", "LA", "P"):
            # Logos and screenshots often have transparency; a white background is what the customer saw in the chat app.
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85, optimize=True)
        return "image/jpeg", base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:      # noqa: BLE001 - a file Pillow cannot read is not an image we can show
        return None


def user_parts(text: str, paths) -> Optional[list]:
    """OpenAI-shape content for one user turn: the text, then up to `MAX_IMAGES` images. None when no image could be loaded,
    so the caller keeps sending plain text."""
    imgs = [x for x in (load(p) for p in list(paths or [])[:MAX_IMAGES]) if x]
    if not imgs:
        return None
    parts: list = [{"type": "text", "text": str(text or "")}]
    for mime, b64 in imgs:
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return parts


def content_text(content) -> str:
    """The text of a content value, whether a plain string or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(p.get("text") or "") for p in content
                         if isinstance(p, dict) and p.get("type") in ("text", "input_text", "output_text")).strip()
    return str(content or "")


def _images_of(content) -> List[Tuple[str, str]]:
    out = []
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "image_url":
                m = _DATA_URL.match(str((p.get("image_url") or {}).get("url") or ""))
                if m:
                    out.append((m.group(1), m.group(2)))
    return out


def has_images(messages) -> bool:
    return any(_images_of(m.get("content")) for m in (messages or []) if isinstance(m, dict))


def split_last_images(messages) -> Tuple[list, List[Tuple[str, str]]]:
    """(messages with every content as plain text, images of the turn). For engines that take one prompt string
    (Claude Code) and attach images on the side."""
    imgs: List[Tuple[str, str]] = []
    out = []
    for m in messages or []:
        c = m.get("content")
        if isinstance(c, list):
            imgs += _images_of(c)
            m = dict(m, content=content_text(c))
        out.append(m)
    return out, imgs


def strip_images(messages) -> list:
    """Same messages, images removed (text kept). For the retry when a model rejects image input."""
    return split_last_images(messages)[0]


def to_anthropic(content):
    """OpenAI-shape content -> Anthropic Messages content. Strings pass through untouched."""
    if not isinstance(content, list):
        return content
    blocks = []
    for p in content:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            blocks.append({"type": "text", "text": str(p.get("text") or "")})
        elif p.get("type") == "image_url":
            m = _DATA_URL.match(str((p.get("image_url") or {}).get("url") or ""))
            if m:
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": m.group(1), "data": m.group(2)}})
    # Anthropic reads images best placed BEFORE the question.
    return [b for b in blocks if b["type"] == "image"] + [b for b in blocks if b["type"] != "image"]


def anthropic_blocks(text: str, imgs: List[Tuple[str, str]]) -> list:
    """Content blocks for a Claude Code turn: images first, then the prompt text."""
    return ([{"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}} for mime, b64 in imgs]
            + [{"type": "text", "text": str(text or "")}])


def to_responses(content, role: str = "user") -> list:
    """OpenAI-shape content -> Responses API content items (ChatGPT plan, Codex backend)."""
    ttype = "input_text" if role == "user" else "output_text"
    if not isinstance(content, list):
        return [{"type": ttype, "text": str(content or "")}]
    items = []
    for p in content:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            items.append({"type": ttype, "text": str(p.get("text") or "")})
        elif p.get("type") == "image_url" and role == "user":
            items.append({"type": "input_image", "image_url": str((p.get("image_url") or {}).get("url") or "")})
    return items


# ---- Attachment markers written by the channel gateways --------------------------------------------------------------
# Telegram, Zalo Bot, Slack and WhatsApp download a file and put one line in the text: "[Người dùng gửi ảnh qua Telegram,
# gateway đã tải về: <path>]". For the owner's own chat that line is useful (a CLI engine opens the path). For a bot talking
# to a stranger it is wrong twice: the model cannot open it (no tools) and the line leaks a server path the model may repeat.
_MARKER = re.compile(r"\[(?:Người dùng|The user|User) (?:gửi|sent)[^\]\n]*?(?:đã tải về|downloaded(?: to)?):\s*([^\]\n]+?)\]")


def take_image_markers(text: str, root=None) -> Tuple[str, List[str]]:
    """(text without image-download markers, image paths). Only image files, and only inside `root` when given (a bot may
    never be shown a file outside its own brain). Non-image markers (a PDF...) stay in the text untouched."""
    paths: List[str] = []
    base = Path(str(root)).resolve() if root else None

    def _sub(m):
        raw = m.group(1).strip()
        p = Path(raw)
        if not is_image_path(p):
            return m.group(0)
        try:
            rp = p.resolve()
            if base is not None and base not in rp.parents:
                return m.group(0)
        except OSError:
            return m.group(0)
        paths.append(str(rp))
        return ""

    out = _MARKER.sub(_sub, str(text or ""))
    return out.strip(), paths
