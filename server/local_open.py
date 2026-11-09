"""Open a file that lives OUTSIDE the brain with the owner's own app, on the machine running Javis.

Why this exists: Javis often builds things outside the brain (a teaching deck in ~/Documents, a
report in ~/Downloads), then names the file in chat. The chat only turns brain paths into links,
and with login on the file server is locked to the brain, so the owner saw the file name as dead
text and had to dig it out in Finder (owner request, 2026-11-09).

What it does NOT do is serve the file over HTTP. It asks the operating system to open it, the same
as a double click in Finder, so it only makes sense when the browser is on the same machine. The
endpoint in main.py checks that (no tunnel, no proxy) before it calls in here.

The rules that keep a click from becoming "run anything":
  - the path must be absolute, exist, and sit inside the owner's home folder (or the brain);
  - only document-like types are OPENED (OPEN_EXTS). Anything else, and every app bundle,
    installer or script, is only REVEALED in Finder / Explorer, which runs nothing;
  - no shell: the path goes to the launcher as one argument, and it always starts with "/" (or a
    drive letter), so it can never be read as a flag.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

# Types a click OPENS with the default app. Kept to documents and media on purpose: adding a type
# here means a link in chat can launch whatever app owns it.
OPEN_EXTS = frozenset({
    ".html", ".htm", ".md", ".markdown", ".txt", ".rtf", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    ".pages", ".numbers", ".key", ".epub",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic", ".bmp", ".tif", ".tiff",
    ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
})

# Folders that are really programs or installers on macOS: "opening" one runs it. Only reveal.
BUNDLE_EXTS = frozenset({
    ".app", ".bundle", ".framework", ".pkg", ".mpkg", ".workflow", ".action", ".prefpane", ".kext",
    ".plugin", ".appex", ".saver", ".qlgenerator", ".mdimporter", ".xpc", ".terminal",
})


class LocalOpenError(ValueError):
    """`code` is one of: not_absolute, missing, outside. main.py turns it into a message."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean(raw: str) -> str:
    p = str(raw or "").strip().strip("`'\"<>")
    if p.lower().startswith("file:"):
        p = urllib.parse.unquote(p[5:])
        if p.startswith("//"):                       # file://host/path -> /path
            cut = p.find("/", 2)
            p = p[cut:] if cut >= 0 else ""
        if len(p) > 2 and p[0] == "/" and p[2] == ":":   # /C:/x -> C:/x
            p = p[1:]
    return os.path.expanduser(p)


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def resolve_target(raw: str, roots=None) -> Path:
    """The real file or folder `raw` points at, or LocalOpenError.

    `roots` are the folders a click may reach; default is the owner's home folder. Symlinks are
    resolved first, so a link inside home that points at /etc is refused like /etc itself.
    """
    p = _clean(raw)
    if not p or not os.path.isabs(p):
        raise LocalOpenError("not_absolute")
    target = Path(p).resolve()
    allowed = [Path(r).resolve() for r in (roots or [Path.home()]) if r]
    if not any(_inside(target, r) for r in allowed):
        raise LocalOpenError("outside")
    if not target.exists():
        raise LocalOpenError("missing")
    return target


def plan(target: Path) -> str:
    """'open' (default app) or 'reveal' (show it selected in Finder / Explorer)."""
    ext = target.suffix.lower()
    if target.is_dir():
        return "reveal" if ext in BUNDLE_EXTS else "open"
    return "open" if ext in OPEN_EXTS else "reveal"


def launch(action: str, target: Path) -> None:
    """Hand the path to the OS. Returns at once; the app opens on its own."""
    s = str(target)
    if sys.platform == "darwin":
        cmd = ["open", "-R", s] if action == "reveal" else ["open", s]
    elif sys.platform.startswith("win"):
        if action == "open":
            os.startfile(s)  # noqa: S606 - type already limited by plan()
            return
        cmd = ["explorer", "/select," + s]
    else:
        cmd = ["xdg-open", s if action == "open" else str(target.parent)]
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True)
