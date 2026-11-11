"""file_scan.py - index the files under folders the owner picks, find exact duplicates, summarise what takes space.

Version 1 only READS the owner's files. Nothing is moved, renamed or deleted here; the only writes are the index
(STATE_DIR/file_scan/index.db) and, through the plugin, a Markdown report in the brain's exports/ folder.

How a scan works:
  1. Walk every root with os.scandir. Symlinks and junctions are not followed, dev/cache folders (.git, node_modules,
     __pycache__...) are skipped anywhere, and OS folders (Windows, Program Files, $Recycle.Bin, /proc...) are skipped
     when they sit at the top of a drive.
  2. A file whose size and modified time match the index keeps its stored hashes, so a second scan only hashes what
     changed. Rows under a scanned root that were not seen again are dropped.
  3. Duplicates are found in three passes, each one cheap enough to run on what the previous one left:
     same size -> same hash of the first and last 64 KB -> same hash of the whole file (BLAKE2b).
     Hard links to the same data count once, since they take no extra space.
  4. Cloud placeholders (OneDrive "online only" files) are listed but never read, because reading one downloads it.

Network storage: a mapped drive letter (Z:) is stored as its UNC path (//nas/share in Windows form), so scanning Z:
and the share itself never shows the same file twice as a duplicate. NAS housekeeping folders (Synology #recycle and
@eaDir, QNAP @Recycle and .@__thumb, snapshots) are skipped. `list_drives()` names local, removable and network drives.

Scans run on a background thread (`ScanJob`) so a whole drive does not hold a chat turn open; the plugin waits a
little, then reports progress, and `status()` tells later turns how it went.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import stat as stat_mod
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

EDGE_BYTES = 64 * 1024
CHUNK = 1024 * 1024
DEFAULT_MIN_SIZE = 1

# Skipped wherever they appear: tool caches and version control, never the owner's documents.
SKIP_ANYWHERE = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache",
    ".pytest_cache", ".gradle", ".idea", ".cache", ".trash", ".trashes", ".npm", ".nuget",
    # NAS recycle bins, thumbnails and snapshots (Synology, QNAP, NetApp, TrueNAS): copies the NAS made itself.
    "#recycle", "@eadir", "#snapshot", "@recycle", ".@__thumb", "@recently-snapshot", ".snapshot", ".snapshots",
    ".zfs", "@tmp", ".appledouble", "$recycle.bin",
}
# Skipped only directly under a drive or filesystem root, so a user folder that happens to be called "Windows" deep
# inside Documents is still scanned.
SKIP_AT_TOP = {
    "windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information",
    "recovery", "$windows.~bt", "$windows.~ws", "msocache", "perflogs",
    "proc", "sys", "dev", "run", "boot", "snap", "lost+found", "private", "system", "library", "volumes",
}
# Windows attributes of files whose data is not on disk (OneDrive / cloud placeholders).
_OFFLINE_ATTRS = 0x1000 | 0x400000 | 0x40000  # OFFLINE | RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN

CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "image": ("jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "heif", "tif", "tiff", "raw", "cr2", "nef", "arw",
              "dng", "svg", "psd", "ai"),
    "video": ("mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "m4v", "3gp", "mts", "m2ts"),
    "audio": ("mp3", "wav", "flac", "aac", "m4a", "ogg", "wma", "opus"),
    "document": ("pdf", "doc", "docx", "xls", "xlsx", "xlsm", "csv", "ppt", "pptx", "odt", "ods", "odp", "txt", "rtf",
                 "md", "epub", "pages", "numbers", "key"),
    "archive": ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "iso", "dmg"),
    "installer": ("exe", "msi", "apk", "pkg", "deb", "rpm", "appx", "msix"),
    "code": ("py", "js", "ts", "java", "c", "cpp", "h", "cs", "go", "rs", "php", "rb", "html", "css", "json", "xml",
             "yml", "yaml", "sql", "sh", "ps1", "ipynb"),
}
_EXT_TO_CAT = {e: c for c, exts in CATEGORIES.items() for e in exts}


def category(ext: str) -> str:
    return _EXT_TO_CAT.get((ext or "").lower(), "other")


def human_size(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------- index storage

def _state_dir() -> Path:
    try:
        import config
        base = Path(config.STATE_DIR)
    except Exception:
        base = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
    d = base / "file_scan"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return _state_dir() / "index.db"


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or db_path()), timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("""CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY, root TEXT NOT NULL, size INTEGER NOT NULL, mtime REAL NOT NULL, ext TEXT NOT NULL,
        offline INTEGER NOT NULL DEFAULT 0, edge_hash TEXT, full_hash TEXT, seen REAL NOT NULL)""")
    con.execute("CREATE INDEX IF NOT EXISTS files_size ON files(size)")
    con.execute("CREATE INDEX IF NOT EXISTS files_root ON files(root)")
    con.execute("""CREATE TABLE IF NOT EXISTS roots (
        root TEXT PRIMARY KEY, scanned_at REAL NOT NULL, files INTEGER NOT NULL, bytes INTEGER NOT NULL,
        skipped INTEGER NOT NULL, errors INTEGER NOT NULL, seconds REAL NOT NULL)""")
    return con


def _unc_of_drive(letter: str) -> Optional[str]:
    """UNC path behind a mapped Windows drive letter, or None (local drive, not mapped, not Windows)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buf))
        if ctypes.windll.mpr.WNetGetConnectionW(letter.upper() + ":", buf, ctypes.byref(size)) == 0:
            return buf.value or None
    except Exception:
        pass
    return None


