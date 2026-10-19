"""The display name of a brain, kept apart from its folder (0.219.0).

Why this exists. A brain is addressed everywhere by its FOLDER: "brain" means `<BRAINS_DIR>/Brain Default`, any other
brain is `path:<absolute folder>`. That address is stored in the browser, in chat bots, reminders, loops, Kanban tasks,
sessions, the git backup (tombstones, mirror paths) and in links Javis writes into notes and chats
(`/brains/<folder>/wiki/x.md`). Renaming the folder would quietly cut all of them, which is why the dashboard never
offered it, and why Brain Default could not be renamed at all (owner's chat, 2026-10-19: "sao lại fix cứng thế").

So a rename only changes a LABEL. The folder, and every address and link built on it, stays exactly as it was. The
label lives inside the brain (`Javis/brain.json`), so the git backup carries it to every machine that shares the brain,
and a brain copied to another install keeps its name.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

MAX_LEN = 60
FILE = Path("Javis") / "brain.json"


def _file(root) -> Path:
    return Path(root) / FILE


def clean(label) -> str:
    """One line, no control characters, at most MAX_LEN characters."""
    s = " ".join(str(label or "").split())
    s = "".join(ch for ch in s if ch.isprintable())
    return s[:MAX_LEN].strip()


def read(root) -> str:
    """The label set for this brain, or "" when none is set (the folder name is then the name)."""
    try:
        d = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return clean(d.get("name")) if isinstance(d, dict) else ""


def display(root) -> str:
    """What to call the brain: its label, or its folder name."""
    return read(root) or Path(str(root)).name


def write(root, label) -> str:
    """Set the label (an empty label, or one equal to the folder name, clears it). Returns the name now shown.
    Other keys already in the file are kept, so a later setting stored there is not lost by a rename."""
    p = _file(root)
    name = clean(label)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except (OSError, ValueError):
        d = {}
    if not name or name == Path(str(root)).name:
        d.pop("name", None)
    else:
        d["name"] = name
    if d:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    elif p.exists():
        p.unlink()
    return display(root)


def taken_by(brains_dir, label, except_root=None) -> Optional[str]:
    """The folder of another brain already shown under this name (case-insensitive), or None. Two brains with the same
    name in the picker would be told apart only by guessing."""
    want = clean(label).casefold()
    if not want:
        return None
    skip = Path(str(except_root)).resolve() if except_root else None
    try:
        for p in Path(brains_dir).iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            if skip is not None and p.resolve() == skip:
                continue
            if display(p).casefold() == want:
                return p.name
    except OSError:
        pass
    return None
