"""Pinned folders and folders open by default in the Vault tree (user request, 2026-11-11).

A user who moved from a local Javis to a VPS asked for two things in the Vault panel: pin a folder to the top, and have
a folder already unfolded when the tree loads ("I pin the wiki folder and keep it open"). On the local install they had
patched the dashboard by hand; on a VPS that is not an option, so it is a setting now.

Stored in settings.json under "vault_tree", one entry per brain:

    {"vault_tree": {"<brain root>": {"pinned": ["03 - Wiki"], "open": ["03 - Wiki", "projects/shop"]}}}

- Server side, like the brain order (brain_order.py), so the phone and the laptop show the same tree.
- Paths are relative to the BRAIN ROOT, POSIX style, never to the browse ceiling: the ceiling changes with how the
  server is reached (a whole drive on localhost, the brain on a public bind) while the brain root does not.
- A folder that no longer exists is left out of what is read, and stays in the store until the next save. A folder
  that is missing for a moment (a git sync in progress) therefore comes back on its own.
- A folder renamed or deleted through Javis (/files/rename, /files/delete) takes its entries along (`moved`): a pinned
  "Wiki" renamed "03 - Wiki" stays pinned, and so does every saved folder inside it.
"""
from __future__ import annotations

from pathlib import Path

SETTINGS_KEY = "vault_tree"
FIELDS = ("pinned", "open")
MAX_ITEMS = 50
MAX_PATH = 1024


def clean_paths(raw) -> list:
    """A list of distinct brain-relative folder paths: POSIX separators, no empty, "." or ".." segment."""
    out, seen = [], set()
    if not isinstance(raw, (list, tuple)):
        return out
    for x in raw:
        if not isinstance(x, str):
            continue
        path = x.strip().replace("\\", "/").strip("/")
        if not path or len(path) > MAX_PATH or "\0" in path:
            continue
        parts = path.split("/")
        if any(seg.strip() in ("", ".", "..") for seg in parts):
            continue
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= MAX_ITEMS:
            break
    return out


def clean(raw) -> dict:
    """{"pinned": [...], "open": [...]} from anything a client or a hand-edited settings.json may hold."""
    raw = raw if isinstance(raw, dict) else {}
    return {field: clean_paths(raw.get(field)) for field in FIELDS}


def brain_key(brain_root) -> str:
    """The key of a brain in the store: its resolved root, so "brain" and the full path of the default brain agree."""
    try:
        return str(Path(brain_root).resolve())
    except OSError:
        return str(brain_root)


def read(settings, brain_root) -> dict:
    """The saved preferences of one brain, without the folders that are not there (any more)."""
    store = (settings or {}).get(SETTINGS_KEY)
    prefs = clean((store if isinstance(store, dict) else {}).get(brain_key(brain_root)))
    root = Path(brain_key(brain_root))
    return {field: [p for p in prefs[field] if _is_dir_inside(root, p)] for field in FIELDS}


def patch(brain_root, raw) -> dict:
    """The settings patch (for config.update_settings) that saves `raw` as the preferences of this brain."""
    return {SETTINGS_KEY: {brain_key(brain_root): clean(raw)}}


def moved(settings, brain_root, old, new=None):
    """The settings patch after the folder `old` became `new` (a rename) or went away (`new` is None), or None when
    no saved entry is touched. Both are absolute paths; entries of folders inside `old` follow it."""
    root = Path(brain_key(brain_root))
    old_rel = _rel_inside(root, old)
    if not old_rel:
        return None
    new_rel = _rel_inside(root, new) if new is not None else None
    store = (settings or {}).get(SETTINGS_KEY)
    prefs = clean((store if isinstance(store, dict) else {}).get(brain_key(brain_root)))
    changed, out = False, {}
    for field in FIELDS:
        rows = []
        for path in prefs[field]:
            if path == old_rel or path.startswith(old_rel + "/"):
                changed = True
                if new_rel:
                    rows.append(new_rel + path[len(old_rel):])
            else:
                rows.append(path)
        out[field] = rows
    return patch(brain_root, out) if changed else None


def _rel_inside(root: Path, target) -> str:
    """`target` as a POSIX path relative to `root`, "" when it is the root itself or outside it."""
    try:
        rel = Path(target).relative_to(root)
    except (ValueError, TypeError):
        return ""
    return "" if str(rel) == "." else str(rel).replace("\\", "/")


def _is_dir_inside(root: Path, rel: str) -> bool:
    try:
        target = (root / rel).resolve()
        return root in target.parents and target.is_dir()
    except OSError:
        return False