def normalize_root(root: str, resolve_mapped: bool = True) -> str:
    p = os.path.abspath(os.path.expanduser(str(root or "").strip().strip('"')))
    if os.name == "nt" and len(p) == 2 and p[1] == ":":
        p += os.sep
    if resolve_mapped and os.name == "nt" and len(p) >= 3 and p[1] == ":":
        unc = _unc_of_drive(p[0])
        if unc:
            rest = p[3:]
            p = unc.rstrip(os.sep) + (os.sep + rest if rest else os.sep)
    return p


def is_network_path(path: str) -> bool:
    return str(path).startswith(("\\\\", "//"))


def list_drives() -> List[dict]:
    """Drives and mounts the owner can scan: {path, kind: local|removable|network|optical, unc?, label?, free?, total?}."""
    out: List[dict] = []
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            mask = k32.GetLogicalDrives()
            kinds = {2: "removable", 3: "local", 4: "network", 5: "optical", 6: "ramdisk"}
            for i in range(26):
                if not mask & (1 << i):
                    continue
                root = chr(65 + i) + ":" + os.sep
                kind = kinds.get(k32.GetDriveTypeW(root), "unknown")
                d = {"path": root, "kind": kind}
                if kind == "network":
                    d["unc"] = _unc_of_drive(root[0])
                if kind != "optical":
                    label = ctypes.create_unicode_buffer(261)
                    try:
                        if k32.GetVolumeInformationW(root, label, 261, None, None, None, None, 0):
                            d["label"] = label.value
                    except Exception:
                        pass
                    _add_space(d, root)
                out.append(d)
        except Exception:
            pass
        return out
    net_fs = {"cifs", "smbfs", "smb3", "nfs", "nfs4", "afpfs", "webdav", "davfs", "fuse.sshfs", "9p"}
    mounts: List[Tuple[str, str, str]] = []
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                mounts.append((parts[0], parts[1].replace("\\040", " "), parts[2]))
    except Exception:
        try:
            import subprocess
            res = subprocess.run(["mount"], capture_output=True, text=True, timeout=5).stdout
            for line in res.splitlines():
                # macOS: "//user@nas/share on /Volumes/share (smbfs, nodev, ...)"
                if " on " in line and " (" in line:
                    src, rest = line.split(" on ", 1)
                    mnt, opts = rest.rsplit(" (", 1)
                    mounts.append((src, mnt, opts.split(",")[0].strip()))
        except Exception:
            pass
    for src, mnt, fs in mounts:
        if fs in net_fs:
            d = {"path": mnt, "kind": "network", "unc": src, "fs": fs}
        elif src.startswith("/dev/") and not mnt.startswith(("/boot", "/snap", "/var/lib", "/run", "/sys", "/proc")):
            d = {"path": mnt, "kind": "removable" if mnt.startswith(("/media", "/Volumes", "/mnt")) else "local", "fs": fs}
        else:
            continue
        _add_space(d, mnt)
        out.append(d)
    return out


