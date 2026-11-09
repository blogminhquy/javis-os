"""Which brain is the default one (2026-11-09).

The default brain used to be the folder `<BRAINS_DIR>/Brain Default`, fixed in the code, so it could never be deleted:
every record that says "brain" (the dashboard's short name for the default brain), every chat turn whose brain folder is
gone, and the GitHub backup's "always restore the default brain" rule all lead there. The owner asked to delete it
(2026-11-09, "liệu có thể cho quyền xóa default brain không"). Deleting it alone would not stick: the folder is
created again on the next call and the backup restores it. So the default became a CHOICE: the owner picks another
brain as the default in the brain picker, and the old one turns into an ordinary brain that can be deleted.

Where the choice lives. A small file at the top of BRAINS_DIR, `.javis-default-brain.json`, not settings.json:
- the GitHub backup syncs everything under BRAINS_DIR (tombstones live there too), so every machine sharing the repo
  agrees on which brain is the default. With a per-machine setting, a machine still pointing at the old brain would
  keep restoring it and push it back to the others after it was deleted;
- processes that never import main (the MCP hub, plugins) read the same file;
- the name starts with a dot, so the brain list never shows it as a brain.

No file, an unreadable file or a bad name: the default is `Brain Default`, exactly as before this module existed.
The chosen folder is NOT required to exist: like `Brain Default` before, the default brain's folder is created again
when it is missing (main._default_brain_dir), instead of silently falling back to the old folder and bringing it back.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

FALLBACK_FOLDER = "Brain Default"
POINTER_FILE = ".javis-default-brain.json"

_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_lock = threading.Lock()
# path of the pointer file -> (mtime_ns, size, folder). `_default_brain_dir` is called on hot paths (every chat turn,
# every filter), so the file is read again only when it changed.
_cache: dict = {}


def valid_folder(name) -> bool:
    """A folder name that can be the default brain: one plain path segment, not hidden, no path tricks."""
    n = str(name or "")
    if not n or n != n.strip() or n in (".", "..") or n.startswith("."):
        return False
    if len(n) > 200 or _BAD_CHARS.search(n):
        return False
    return True


def pointer_path(brains_dir) -> Path:
    return Path(brains_dir) / POINTER_FILE


def _read_pointer(p: Path) -> Optional[str]:
    try:
        st = p.stat()
    except OSError:
        return None
    key = str(p)
    sig = (st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == sig:
            return hit[1]
    folder = None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and valid_folder(data.get("folder")):
            folder = str(data["folder"])
    except (OSError, ValueError):
        folder = None
    with _lock:
        _cache[key] = (sig, folder)
    return folder


def folder(brains_dir) -> str:
    """The folder name of the default brain inside `brains_dir`."""
    return _read_pointer(pointer_path(brains_dir)) or FALLBACK_FOLDER


def path(brains_dir) -> Path:
    """The default brain's folder. Never creates anything (main._default_brain_dir does that)."""
    return Path(brains_dir) / folder(brains_dir)


def brains_dir_from_env() -> Path:
    """BRAINS_DIR the way main.py derives it, for modules that must not import main."""
    return Path(os.getenv("BRAINS_DIR", str(Path(__file__).resolve().parent.parent / "brains")))


def set_folder(brains_dir, name: str) -> Tuple[bool, str]:
    """Make `<brains_dir>/<name>` the default brain. Returns (ok, reason); reason is "invalid" or "missing" on failure.

    Choosing `Brain Default` again still writes the file (rather than removing it): a removal would not reach the
    other synced machines as clearly as a new value does."""
    n = str(name or "")
    if not valid_folder(n):
        return False, "invalid"
    base = Path(brains_dir)
    if not (base / n).is_dir():
        return False, "missing"
    p = pointer_path(base)
    data = {"folder": n, "set_at": int(time.time()), "v": 1}
    tmp = p.with_name(p.name + ".tmp")   # ".tmp" is skipped by the backup, so a half-written file never syncs
    try:
        base.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(p))
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    with _lock:
        _cache.pop(str(p), None)
    return True, ""
