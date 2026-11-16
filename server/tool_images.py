"""An image a connection tool returns is saved in the brain, so the owner can see it in the chat.

An MCP tool may answer with an `image` content block (base64 `data` plus `mimeType`): Playwright's
browser_take_screenshot does, and so do chart and design tools. `mcp_client._format_result` used to turn that
block into JSON text. The model got a few hundred KB of base64 it could not look at, and the chat showed nothing,
so the owner never saw the screenshot they asked for (owner's report, 2026-11-16).

During a model's tool call the hub says which brain the call belongs to (`saving_to`, set in
`mcp_hub._shaped_call`). Inside that scope an image block is written under `<attachments>/tool-images/` of that
brain and replaced by one line: the relative path and the `![...](path)` that the chat renders inline, the same
convention `javis_generate_image` uses. Everywhere else (an internal caller, no brain, unknown or broken data) the
block is left exactly as before.
"""
from __future__ import annotations

import base64
import binascii
import contextvars
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SUBDIR = "tool-images"
MAX_BYTES = 25 * 1024 * 1024        # a full-page screenshot is a few MB; anything bigger is not a preview

# (vault root, tool name) of the model's tool call running in this context; empty outside one.
_scope = contextvars.ContextVar("javis_tool_image_scope", default=("", ""))

# The bytes decide the type, not the declared mimeType. SVG is left out on purpose: it can carry script.
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)
_ATTACHMENTS_RE = re.compile(r"^(\d+\s*[-_.]\s*)?attachments$", re.IGNORECASE)


@contextmanager
def saving_to(vault_root, tool=""):
    """Inside this block an image block from a tool is saved into `vault_root`. An empty root changes nothing."""
    token = _scope.set((str(vault_root or ""), str(tool or "")))
    try:
        yield
    finally:
        _scope.reset(token)


def current():
    return _scope.get()


def _kind(raw: bytes) -> str:
    for magic, ext in _SIGNATURES:
        if raw.startswith(magic):
            return ext
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return ""


def _attachments_dir(vault: Path) -> Path:
    """The brain's attachments folder ("attachments", "Attachments", "05 - Attachments"), like image_gen."""
    try:
        for name in sorted(os.listdir(vault)):
            if _ATTACHMENTS_RE.match(name.strip()) and (vault / name).is_dir():
                return vault / name
    except OSError:
        pass
    return vault / "attachments"


def _slug(tool: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", tool.lower()).strip("-")[:60] or "tool"


def note_for(block) -> str | None:
    """The line that replaces an image block, or None to leave the block as it was."""
    vault, tool = _scope.get()
    if not vault or not isinstance(block, dict) or block.get("type") != "image":
        return None
    if not str(block.get("mimeType") or "").lower().startswith("image/"):
        return None
    data = block.get("data")
    if not isinstance(data, str) or not data:
        return None
    try:
        raw = base64.b64decode("".join(data.split()), validate=True)
    except (binascii.Error, ValueError):
        return None
    ext = _kind(raw)
    if not ext or len(raw) > MAX_BYTES:
        return None
    root = Path(vault)
    if not root.is_dir():
        return None                     # never create a brain folder that is not there
    folder = _attachments_dir(root) / SUBDIR
    path = folder / f"{_slug(tool)}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.{ext}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    except OSError:
        return None
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    alt = "screenshot" if "screenshot" in tool.lower() else "image"
    return (f"[Image from this tool saved in the brain: {rel} ({max(1, len(raw) // 1024)} KB). The owner sees it "
            f"only if you show it: put ![{alt}]({rel}) in your reply. To look at it yourself, open {path}]")