def _add_space(d: dict, path: str) -> None:
    try:
        import shutil
        u = shutil.disk_usage(path)
        d["total"], d["free"] = u.total, u.free
    except Exception:
        pass


def _under(path: str, root: str) -> bool:
    r = root if root.endswith(os.sep) else root + os.sep
    a, b = (path.lower(), r.lower()) if os.name == "nt" else (path, r)
    return a.startswith(b) or a == b.rstrip(os.sep)


def _like_prefix(root: str) -> str:
    r = root if root.endswith(os.sep) else root + os.sep
    return r.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _is_top(dir_path: str) -> bool:
    parent = os.path.dirname(dir_path.rstrip(os.sep)) or dir_path
    return os.path.dirname(parent) == parent  # parent is a drive / filesystem root


# ---------------------------------------------------------------- hashing

class Cancelled(Exception):
    pass


def edge_hash(path: str, size: int) -> str:
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        h.update(f.read(EDGE_BYTES))
        if size > 2 * EDGE_BYTES:
            f.seek(size - EDGE_BYTES)
            h.update(f.read(EDGE_BYTES))
        elif size > EDGE_BYTES:
            h.update(f.read())
    return h.hexdigest()


def full_hash(path: str, cancel: Optional[threading.Event] = None) -> str:
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- scan

def _walk(root: str, excludes: Iterable[str], cancel: threading.Event, progress: Callable[[dict], None],
          counters: dict):
    """Yield (path, size, mtime, offline) for every regular file under root."""
    excl = [normalize_root(e) for e in excludes if str(e or "").strip()]
    stack = [root]
    while stack:
        if cancel.is_set():
            raise Cancelled()
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            counters["errors"] += 1
            continue
        with it:
            for e in it:
                try:
                    if e.is_symlink() or (getattr(e, "is_junction", None) and e.is_junction()):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        name = e.name.lower()
                        if name in SKIP_ANYWHERE or (name in SKIP_AT_TOP and _is_top(e.path)):
                            counters["skipped"] += 1
                            continue
                        if any(_under(e.path, x) for x in excl):
                            counters["skipped"] += 1
                            continue
                        stack.append(e.path)
                        continue
                    if not e.is_file(follow_symlinks=False):
                        continue
                    st = e.stat(follow_symlinks=False)
                    if not stat_mod.S_ISREG(st.st_mode):
                        continue
                    attrs = getattr(st, "st_file_attributes", 0) or 0
                    yield e.path, st.st_size, st.st_mtime, bool(attrs & _OFFLINE_ATTRS)
                except OSError:
                    counters["errors"] += 1
        counters["dirs"] += 1
        if counters["dirs"] % 200 == 0:
            progress({"phase": "walk", "dir": d})


