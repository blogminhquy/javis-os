"""brain_export.py - a whole brain as one .zip file, out and back in (2026-11-09).

Owner, redesigning the brain picker: "có thể xuất bộ não đấy ra thành file và tải lên chỗ khác". Each row of the picker
gets an Export button (GET /brains/export) and the panel gets "Upload a brain" (POST /brains/import).

What goes into the file is the brain's knowledge: notes, images, agents, skills, workflows, memory. What stays out is
what must not travel in a file someone may forward: the brain's own git folder, raw chat logs and run logs, learned
files carrying customer chat text, and the config files Javis writes with a hub token in them. The list follows the
backup's (git_brain._BACKUP_SKIP_SUBSTR), so the two never disagree about what is private, plus a few names that are
secrets anywhere (.env, private keys, .mcp.json).

An upload is a file from elsewhere, so it is treated as such:
- every name is checked (no absolute path, no "..", no symlink) and the private names above are dropped on the way in;
- size and file count are capped while extracting (the sizes a zip announces can lie);
- it always becomes a NEW brain folder, never written over an existing one, extracted into a work folder first and
  moved into place only once complete;
- whatever would run on its own is switched off: plugins (real Python), loops and pending reminders. The owner switches
  back on what they want, on this machine, knowingly.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

import brain_label
import git_brain

MAX_FILES = 20000                      # same caps as a folder download (/files/zip)
MAX_BYTES = 2 * 1024 * 1024 * 1024     # 2GB of raw data
MAX_UPLOAD = 1024 * 1024 * 1024        # 1GB compressed file
MANIFEST = "javis-brain.json"
IMPORT_PREFIX = ".javis-import-"

_SECRET_NAMES = {".env", ".mcp.json", ".mcp_hub.json", ".javis-learn.lock", ".ds_store"}
_SECRET_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
_SECRET_SUFFIXES = (".tmp", ".pem", ".key", ".p12", ".pfx")
_SKIP_DIRS = {".git", ".trash"}


class TooBig(Exception):
    """Over MAX_FILES or MAX_BYTES."""


class BadFile(Exception):
    """Not a brain file we can take (not a zip, empty, damaged)."""


def kept_out(rel: str) -> bool:
    """True for a path (relative to the brain root) that never goes into, or comes out of, a brain file."""
    r = str(rel or "").replace("\\", "/").strip("/")
    if not r:
        return True
    parts = r.split("/")
    if any(p in _SKIP_DIRS for p in parts):
        return True
    wrapped = "/" + r + "/"
    if any(s in wrapped for s in git_brain._BACKUP_SKIP_SUBSTR):
        return True
    if git_brain._learned_private(r):
        return True
    name = parts[-1].lower()
    if name in _SECRET_NAMES or name.startswith(_SECRET_PREFIXES) or name.endswith(_SECRET_SUFFIXES):
        return True
    dirs = parts[:-1]
    for i in range(len(dirs) - 3):   # agent run logs: memory/agents/<slug>/runs/
        if dirs[i] in ("memory", "Memory") and dirs[i + 1] == "agents" and dirs[i + 3] == "runs":
            return True
    return False


def _walk(root: Path):
    """(path, rel) of every file to export, symlinks skipped so the walk never leaves the brain."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        rel_dir = "" if base == root else base.relative_to(root).as_posix()
        keep = []
        for d in dirnames:
            if os.path.islink(os.path.join(dirpath, d)):
                continue
            if kept_out((rel_dir + "/" + d) if rel_dir else d):
                continue
            keep.append(d)
        dirnames[:] = keep
        for fn in filenames:
            p = base / fn
            rel = (rel_dir + "/" + fn) if rel_dir else fn
            if p.is_symlink() or kept_out(rel):
                continue
            yield p, rel


def scan(root) -> tuple:
    """(files, bytes) the export of this brain would hold. Raises TooBig past the caps."""
    root = Path(root)
    files = total = 0
    for p, _rel in _walk(root):
        try:
            total += p.stat().st_size
        except OSError:
            continue
        files += 1
        if files > MAX_FILES or total > MAX_BYTES:
            raise TooBig()
    return files, total


def export_zip(root, dst: str, app_version: str = "") -> tuple:
    """Write the brain at `root` into the zip `dst`, under one top folder named like the brain's folder, with a small
    manifest (label, folder, date) at the top so an import keeps the name. Returns (files, bytes)."""
    root = Path(root)
    top = root.name or "brain"
    files = total = 0
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(top + "/" + MANIFEST, json.dumps({
            "kind": "javis-brain", "label": brain_label.display(root), "folder": top,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "app_version": app_version,
        }, ensure_ascii=False, indent=2))
        for p, rel in _walk(root):
            try:
                size = p.stat().st_size
            except OSError:
                continue
            files += 1
            total += size
            if files > MAX_FILES or total > MAX_BYTES:
                raise TooBig()
            try:
                zf.write(p, top + "/" + rel)
            except (OSError, ValueError):
                continue
    return files, total


def safe_name(name: str) -> str:
    """A folder name for a brain (same rule as /brains/new)."""
    name = (name or "").strip().strip(".")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", name)
    return name[:60].strip()


