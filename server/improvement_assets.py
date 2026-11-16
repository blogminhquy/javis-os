"""Read-only canonical snapshots; editable ownership is never inferred from model text."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Callable

import fastyaml
import system_sync
from improvement_blobs import AssetUnavailable, MAX_ASSET_BYTES, check_ancestry
from improvement_store import SourceSnapshot

_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
_DEVICES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class SourceError(ValueError):
    """A source cannot be captured under the canonical ownership contract."""


def _stamp(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _pack_owned(root: Path, kind: str, slug: str, path: Path, state: Path) -> bool:
    if not state.exists():
        return False
    check_ancestry(state)
    for registry in state.glob("*.json"):
        check_ancestry(registry)
        if registry.stat().st_size > 2 * MAX_ASSET_BYTES:
            raise SourceError("ownership_unavailable")
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("items", {}), dict):
                raise SourceError("ownership_unavailable")
            # One pack can be installed in several brains (16/11/2026): `brains` maps each root to its items.
            # The older one-brain shape (`brain` + `items`) is still read.
            per_brain = data.get("brains")
            if per_brain is None:
                per_brain = {str(data.get("brain") or ""): {"items": data.get("items", {})}}
            if not isinstance(per_brain, dict):
                raise SourceError("ownership_unavailable")
            entry = None
            for brain, value in per_brain.items():
                if not brain or not isinstance(value, dict) or not isinstance(value.get("items", {}), dict):
                    if brain:
                        raise SourceError("ownership_unavailable")
                    continue
                if Path(str(brain)).resolve() == root:
                    entry = value
                    break
            if entry is None:
                continue
            item = entry.get("items", {}).get(f"{kind}s/{slug}")
            if item is not None:
                if not isinstance(item, dict):
                    raise SourceError("ownership_unavailable")
                installed = Path(str(item.get("duong") or "")).resolve()
                if installed == (path.parent if kind == "skill" else path):
                    return True
                raise SourceError("ownership_unavailable")
        except (OSError, ValueError, TypeError) as error:
            raise SourceError("ownership_unavailable") from error
    return False


def capture_source(root: Path, kind: str, slug: str, *, pack_state_dir: Path | None = None,
                   agent_identity: Callable[[], str] | None = None) -> tuple[SourceSnapshot, bytes]:
    if kind not in ("skill", "agent") or not isinstance(slug, str) or not _SLUG.fullmatch(slug) or slug in _DEVICES:
        raise SourceError("invalid_target")
    try:
        root = Path(root).absolute()
        check_ancestry(root)
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise SourceError("brain_unavailable")
        if kind == "skill":
            if (root / "skills" / ".disabled" / slug).exists():
                raise SourceError("source_disabled")
            if system_sync.is_system_skill(slug):
                raise SourceError("system_source_protected")
            relative = f"skills/{slug}/SKILL.md"
        else:
            relative = f"agents/{slug}.md"
        path = root / relative
        check_ancestry(path)
        if not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
            raise SourceError("canonical_source_unavailable")
        if pack_state_dir is None:
            from config import STATE_DIR
            pack_state_dir = STATE_DIR / "packs-state"
        if _pack_owned(root, kind, slug, path, Path(pack_state_dir)):
            raise SourceError("pack_source_protected")
        before = path.stat()
        if before.st_size > MAX_ASSET_BYTES:
            raise SourceError("source_too_large")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            content = handle.read(MAX_ASSET_BYTES + 1)
            finished = os.fstat(handle.fileno())
        check_ancestry(path)
        after = path.stat()
        # Windows path stat exposes creation time as ctime, while fstat may expose
        # metadata-change time. Compare ctime within each source, not across APIs.
        stable = (_stamp(before) == _stamp(opened) == _stamp(finished) == _stamp(after)
                  and before.st_ctime_ns == after.st_ctime_ns
                  and opened.st_ctime_ns == finished.st_ctime_ns)
        if len(content) > MAX_ASSET_BYTES or not stable:
            raise SourceError("source_changed_during_capture")
        text = content.decode("utf-8", errors="strict")
        parts = fastyaml.split_frontmatter(text)
        if parts is not None:
            if len(parts[0].encode("utf-8")) > 16384:
                raise SourceError("source_frontmatter_too_large")
            try:
                metadata = fastyaml.safe_load(parts[0])
            except Exception as error:
                raise SourceError("invalid_source_frontmatter") from error
            if metadata is not None and not isinstance(metadata, dict):
                raise SourceError("invalid_source_frontmatter")
            lock = (metadata or {}).get("learn_lock", False)
            if lock not in (False, None, "", 0, "false", "off", "no"):
                raise SourceError("source_learning_locked")
        digest = hashlib.sha256(content).hexdigest()
        agent_key = str(agent_identity() or "") if kind == "agent" and agent_identity else ""
        if kind == "agent" and not agent_key:
            raise SourceError("host_agent_identity_required")
        identity = hashlib.sha256(f"{agent_key}:{before.st_dev}:{before.st_ino}".encode("utf-8")).hexdigest()
        return SourceSnapshot(kind, relative, digest, digest, True, "user_protected", identity, agent_key), content
    except SourceError:
        raise
    except (AssetUnavailable, OSError, UnicodeError, RuntimeError) as error:
        raise SourceError("canonical_source_unavailable") from error
