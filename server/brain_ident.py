"""One brain, many spellings: compare brain identifiers by what they point at (issue #716).

The same brain reaches the stores in several shapes. The dashboard sends the short alias
"brain" for the default brain and "<dir>" (from "path:<dir>") for any other; Telegram `/brain`,
chat tools and older records store an absolute path such as "/brains/Brain Default". A filter
that compares those strings directly hides a bot from the brain it belongs to.

`same_brain` resolves both sides to an absolute path and compares those. It is strict on
purpose: an unknown or deleted path is NOT folded into the default brain (unlike
`main._brain_root`, which falls back to the default for a chat turn), so a filter never shows
another brain's records under Brain Default.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_ALIAS = "brain"
_default_dir_fn: Optional[Callable[[], Any]] = None


def set_default_dir(fn: Callable[[], Any]) -> None:
    """main.py hands over its `_default_brain_dir` so both sides agree on the default brain."""
    global _default_dir_fn
    _default_dir_fn = fn


def default_dir() -> Path:
    if _default_dir_fn is not None:
        return Path(_default_dir_fn())
    root = Path(__file__).resolve().parent.parent
    return Path(os.getenv("BRAINS_DIR", str(root / "brains"))) / "Brain Default"


def canonical(value: Any) -> str:
    """Absolute resolved path of a brain identifier, or "" when it names no brain."""
    v = str(value or "").strip()
    if v.startswith("path:"):
        v = v[5:].strip()
    if not v:
        return ""
    p = default_dir() if v == DEFAULT_ALIAS else Path(v).expanduser()
    try:
        return str(p.resolve())
    except OSError:
        return str(p)


def same_brain(a: Any, b: Any) -> bool:
    """True when two brain identifiers name the same brain. Empty never matches anything."""
    sa, sb = str(a or "").strip(), str(b or "").strip()
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    ca = canonical(sa)
    return bool(ca) and ca == canonical(sb)