def scan(roots: List[str], excludes: Iterable[str] = (), cancel: Optional[threading.Event] = None,
         progress: Optional[Callable[[dict], None]] = None, con: Optional[sqlite3.Connection] = None,
         min_size: int = DEFAULT_MIN_SIZE) -> dict:
    """Index every root, then hash only what the duplicate search needs. Returns a summary dict."""
    cancel = cancel or threading.Event()
    progress = progress or (lambda _p: None)
    own = con is None
    con = con or connect()
    t0 = time.time()
    summary = {"roots": [], "files": 0, "bytes": 0, "hashed": 0, "errors": 0, "skipped": 0}
    try:
        for root in roots:
            root = normalize_root(root)
            if any(_under(root, r) for r in summary["roots"]):
                continue  # already covered by a wider root in this same scan
            if not os.path.isdir(root):
                raise FileNotFoundError(root)
            r0 = time.time()
            seen_at = time.time()
            counters = {"dirs": 0, "files": 0, "bytes": 0, "errors": 0, "skipped": 0}
            # Rows indexed under this root or under a folder inside it (an earlier, narrower scan).
            prefix = _like_prefix(root)
            nested = "root = ? OR root LIKE ? ESCAPE '!'"
            known = {p: (s, m) for p, s, m in con.execute(
                f"SELECT path, size, mtime FROM files WHERE {nested}", (root, prefix))}
            batch = []

            def flush():
                if batch:
                    con.executemany(
                        """INSERT INTO files(path, root, size, mtime, ext, offline, edge_hash, full_hash, seen)
                           VALUES(?,?,?,?,?,?,NULL,NULL,?)
                           ON CONFLICT(path) DO UPDATE SET root=excluded.root, size=excluded.size,
                             mtime=excluded.mtime, ext=excluded.ext, offline=excluded.offline,
                             edge_hash=NULL, full_hash=NULL, seen=excluded.seen""", batch)
                    batch.clear()

            unchanged = []
            for path, size, mtime, offline in _walk(root, excludes, cancel, progress, counters):
                counters["files"] += 1
                counters["bytes"] += size
                old = known.get(path)
                if old and old[0] == size and abs(old[1] - mtime) < 0.001:
                    unchanged.append((seen_at, int(offline), root, path))
                else:
                    ext = os.path.splitext(path)[1].lstrip(".").lower()[:16]
                    batch.append((path, root, size, mtime, ext, int(offline), seen_at))
                if len(batch) >= 2000:
                    flush()
                if len(unchanged) >= 5000:
                    con.executemany("UPDATE files SET seen=?, offline=?, root=? WHERE path=?", unchanged)
                    unchanged.clear()
                if counters["files"] % 5000 == 0:
                    progress({"phase": "walk", "files": counters["files"], "bytes": counters["bytes"]})
            flush()
            if unchanged:
                con.executemany("UPDATE files SET seen=?, offline=?, root=? WHERE path=?", unchanged)
            con.execute(f"DELETE FROM files WHERE ({nested}) AND seen < ?", (root, prefix, seen_at))
            con.execute("DELETE FROM roots WHERE root LIKE ? ESCAPE '!'", (prefix,))
            con.commit()
            hashed = _hash_candidates(con, root, cancel, progress, min_size)
            secs = time.time() - r0
            con.execute("INSERT OR REPLACE INTO roots VALUES(?,?,?,?,?,?,?)",
                        (root, time.time(), counters["files"], counters["bytes"], counters["skipped"],
                         counters["errors"], secs))
            con.commit()
            summary["roots"].append(root)
            summary["files"] += counters["files"]
            summary["bytes"] += counters["bytes"]
            summary["errors"] += counters["errors"]
            summary["skipped"] += counters["skipped"]
            summary["hashed"] += hashed
        summary["seconds"] = round(time.time() - t0, 1)
        return summary
    finally:
        if own:
            con.close()


def _reachable_roots(con: sqlite3.Connection) -> set:
    """Indexed roots that answer right now. A NAS that is switched off is left alone instead of timing out per file."""
    return {r for (r,) in con.execute("SELECT DISTINCT root FROM files") if os.path.isdir(r)}