def _clean_member(name: str) -> Optional[str]:
    """The member's path as a safe relative POSIX path, or None to skip it."""
    n = str(name or "").replace("\\", "/")
    if not n or n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _is_link(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _unique_folder(brains_dir: Path, base: str) -> Path:
    base = base or "Brain"
    p = brains_dir / base
    i = 2
    while p.exists():
        p = brains_dir / f"{base} ({i})"
        i += 1
    return p


def _unique_label(brains_dir: Path, label: str, root: Path) -> str:
    label = brain_label.clean(label)
    if not label:
        return ""
    want, i = label, 2
    while brain_label.taken_by(brains_dir, want, except_root=root):
        suffix = f" ({i})"
        want = label[:brain_label.MAX_LEN - len(suffix)].rstrip() + suffix
        i += 1
    return want


def _off_plugins(root: Path) -> int:
    import yaml
    n = 0
    for d in (root / "plugins", root / "Javis" / "plugins"):
        if not d.is_dir():
            continue
        for f in list(d.glob("*/plugin.yaml")) + list(d.glob("*/plugin.yml")):
            try:
                m = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                m = None
            if not isinstance(m, dict):
                # A manifest we cannot read cannot be switched off by editing it: take the plugin's code out instead.
                for entry in ("plugin.py", "__init__.py"):
                    e = f.parent / entry
                    if e.is_file():
                        e.rename(e.with_name(entry + ".off"))
                n += 1
                continue
            if m.get("enabled"):
                m["enabled"] = False
                f.write_text(yaml.safe_dump(m, allow_unicode=True, sort_keys=False), encoding="utf-8")
                n += 1
    return n


_ENABLED_LINE = re.compile(r"^(enabled\s*:\s*)(true|yes|on)\s*$", re.IGNORECASE | re.MULTILINE)


def _off_loops(root: Path) -> int:
    d = root / "Javis" / "loops"
    n = 0
    if not d.is_dir():
        return 0
    for f in d.glob("*.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        if end < 0:
            continue
        head, rest = text[:end], text[end:]
        new_head, k = _ENABLED_LINE.subn(r"\1false", head)
        if k:
            f.write_text(new_head + rest, encoding="utf-8")
            n += 1
    return n


def _off_reminders(root: Path) -> int:
    f = root / "Javis" / "reminders.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    rems = d.get("reminders") if isinstance(d, dict) else None
    if not isinstance(rems, list):
        return 0
    n = 0
    for r in rems:
        if isinstance(r, dict) and r.get("status") == "pending":
            r["status"] = "paused"
            n += 1
    if n:
        tmp = f.with_name(f.name + ".import")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, f)
    return n


def import_zip(fileobj, brains_dir, filename: str = "", label: str = "", work_dir=None) -> dict:
    """Unpack a brain file into a NEW folder of `brains_dir`. Returns {name, path, label, files, paused}.
    Raises BadFile or TooBig; nothing is left behind when it raises.

    It is extracted under `work_dir` first (the state folder: outside BRAINS_DIR, so a backup sync running meanwhile
    never copies a half-extracted brain) and moved into place once complete."""
    brains_dir = Path(brains_dir)
    work = Path(work_dir) if work_dir else brains_dir
    try:
        zf = zipfile.ZipFile(fileobj)
    except (zipfile.BadZipFile, OSError, ValueError):
        raise BadFile("not a zip")
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES + 1:
            raise TooBig()
        members = []
        for i in infos:
            rel = _clean_member(i.filename)
            if rel and not _is_link(i):
                members.append((i, rel))
        if not members:
            raise BadFile("empty")
        # One folder at the top (what Javis writes, and what zipping a folder by hand gives): strip it.
        tops = {rel.split("/", 1)[0] for _i, rel in members}
        prefix = ""
        if len(tops) == 1 and all("/" in rel for _i, rel in members):
            prefix = next(iter(tops)) + "/"
        manifest = {}
        for i, rel in members:
            if rel == prefix + MANIFEST:
                try:
                    manifest = json.loads(zf.read(i).decode("utf-8")) or {}
                except Exception:
                    manifest = {}
                break
        if not isinstance(manifest, dict):
            manifest = {}

        stem = Path(str(filename or "")).stem
        folder = safe_name(str(manifest.get("folder") or "")) or safe_name(prefix.rstrip("/")) or safe_name(stem) or "Brain"
        brains_dir.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        tmp = work / (IMPORT_PREFIX + uuid.uuid4().hex[:12])
        tmp.mkdir()
        try:
            tmp_res = tmp.resolve()
            files = total = 0
            for i, rel in members:
                inner = rel[len(prefix):] if prefix else rel
                if not inner or inner == MANIFEST or kept_out(inner):
                    continue
                dest = (tmp / inner).resolve()
                if tmp_res not in dest.parents:
                    continue
                files += 1
                if files > MAX_FILES:
                    raise TooBig()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(i) as src, open(dest, "wb") as out:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise TooBig()
                        out.write(chunk)
            if not files:
                raise BadFile("empty")
            paused = {"plugins": _off_plugins(tmp), "loops": _off_loops(tmp), "reminders": _off_reminders(tmp)}
            final = _unique_folder(brains_dir, folder)
            shutil.move(str(tmp), str(final))   # a rename on the same disk, a copy across disks
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    want = (label or "").strip() or str(manifest.get("label") or "") or brain_label.display(final)
    shown = brain_label.write(final, _unique_label(brains_dir, want, final) or final.name)
    return {"name": final.name, "path": str(final), "label": shown, "files": files, "paused": paused}


def sweep_leftovers(work_dir, older_than_s: int = 3600) -> None:
    """Remove import folders a crash left behind."""
    try:
        now = time.time()
        for p in Path(work_dir).iterdir():
            if p.name.startswith(IMPORT_PREFIX) and p.is_dir():
                try:
                    if now - p.stat().st_mtime > older_than_s:
                        shutil.rmtree(p, ignore_errors=True)
                except OSError:
                    pass
    except OSError:
        pass
