"""Keep every brain's operations index (Javis/index.md) current without rebuilding it blindly (0.389.0).

Before this, the scheduler rebuilt the index every 30 s, but only for the brains the loop scheduler knew about: the
default brain plus brains that once had a loop or a reminder. Any other brain kept the index written the day it was
created, so it said "0 agents" while the brain grew 18 of them, and an AI reading it to avoid duplicates was misled.

Rebuilding every brain on every tick would fix that and cost a full parse of every agent, workflow, skill and plugin
manifest, again and again, growing with the number of brains. So instead:

- Each sweep takes a cheap SIGNATURE of what the index is built from: stat calls only, no file is read or parsed.
  Adding, removing or renaming a file moves its folder's mtime; editing one moves its own mtime and size.
- Only a brain whose signature moved is rebuilt, and a sweep rebuilds at most `max_rebuilds` brains, the ones built
  longest ago first, so a burst of changes across many brains spreads over a few ticks instead of one long one.
- Inputs the signature cannot see (a plugin tool shown only when a per-brain setting is on, say) are covered by
  `refresh_s`: a brain is rebuilt anyway once that much time has passed. The write itself stays change-gated in
  `rebuild_javis_index`, so a refresh that finds nothing new never touches the disk.

The module knows nothing about main.py: the caller passes how to sign one brain, how to sign what all brains share,
and how to rebuild one brain. That keeps it testable with plain folders.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

MAX_REBUILDS_PER_SWEEP = 4
REFRESH_S = 30 * 60

# Where a skill can live, same order as skill_router._READ_BASES. A disabled skill sits in <base>/.disabled/<slug>.
SKILL_BASES = ("skills", ".claude/skills", ".agents")
# Files that make a folder a plugin, same set plugins_host signs.
PLUGIN_FILES = ("plugin.yaml", "plugin.yml", "plugin.py", "__init__.py")


def _stat(parts: list, path, keep_missing: bool = True) -> None:
    try:
        st = os.stat(path)
    except OSError:
        if keep_missing:
            parts.append((str(path), None))
        return
    parts.append((str(path), st.st_mtime_ns, st.st_size))


def _md_files(parts: list, folder) -> None:
    """The folder itself (add, remove, rename) plus every .md directly inside it (edits)."""
    if not folder:
        return
    _stat(parts, folder)
    rows = []
    try:
        with os.scandir(folder) as it:
            for e in it:
                if e.name.endswith(".md") and e.is_file():
                    st = e.stat()
                    rows.append((e.path, st.st_mtime_ns, st.st_size))
    except OSError:
        return
    parts.extend(sorted(rows))


def _child_manifests(parts: list, folder, names: Tuple[str, ...]) -> None:
    """The folder itself plus the manifest of each subfolder (skills/<slug>/SKILL.md, plugins/<slug>/plugin.yaml)."""
    if not folder:
        return
    _stat(parts, folder)
    try:
        with os.scandir(folder) as it:
            subdirs = sorted(e.path for e in it if e.is_dir())
    except OSError:
        return
    for sd in subdirs:
        for n in names:
            _stat(parts, os.path.join(sd, n), keep_missing=False)


def brain_signature(root, agents_dir, workflows_dir, plugins_dir: Optional[Path] = None) -> str:
    """Signature of one brain's index inputs. Equal signatures mean nothing the index lists has changed on disk."""
    root = Path(root)
    parts: list = []
    _md_files(parts, agents_dir)
    _md_files(parts, workflows_dir)
    for base in SKILL_BASES:
        _child_manifests(parts, root / base, ("SKILL.md",))
        _child_manifests(parts, root / base / ".disabled", ("SKILL.md",))
    _md_files(parts, root / "Javis" / "loops")
    _stat(parts, root / "Javis" / "loop-state.json")   # a loop that paused itself shows in the index
    _child_manifests(parts, plugins_dir, PLUGIN_FILES)
    _stat(parts, root / "Javis" / "index.md")          # deleted or edited by hand: write it again
    return hashlib.blake2b(repr(parts).encode("utf-8"), digest_size=16).hexdigest()


class IndexWatcher:
    """Remembers, per brain, the signature at its last rebuild and when that was."""

    def __init__(self, signature_of: Callable[[str], str], rebuild: Callable[[str], dict],
                 shared_signature: Callable[[], object] = lambda: None,
                 max_rebuilds: int = MAX_REBUILDS_PER_SWEEP, refresh_s: float = REFRESH_S,
                 clock: Callable[[], float] = time.monotonic):
        self._signature_of = signature_of
        self._rebuild = rebuild
        self._shared = shared_signature
        self._max = max(1, int(max_rebuilds))
        self._refresh_s = refresh_s
        self._clock = clock
        self._seen: Dict[str, Tuple[object, float]] = {}
        self._lock = threading.Lock()   # sweeps run in a worker thread; never let two overlap

    def _sign(self, brain: str, shared) -> Optional[tuple]:
        try:
            return (shared, self._signature_of(brain))
        except Exception:
            return None

    def sweep(self, brains: Iterable[str]) -> List[str]:
        """Rebuild the brains whose index inputs changed (or whose refresh is due). Returns the ones rebuilt."""
        if not self._lock.acquire(blocking=False):
            return []
        try:
            try:
                shared = self._shared()
            except Exception:
                shared = None
            now = self._clock()
            live, due = set(), []
            for b in brains:
                if b in live:
                    continue
                live.add(b)
                sig = self._sign(b, shared)
                if sig is None:
                    continue
                last = self._seen.get(b)
                if last is None or last[0] != sig or now - last[1] >= self._refresh_s:
                    due.append((last[1] if last else float("-inf"), b))
            for gone in set(self._seen) - live:
                del self._seen[gone]
            due.sort(key=lambda x: x[0])
            rebuilt = []
            for _, b in due[:self._max]:
                try:
                    res = self._rebuild(b)
                except Exception:
                    res = None
                if not (isinstance(res, dict) and res.get("ok")):
                    continue                      # not remembered: the next sweep tries again
                sig = self._sign(b, shared)       # signed AFTER the rebuild, which may have rewritten index.md
                if sig is not None:
                    self._seen[b] = (sig, now)
                rebuilt.append(b)
            return rebuilt
        finally:
            self._lock.release()