def _hash_candidates(con: sqlite3.Connection, root: str, cancel: threading.Event,
                     progress: Callable[[dict], None], min_size: int) -> int:
    """Fill edge_hash for files sharing a size, then full_hash for files sharing (size, edge_hash).

    Sizes are matched across EVERY indexed root, not only the one just scanned, so a photo on the PC and its copy on
    the NAS are found even when the two places were scanned in separate runs. A file that cannot be read keeps a NULL
    hash and is tried again on the next scan (a NAS that dropped off for a moment is not marked unreadable forever)."""
    hashed = 0
    live = _reachable_roots(con)
    floor = max(1, min_size)
    rows = [(p, s) for p, s, r in con.execute(
        """SELECT path, size, root FROM files WHERE offline = 0 AND size >= ? AND edge_hash IS NULL
           AND size IN (SELECT size FROM files WHERE offline = 0 AND size >= ? GROUP BY size HAVING COUNT(*) > 1)
           ORDER BY root = ? DESC""", (floor, floor, root)) if r in live]
    for i, (path, size) in enumerate(rows):
        if cancel.is_set():
            raise Cancelled()
        try:
            con.execute("UPDATE files SET edge_hash = ? WHERE path = ?", (edge_hash(path, size), path))
            hashed += 1
        except OSError:
            pass
        if i % 500 == 0:
            progress({"phase": "edge", "done": i, "total": len(rows)})
            con.commit()
    con.commit()
    # Files no bigger than the two edges were already read in full by edge_hash; duplicates() groups them by it.
    rows = [(p, s) for p, s, r in con.execute(
        f"""SELECT f.path, f.size, f.root FROM files f JOIN (
               SELECT size, edge_hash FROM files WHERE offline = 0 AND edge_hash IS NOT NULL AND size > {2 * EDGE_BYTES}
               GROUP BY size, edge_hash HAVING COUNT(*) > 1) g
           ON f.size = g.size AND f.edge_hash = g.edge_hash
           WHERE f.full_hash IS NULL AND f.offline = 0""") if r in live]
    total = len(rows)
    for i, (path, size) in enumerate(rows):
        if cancel.is_set():
            raise Cancelled()
        try:
            con.execute("UPDATE files SET full_hash = ? WHERE path = ?", (full_hash(path, cancel), path))
            hashed += 1
        except OSError:
            pass
        if i % 50 == 0:
            progress({"phase": "full", "done": i, "total": total})
            con.commit()
    con.commit()
    return hashed


# ---------------------------------------------------------------- queries

def _root_filter(roots: Optional[List[str]]) -> Tuple[str, list]:
    if not roots:
        return "", []
    rs = [normalize_root(r) for r in roots]
    return " AND root IN (%s)" % ",".join("?" * len(rs)), rs


def _same_data(paths: List[str]) -> List[str]:
    """Collapse hard links: paths pointing at the same data take space once."""
    seen, out = set(), []
    for p in paths:
        try:
            st = os.stat(p)
            # Trust the file id only for real hard links: network shares may report 0 or reuse ids.
            key = (st.st_dev, st.st_ino) if st.st_ino and st.st_nlink > 1 else ("path", p)
        except OSError:
            key = ("path", p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def duplicates(roots: Optional[List[str]] = None, min_size: int = DEFAULT_MIN_SIZE,
               con: Optional[sqlite3.Connection] = None, check_links: bool = True) -> List[dict]:
    """Groups of identical files, biggest waste first. Each group suggests which copy to keep (oldest, then shortest
    path) but nothing acts on it."""
    own = con is None
    con = con or connect()
    try:
        where, params = _root_filter(roots)
        rows = con.execute(
            f"""SELECT size, full_hash, edge_hash, path, mtime FROM files
                WHERE offline = 0 AND size >= ? {where}
                AND ((full_hash IS NOT NULL AND full_hash != '!unreadable')
                     OR (size <= {2 * EDGE_BYTES} AND edge_hash IS NOT NULL AND edge_hash != '!unreadable'))""",
            [max(1, min_size)] + params).fetchall()
    finally:
        if own:
            con.close()
    groups: Dict[tuple, list] = {}
    for size, fh, eh, path, mtime in rows:
        key = (size, fh or ("edge:" + eh))
        groups.setdefault(key, []).append((path, mtime))
    out = []
    for (size, h), items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: (x[1], len(x[0]), x[0]))
        paths = [p for p, _ in items]
        if check_links:
            paths = _same_data(paths)
        if len(paths) < 2:
            continue
        out.append({"size": size, "hash": h, "count": len(paths), "wasted": size * (len(paths) - 1),
                    "keep": paths[0], "copies": paths[1:], "ext": os.path.splitext(paths[0])[1].lstrip(".").lower()})
    out.sort(key=lambda g: (-g["wasted"], g["keep"]))
    return out


