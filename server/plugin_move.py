"""Owner-requested availability changes without rewriting plugin code or permissions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading

import plugin_authoring
import plugin_scope
import plugins_host

_LOCK = threading.Lock()


class MoveError(ValueError):
    pass


def _plain_path(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise MoveError("symlink")


def fingerprint(folder: Path) -> str:
    _plain_path(folder)
    if not folder.is_dir():
        raise MoveError("source_missing")
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        info = path.lstat()
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise MoveError("symlink")
        if "__pycache__" in path.relative_to(folder).parts:
            continue
        digest.update(json.dumps([path.relative_to(folder).as_posix(), info.st_mode]).encode())
        if path.is_file():
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _source(slug: str, scope: str, root: Path) -> Path:
    if not plugins_host.valid_slug(slug):
        raise MoveError("invalid_slug")
    if scope not in ("brain", "global"):
        raise MoveError("invalid_scope")
    if slug in plugins_host._slug_bundled() or slug in plugin_authoring._pack_slugs():
        raise MoveError("protected_plugin")
    base = (plugins_host.global_plugins_dir() if scope == "global"
            else plugins_host.vault_plugins_dir(str(root)))
    folder = base / slug
    _plain_path(folder)
    manifest, error = plugins_host._read_manifest(folder)
    if error or not any((folder / name).is_file() for name in plugins_host._ENTRY_FILES):
        raise MoveError("source_missing")
    if manifest.get("slug", slug) != slug:
        raise MoveError("invalid_slug")
    return folder


def _revision(folder: Path, slug: str, content: str = "") -> str:
    return hashlib.sha256(((content or fingerprint(folder)) + json.dumps(plugin_scope.selection(slug))).encode()).hexdigest()


def inspect(slug: str, scope: str, root: Path) -> dict:
    folder = _source(slug, scope, root)
    return {"ok": True, "digest": _revision(folder, slug), "scope": scope,
            "selected_brains": plugin_scope.selection(slug) if scope == "global" else [str(root)],
            "enabled": bool(plugins_host._read_manifest(folder)[0].get("enabled"))}


def _write(path: Path, data: bytes):
    _plain_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".plugin-scope-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def configure(slug: str, source_scope: str, source_root: Path,
              targets: list[Path] | None, brain_roots: list[Path], expected_digest: str) -> dict:
    """None = all brains including future ones; otherwise an explicit nonempty selection.

    Selected plugins share one code folder in global storage. Availability is checked during
    discovery and again before a cached tool handler runs. Plugin data_dir stays unchanged.
    """
    with _LOCK:
        source = _source(slug, source_scope, source_root)
        if targets is not None and (not targets or any(p not in brain_roots for p in targets)):
            raise MoveError("unknown_brain")
        before = fingerprint(source)
        if not expected_digest or _revision(source, slug, before) != expected_digest:
            raise MoveError("source_changed")
        dest = plugins_host.global_plugins_dir() / slug
        _plain_path(dest)
        candidates = [dest]
        for root in brain_roots:
            candidates.extend([root / "plugins" / slug, root / "Javis" / "plugins" / slug])
        for candidate in candidates:
            _plain_path(candidate)
            if candidate != source and candidate.exists():
                raise MoveError("destination_conflict")
        policy_path = plugin_scope.PATH
        _plain_path(policy_path)
        policy_before = policy_path.read_bytes() if policy_path.exists() else None
        policy = json.loads(policy_before) if policy_before is not None else {}
        if not isinstance(policy, dict) or "*" in policy:
            raise MoveError("policy_invalid")
        if targets is None:
            policy.pop(slug, None)
        else:
            policy[slug] = sorted({str(p.resolve()) for p in targets})
        ledger_path = plugin_authoring._LEDGER
        _plain_path(ledger_path)
        ledger_before = ledger_path.read_bytes() if ledger_path.exists() else None
        ledger = json.loads(ledger_before) if ledger_before is not None else {}
        if not isinstance(ledger, dict):
            raise MoveError("ledger_invalid")
        old_key = plugin_authoring._ledger_key(source_scope, source.parent, slug)
        new_key = plugin_authoring._ledger_key("global", dest.parent, slug)
        migrated = source != dest and old_key in ledger
        if migrated:
            ledger[new_key] = dict(ledger.pop(old_key), dir=str(dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source != dest and source.stat().st_dev != dest.parent.stat().st_dev:
            raise MoveError("different_filesystem")
        moved = policy_written = reserved = False
        try:
            # Apply restrictions before publishing a formerly brain-private folder.
            _write(policy_path, json.dumps(policy, ensure_ascii=False, indent=1).encode())
            policy_written = True
            plugin_scope.invalidate()
            if source != dest:
                # Reserve an absent destination; rename only replaces our empty
                # directory and cannot overwrite an existing plugin in a race.
                try:
                    dest.mkdir(mode=0o700)
                except FileExistsError as e:
                    raise MoveError("destination_conflict") from e
                reserved = True
                os.rename(source, dest)
                moved = True
            if fingerprint(dest) != before:
                raise MoveError("source_changed")
            if migrated:
                _write(ledger_path, json.dumps(ledger, ensure_ascii=False, indent=1).encode())
        except Exception:
            if moved:
                os.rename(dest, source)
            elif reserved:
                dest.rmdir()
            if policy_written:
                if policy_before is None:
                    policy_path.unlink()
                else:
                    _write(policy_path, policy_before)
            plugin_scope.invalidate()
            plugins_host.invalidate()
            raise
        plugins_host.unload(slug)
        plugins_host.invalidate()
        return {"ok": True, "slug": slug, "scope": "global" if targets is None else "selected",
                "brains": None if targets is None else policy[slug],
                "enabled": bool(plugins_host._read_manifest(dest)[0].get("enabled")),
                "digest": _revision(dest, slug)}
