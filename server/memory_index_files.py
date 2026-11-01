"""Which files in a brain's memory/ folder are memory indexes (0.432.1, #934).

MEMORY.md is the core index, preloaded before every chat turn, so a brain with many memories can split it: the core lines
stay in MEMORY.md and the rest go to secondary index files in memory/. Before this module Javis only knew MEMORY.md, so
the learn loop and the curator saw every memory listed elsewhere as "missing" and appended a duplicate line to MEMORY.md,
pushing it back over JAVIS_MEMORY_INDEX_MAX.

A secondary index is a Markdown file directly in memory/ that either declares `type: index` in its frontmatter or is named
`muc-luc-*.md` (the convention a real brain already used). Lines in it follow MEMORY.md's format:
`- [Title](facts/<slug>.md) - hook`. Only MEMORY.md is preloaded; the others are read when needed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

CORE = "MEMORY.md"
_TYPE_INDEX = re.compile(r"^type:\s*['\"]?index['\"]?\s*$", re.M | re.I)
_NAME_PREFIXES = ("muc-luc",)


def _declares_index(path: Path) -> bool:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(800)
    except OSError:
        return False
    if not head.startswith("---"):
        return False
    end = head.find("\n---", 3)
    return end > 0 and bool(_TYPE_INDEX.search(head[3:end]))


def secondary_indexes(mem_dir) -> List[Path]:
    """Secondary index files, sorted by name. Never raises."""
    d = Path(mem_dir)
    out: List[Path] = []
    try:
        files = sorted(d.glob("*.md")) if d.is_dir() else []
    except OSError:
        return out
    for f in files:
        if f.name == CORE:
            continue
        if f.stem.casefold().startswith(_NAME_PREFIXES) or _declares_index(f):
            out.append(f)
    return out


def index_files(mem_dir) -> List[Path]:
    """MEMORY.md first (when it exists), then the secondary indexes."""
    core = Path(mem_dir) / CORE
    return ([core] if core.is_file() else []) + secondary_indexes(mem_dir)


def all_index_text(mem_dir) -> str:
    """Every index file's text joined, MEMORY.md first. Used to ask "is this memory listed anywhere?"."""
    parts = []
    for f in index_files(mem_dir):
        try:
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)


def listed(mem_dir, slug: str, text: str | None = None) -> bool:
    """True when facts/<slug>.md is listed in MEMORY.md or any secondary index."""
    return f"facts/{slug}.md" in (all_index_text(mem_dir) if text is None else text)
