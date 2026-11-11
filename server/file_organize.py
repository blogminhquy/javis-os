"""file_organize.py - tidy a folder into a clear structure, always as a plan the owner reviews first, always undoable.

Flow:
  1. `build_plan(source, mode, ...)` walks the folder (same skips as the scanner) and proposes a new place for each
     file: by type (Ảnh, Video, Tài liệu/PDF...), by type and year or month, or by date. Photos use the date they
     were taken (EXIF), other files their modified date. Javis can instead hand over its own plan by topic through
     `propose_plan()` (the javis_files tool), for example invoices, contracts or one folder per project.
  2. The plan is saved (STATE_DIR/file_scan/organize_plan.json) and shown on the Disk cleanup page grouped by
     destination folder. Nothing has moved yet.
  3. `apply_plan()` moves the chosen files, journalled in file_scan's `moves` table as an "organize" batch, so
     `file_scan.restore(batch)` puts every file back. An organize batch can never be purged.

Safety rules: a project folder (one holding .git, package.json, a .sln...) is left whole, because moving its files
breaks it; hidden and system files stay; an existing file is never overwritten (the moved one gets " (1)", " (2)"...);
a file that changed since the plan, or whose source vanished, is skipped; every destination must stay inside the
target folder. Empty folders left behind are removed, and recreated on undo.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import file_scan as fs

MODES = ("type", "type_year", "type_month", "date")
MAX_ITEMS = 50000
# Folder names are the owner's content, so they are Vietnamese by default and can be renamed per plan.
DEFAULT_NAMES = {"image": "Ảnh", "video": "Video", "audio": "Âm thanh", "document": "Tài liệu", "archive": "File nén",
                 "installer": "Phần mềm", "code": "Mã nguồn", "other": "Khác"}
DOC_SUB = {"pdf": "PDF", "doc": "Word", "docx": "Word", "odt": "Word", "rtf": "Word", "pages": "Word",
           "xls": "Excel", "xlsx": "Excel", "xlsm": "Excel", "csv": "Excel", "ods": "Excel", "numbers": "Excel",
           "ppt": "PowerPoint", "pptx": "PowerPoint", "odp": "PowerPoint", "key": "PowerPoint",
           "txt": "Văn bản", "md": "Văn bản", "epub": "Sách"}
PROJECT_MARKERS = {".git", ".hg", ".svn", "package.json", "pyproject.toml", "setup.py", "requirements.txt", "go.mod",
                   "cargo.toml", "pom.xml", "build.gradle", "composer.json", "gemfile", ".project", "makefile",
                   "cmakelists.txt", "angular.json", "next.config.js", "vite.config.js", "vite.config.ts"}
PROJECT_EXTS = (".sln", ".csproj", ".vcxproj", ".xcodeproj", ".uproject", ".prproj", ".aep", ".psdproj")
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "icon\r", "autorun.inf"}
_BAD_CHARS = '<>:"|?*\x00'


class OrganizeError(Exception):
    pass


def _plan_path() -> Path:
    return fs._state_dir() / "organize_plan.json"


def safe_part(name: str) -> str:
    """One folder name a user or Javis typed, made safe on Windows, macOS and Linux."""
    s = "".join("_" if (c in _BAD_CHARS or ord(c) < 32) else c for c in str(name or "")).strip().strip(".")
    return s[:80] or "_"


def safe_rel(rel: str) -> str:
    parts = [p for p in str(rel or "").replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return os.path.join(*[safe_part(p) for p in parts]) if parts else ""


def file_date(path: str, ext: str, mtime: float) -> Tuple[int, int]:
    """(year, month) a photo was taken, else when the file was last modified."""
    if ext in fs.IMAGE_EXTS and fs.pillow_ready():
        try:
            from PIL import Image
            with Image.open(path) as im:
                exif = im.getexif()
                raw = None
                try:
                    raw = exif.get_ifd(0x8769).get(36867)  # DateTimeOriginal
                except Exception:
                    pass
                raw = raw or exif.get(306)  # DateTime
                if raw:
                    y, m = int(str(raw)[0:4]), int(str(raw)[5:7])
                    if 1970 <= y <= 2100 and 1 <= m <= 12:
                        return y, m
        except Exception:
            pass
    t = time.localtime(mtime)
    return t.tm_year, t.tm_mon


def dest_folder(cat: str, ext: str, year: int, month: int, mode: str, names: Optional[Dict[str, str]] = None,
                doc_sub: bool = True) -> str:
    names = {**DEFAULT_NAMES, **{k: safe_part(v) for k, v in (names or {}).items() if v}}
    parts = [names.get(cat, names["other"])]
    if doc_sub and cat == "document" and ext in DOC_SUB:
        parts.append(DOC_SUB[ext])
    ym = f"{year}-{month:02d}"
    if mode == "type_year":
        parts.append(str(year))
    elif mode == "type_month":
        parts += [str(year), ym]
    elif mode == "date":
        parts = [str(year), ym]
    return os.path.join(*parts)


class _ProjectDirs:
    """Answers "is this folder (or one above it, up to the source) a project?" with one listing per folder."""

    def __init__(self, stop: str):
        self.stop = os.path.abspath(stop)
        self.cache: Dict[str, bool] = {}

    def _is_project(self, d: str) -> bool:
        if d not in self.cache:
            hit = False
            try:
                with os.scandir(d) as it:
                    for e in it:
                        n = e.name.lower()
                        if n in PROJECT_MARKERS or n.endswith(PROJECT_EXTS):
                            hit = True
                            break
            except OSError:
                pass
            self.cache[d] = hit
        return self.cache[d]

    def inside_project(self, folder: str) -> Optional[str]:
        d = os.path.abspath(folder)
        while True:
            if self._is_project(d):
                return d
            if d == self.stop or len(d) <= len(self.stop):
                return None
            d = os.path.dirname(d)


def _walk_files(source: str, scope: str):
    """(path, size, mtime, offline) under source. scope 'top' = only files sitting directly in source."""
    if scope == "top":
        try:
            with os.scandir(source) as it:
                for e in it:
                    try:
                        if e.is_file(follow_symlinks=False):
                            st = e.stat(follow_symlinks=False)
                            attrs = getattr(st, "st_file_attributes", 0) or 0
                            yield e.path, st.st_size, st.st_mtime, bool(attrs & fs._OFFLINE_ATTRS)
                    except OSError:
                        continue
        except OSError:
            return
        return
    import threading
    counters = {"dirs": 0, "files": 0, "bytes": 0, "errors": 0, "skipped": 0}
    yield from fs._walk(source, (), threading.Event(), lambda _p: None, counters)


def build_plan(source: str, mode: str = "type", target: str = "", scope: str = "all",
               names: Optional[Dict[str, str]] = None, doc_sub: bool = True) -> dict:
    """Propose a new place for every file under `source`, inside `target` (default: source itself). Saves and returns
    the plan; moves nothing."""
    if mode not in MODES:
        raise OrganizeError("bad_mode")
    source = fs.normalize_root(source)
    target = fs.normalize_root(target) if str(target or "").strip() else source
    if not os.path.isdir(source):
        raise OrganizeError("no_source")
    if not os.path.isdir(target):
        raise OrganizeError("no_target")
    projects = _ProjectDirs(source)
    items, skipped = [], {"project": 0, "in_place": 0, "hidden": 0, "offline": 0}
    project_dirs: set = set()
    truncated = False
    for path, size, mtime, offline in _walk_files(source, scope):
        name = os.path.basename(path)
        if name.startswith(".") or name.lower() in SKIP_NAMES:
            skipped["hidden"] += 1
            continue
        if offline:
            skipped["offline"] += 1
            continue
        proj = projects.inside_project(os.path.dirname(path))
        if proj:
            skipped["project"] += 1
            project_dirs.add(proj)
            continue
        ext = os.path.splitext(name)[1].lstrip(".").lower()
        cat = fs.category(ext)
        year, month = file_date(path, ext, mtime)
        folder = dest_folder(cat, ext, year, month, mode, names, doc_sub)
        dst = os.path.join(target, folder, name)
        if os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(path)):
            skipped["in_place"] += 1
            continue
        items.append({"src": path, "dst": dst, "folder": folder, "size": size, "mtime": mtime, "cat": cat})
        if len(items) >= MAX_ITEMS:
            truncated = True
            break
    _number_clashes(items)
    plan = {"id": time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex(), "created": time.time(), "by": "rules",
            "source": source, "target": target, "mode": mode, "scope": scope, "items": items, "skipped": skipped,
            "projects": sorted(project_dirs)[:50], "truncated": truncated, "note": ""}
    _save(plan)
    return plan


def propose_plan(source: str, moves: Iterable[dict], target: str = "", note: str = "") -> dict:
    """A plan Javis wrote itself (by topic, client, project...). Each move is {src, folder}: a file under `source`
    and a folder relative to `target`. Anything that would leave the target, or is not a file under the source, is
    dropped and counted."""
    source = fs.normalize_root(source)
    target = fs.normalize_root(target) if str(target or "").strip() else source
    if not os.path.isdir(source):
        raise OrganizeError("no_source")
    if not os.path.isdir(target):
        raise OrganizeError("no_target")
    projects = _ProjectDirs(source)
    items, rejected, seen = [], 0, set()
    for mv in moves or []:
        src = str((mv or {}).get("src") or "").strip()
        if src and not os.path.isabs(src):
            src = os.path.join(source, src)
        src = os.path.abspath(src) if src else ""
        folder = safe_rel((mv or {}).get("folder") or "")
        if (not src or src in seen or not folder or not fs._under(src, source) or not os.path.isfile(src)
                or projects.inside_project(os.path.dirname(src))):
            rejected += 1
            continue
        dst = os.path.join(target, folder, os.path.basename(src))
        if not fs._under(dst, target) or os.path.normcase(dst) == os.path.normcase(src):
            rejected += 1
            continue
        st = os.stat(src)
        ext = os.path.splitext(src)[1].lstrip(".").lower()
        seen.add(src)
        items.append({"src": src, "dst": dst, "folder": folder, "size": st.st_size, "mtime": st.st_mtime,
                      "cat": fs.category(ext)})
        if len(items) >= MAX_ITEMS:
            break
    _number_clashes(items)
    plan = {"id": time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex(), "created": time.time(), "by": "javis",
            "source": source, "target": target, "mode": "topic", "scope": "all", "items": items,
            "skipped": {"rejected": rejected}, "projects": [], "truncated": False, "note": str(note or "")[:300]}
    _save(plan)
    return plan


def _number_clashes(items: List[dict]) -> None:
    """Two files heading for the same name, or a name already taken on disk: number them like Explorer does."""
    taken = set()
    for it in items:
        dst = it["dst"]
        base, ext = os.path.splitext(dst)
        n = 1
        while os.path.normcase(dst) in taken or (os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(it["src"])):
            dst = f"{base} ({n}){ext}"
            n += 1
        taken.add(os.path.normcase(dst))
        it["dst"] = dst


def _save(plan: dict) -> None:
    p = _plan_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def current_plan() -> Optional[dict]:
    try:
        return json.loads(_plan_path().read_text(encoding="utf-8"))
    except Exception:
        return None


def discard_plan() -> bool:
    try:
        _plan_path().unlink()
        return True
    except OSError:
        return False


def plan_items(plan: dict, folder: str, limit: int = 500) -> List[dict]:
    return [{"src": it["src"], "dst": it["dst"], "size": it["size"]}
            for it in plan.get("items", []) if it["folder"] == folder][:limit]


def plan_summary(plan: dict, top: int = 30) -> dict:
    """Plan grouped by destination folder, biggest first, for the page and the tool."""
    groups: Dict[str, dict] = {}
    for it in plan.get("items", []):
        g = groups.setdefault(it["folder"], {"folder": it["folder"], "files": 0, "bytes": 0})
        g["files"] += 1
        g["bytes"] += it["size"]
    gl = sorted(groups.values(), key=lambda g: (-g["files"], g["folder"]))
    return {"id": plan.get("id"), "by": plan.get("by"), "source": plan.get("source"), "target": plan.get("target"),
            "mode": plan.get("mode"), "scope": plan.get("scope"), "files": len(plan.get("items", [])),
            "bytes": sum(it["size"] for it in plan.get("items", [])), "folders": gl[:top], "folder_count": len(gl),
            "skipped": plan.get("skipped", {}), "projects": plan.get("projects", []),
            "truncated": plan.get("truncated", False), "note": plan.get("note", ""), "created": plan.get("created")}


def _prune_up(folder: str, stop: str) -> None:
    folder, stop = os.path.abspath(folder), os.path.abspath(stop)
    while fs._under(folder, stop) and os.path.normcase(folder) != os.path.normcase(stop):
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def apply_plan(plan_id: str, only: Optional[Iterable[str]] = None, exclude: Optional[Iterable[str]] = None,
               exclude_folders: Optional[Iterable[str]] = None) -> dict:
    """Move the plan's files (all, or only the `only` sources, minus `exclude` and anything heading for one of
    `exclude_folders`). Returns {batch, moved, bytes, skipped}."""
    plan = current_plan()
    if not plan or plan.get("id") != plan_id:
        raise OrganizeError("no_plan")
    if fs.JOB.running():
        raise OrganizeError("scan_running")
    only_set = {os.path.normcase(x) for x in (only or [])}
    excl = {os.path.normcase(x) for x in (exclude or [])}
    excl_folders = set(exclude_folders or [])
    source, target = plan["source"], plan["target"]
    con = fs.connect()
    batch = "org-" + time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex()
    moved, skipped, total = 0, [], 0
    try:
        con.execute("INSERT INTO batches(id, at, note, kind, base) VALUES(?,?,?,?,?)",
                    (batch, time.time(), f"{plan.get('mode')}: {source}"[:200], "organize", target))
        con.commit()
        for it in plan["items"]:
            src, dst = it["src"], it["dst"]
            key = os.path.normcase(src)
            if (only_set and key not in only_set) or key in excl or it["folder"] in excl_folders:
                continue
            if not fs._under(dst, target):
                skipped.append({"path": src, "reason": "outside_target"})
                continue
            try:
                st = os.stat(src)
            except OSError:
                skipped.append({"path": src, "reason": "missing"})
                continue
            if st.st_size != it["size"] or abs(st.st_mtime - it["mtime"]) >= 0.001:
                skipped.append({"path": src, "reason": "changed"})
                continue
            if os.path.exists(dst):  # taken since the plan was made: number it again
                base, ext = os.path.splitext(dst)
                n = 1
                while os.path.exists(f"{base} ({n}){ext}"):
                    n += 1
                dst = f"{base} ({n}){ext}"
            row = con.execute("""SELECT root, ext, edge_hash, full_hash, dhash, img_w, img_h FROM files
                                 WHERE path = ?""", (src,)).fetchone()
            root, ext, edge, full, dh, w, h = row or ("", os.path.splitext(src)[1].lstrip(".").lower(), None, None,
                                                       None, None, None)
            con.execute("INSERT OR REPLACE INTO moves VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (batch, src, dst, root, st.st_size, st.st_mtime, ext, edge, full, dh, w, h, "moving",
                         time.time()))
            con.commit()
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.replace(src, dst)
                except OSError:
                    import shutil
                    shutil.move(src, dst)
            except OSError as e:
                con.execute("DELETE FROM moves WHERE batch = ? AND src = ?", (batch, src))
                con.commit()
                skipped.append({"path": src, "reason": "os_error", "detail": str(e)[:200]})
                continue
            con.execute("UPDATE moves SET state = 'organized', dst = ? WHERE batch = ? AND src = ?", (dst, batch, src))
            if row:
                # Keep the index (and its hashes) in step: same file, new place. Outside every scanned root it is
                # simply forgotten until the next scan.
                if fs._under(dst, root):
                    con.execute("UPDATE files SET path = ? WHERE path = ?", (dst, src))
                else:
                    con.execute("DELETE FROM files WHERE path = ?", (src,))
            con.commit()
            _prune_up(os.path.dirname(src), source)
            moved += 1
            total += st.st_size
        if moved:
            con.execute("UPDATE batches SET files = ?, bytes = ?, state = 'organized' WHERE id = ?", (moved, total, batch))
        else:
            con.execute("DELETE FROM batches WHERE id = ?", (batch,))
            batch = ""
        con.commit()
    finally:
        con.close()
    if moved:
        discard_plan()
    return {"batch": batch, "moved": moved, "bytes": total, "skipped": skipped}


def list_files(source: str, offset: int = 0, limit: int = 300) -> dict:
    """Files under source for Javis to sort by topic: relative path, size, date. Project folders are left out."""
    source = fs.normalize_root(source)
    if not os.path.isdir(source):
        raise OrganizeError("no_source")
    projects = _ProjectDirs(source)
    rows = []
    for path, size, mtime, offline in _walk_files(source, "all"):
        name = os.path.basename(path)
        if offline or name.startswith(".") or name.lower() in SKIP_NAMES:
            continue
        if projects.inside_project(os.path.dirname(path)):
            continue
        rows.append((os.path.relpath(path, source), size, mtime))
    rows.sort()
    page = rows[offset:offset + limit]
    return {"source": source, "total": len(rows), "offset": offset,
            "files": [{"rel": r, "size": s, "date": time.strftime("%Y-%m-%d", time.localtime(m))} for r, s, m in page]}