def stats(roots: Optional[List[str]] = None, top: int = 10, con: Optional[sqlite3.Connection] = None) -> dict:
    own = con is None
    con = con or connect()
    try:
        where, params = _root_filter(roots)
        total = con.execute(f"SELECT COUNT(*), COALESCE(SUM(size),0) FROM files WHERE 1=1 {where}", params).fetchone()
        by_cat: Dict[str, list] = {}
        for ext, n, b in con.execute(
                f"SELECT ext, COUNT(*), SUM(size) FROM files WHERE 1=1 {where} GROUP BY ext", params):
            c = by_cat.setdefault(category(ext), [0, 0])
            c[0] += n
            c[1] += b or 0
        biggest = con.execute(
            f"SELECT path, size FROM files WHERE 1=1 {where} ORDER BY size DESC LIMIT ?", params + [top]).fetchall()
        offline = con.execute(f"SELECT COUNT(*) FROM files WHERE offline = 1 {where}", params).fetchone()[0]
        folders: Dict[str, list] = {}
        root_rows = con.execute(f"SELECT root, scanned_at, files, bytes, skipped, errors, seconds FROM roots "
                                f"WHERE 1=1 {where}", params).fetchall()
        for root, *_ in root_rows:
            for path, size in con.execute("SELECT path, size FROM files WHERE root = ?", (root,)):
                rel = os.path.relpath(path, root)
                # Group by the first folder under the root; files sitting at the top count under the root itself.
                key = os.path.join(root, rel.split(os.sep, 1)[0]) if os.sep in rel else root
                f = folders.setdefault(key, [0, 0])
                f[0] += 1
                f[1] += size
    finally:
        if own:
            con.close()
    return {
        "files": total[0], "bytes": total[1], "offline": offline,
        "categories": sorted(({"category": k, "files": v[0], "bytes": v[1]} for k, v in by_cat.items()),
                             key=lambda x: -x["bytes"]),
        "biggest": [{"path": p, "size": s} for p, s in biggest],
        "folders": sorted(({"path": k, "files": v[0], "bytes": v[1]} for k, v in folders.items()),
                          key=lambda x: -x["bytes"])[:top],
        "roots": [{"root": r[0], "scanned_at": r[1], "files": r[2], "bytes": r[3], "skipped": r[4], "errors": r[5],
                   "seconds": r[6]} for r in root_rows],
    }


def report_markdown(roots: Optional[List[str]] = None, max_groups: int = 200) -> str:
    """The report the plugin saves into the brain. Written in Vietnamese: it is the owner's own content."""
    st = stats(roots)
    groups = duplicates(roots)
    wasted = sum(g["wasted"] for g in groups)
    lines = [
        "---", "type: report", f"created: {time.strftime('%Y-%m-%d')}", "tags: [don-o-dia, file-trung]", "---", "",
        f"# Báo cáo quét file {time.strftime('%Y-%m-%d %H:%M')}", "",
        "Báo cáo chỉ đọc: Javis chưa di chuyển hay xoá file nào.", "",
        "## Tổng quan", "",
    ]
    for r in st["roots"]:
        lines.append(f"- `{r['root']}`: {r['files']:,} file, {human_size(r['bytes'])}, quét lúc "
                     f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['scanned_at']))} trong {r['seconds']:.0f} giây"
                     + (f", {r['errors']} chỗ không đọc được" if r["errors"] else ""))
    lines += ["", f"- **{len(groups):,} nhóm file trùng, chiếm thừa {human_size(wasted)}.**"]
    if st["offline"]:
        lines.append(f"- {st['offline']:,} file chỉ nằm trên đám mây (OneDrive...) nên không so sánh nội dung.")
    names = {"image": "Ảnh", "video": "Video", "audio": "Âm thanh", "document": "Tài liệu", "archive": "File nén",
             "installer": "File cài đặt", "code": "Mã nguồn", "other": "Khác"}
    lines += ["", "## Dung lượng theo loại", ""]
    for c in st["categories"]:
        lines.append(f"- {names.get(c['category'], c['category'])}: {c['files']:,} file, {human_size(c['bytes'])}")
    lines += ["", "## Thư mục nặng nhất", ""]
    for f in st["folders"]:
        lines.append(f"- `{f['path']}`: {human_size(f['bytes'])} ({f['files']:,} file)")
    lines += ["", "## File lớn nhất", ""]
    for b in st["biggest"]:
        lines.append(f"- `{b['path']}`: {human_size(b['size'])}")
    lines += ["", "## Các nhóm file trùng", "",
              "Bản đề xuất giữ là bản cũ nhất (đường dẫn ngắn nhất nếu bằng nhau). Hãy tự kiểm tra trước khi xoá.", ""]
    for i, g in enumerate(groups[:max_groups], 1):
        lines.append(f"### {i}. {os.path.basename(g['keep'])} - {g['count']} bản, thừa {human_size(g['wasted'])}")
        lines.append(f"- Giữ: `{g['keep']}`")
        for c in g["copies"]:
            lines.append(f"- Trùng: `{c}`")
        lines.append("")
    if len(groups) > max_groups:
        lines.append(f"_Còn {len(groups) - max_groups:,} nhóm nhỏ hơn không liệt kê._")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- background job

class ScanJob:
    """One scan at a time, on a daemon thread. Thread-safe status for the plugin to poll."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self.state: dict = {"status": "idle"}

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, roots: List[str], excludes: Iterable[str] = (), min_size: int = DEFAULT_MIN_SIZE,
              on_done: Optional[Callable[[dict], None]] = None) -> bool:
        with self._lock:
            if self.running():
                return False
            self._cancel = threading.Event()
            self.state = {"status": "running", "roots": [normalize_root(r) for r in roots], "started": time.time(),
                          "progress": {}}
            cancel = self._cancel
            excludes = list(excludes)

            def run():
                try:
                    res = scan(roots, excludes, cancel=cancel, progress=self._progress, min_size=min_size)
                    self.state = {**self.state, "status": "done", "result": res, "finished": time.time()}
                except Cancelled:
                    self.state = {**self.state, "status": "cancelled", "finished": time.time()}
                except Exception as e:  # keep the reason for the next status call
                    self.state = {**self.state, "status": "error", "error": f"{type(e).__name__}: {e}",
                                  "finished": time.time()}
                if on_done:
                    try:
                        on_done(dict(self.state))
                    except Exception:
                        pass

            self._thread = threading.Thread(target=run, name="javis-file-scan", daemon=True)
            self._thread.start()
            return True

    def _progress(self, p: dict) -> None:
        self.state = {**self.state, "progress": p}

    def wait(self, seconds: float) -> bool:
        t = self._thread
        if t:
            t.join(max(0.0, seconds))
        return not self.running()

    def cancel(self) -> bool:
        if not self.running():
            return False
        self._cancel.set()
        return True


JOB = ScanJob()
