"""file_scan.py - index the files under folders the owner picks, find exact duplicates and look-alike photos, summarise
what takes space, and move unwanted copies into a quarantine the owner can undo.

Scanning only READS the owner's files; the index lives in STATE_DIR/file_scan/index.db. The one thing that changes the
owner's disk is `quarantine()`, and it never deletes: see "Quarantine" below.

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

Look-alike photos: with Pillow installed, every photo of at least 10 KB gets a 64-bit difference hash (dHash) of a
9x8 greyscale thumbnail, EXIF rotation applied. Photos whose hashes differ in at most `SIMILAR_BITS` bits are grouped:
resized, re-compressed or lightly edited copies. Without Pillow the rest works and `similar()` says it is missing.

Quarantine: a chosen copy is MOVED (a rename, same volume, so instant even on a NAS) into
`<scanned folder>/.javis-quarantine/<batch>/<same relative path>` and journalled in the `moves` table. Before each move
the file must still match the index, and another copy that is not being moved must still exist on disk: identical for
duplicates, or within `SIMILAR_BITS` for look-alike photos. So the last copy can never be quarantined. `restore()` puts a
batch back; only `purge()` deletes, and only files already in quarantine.

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
    # Javis's own quarantine: copies already set aside must not show up as duplicates again.
    ".javis-quarantine",
}
QUARANTINE_DIR = ".javis-quarantine"
SIMILAR_BITS = 6
IMAGE_MIN_BYTES = 10 * 1024
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "bmp", "gif", "tif", "tiff")
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
    cols = {r[1] for r in con.execute("PRAGMA table_info(files)")}
    # img_w = -1 marks a photo Pillow could not open, so it is not retried until the file changes.
    for col in ("dhash INTEGER", "img_w INTEGER", "img_h INTEGER"):
        if col.split()[0] not in cols:
            con.execute(f"ALTER TABLE files ADD COLUMN {col}")
    con.execute("""CREATE TABLE IF NOT EXISTS batches (
        id TEXT PRIMARY KEY, at REAL NOT NULL, note TEXT NOT NULL DEFAULT '', files INTEGER NOT NULL DEFAULT 0,
        bytes INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'quarantined')""")
    con.execute("""CREATE TABLE IF NOT EXISTS moves (
        batch TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL, root TEXT NOT NULL, size INTEGER NOT NULL,
        mtime REAL NOT NULL, ext TEXT NOT NULL, edge_hash TEXT, full_hash TEXT, dhash INTEGER, img_w INTEGER,
        img_h INTEGER, state TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY (batch, src))""")
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
    mounts: List[Tuple[str, str, str, str]] = []
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 4:
                mounts.append((_unescape_mount(parts[0]), _unescape_mount(parts[1]), parts[2], parts[3]))
    except Exception:
        try:
            import subprocess
            res = subprocess.run(["mount"], capture_output=True, text=True, timeout=5).stdout
            for line in res.splitlines():
                # macOS: "//user@nas/share on /Volumes/share (smbfs, nodev, ...)"
                if " on " in line and " (" in line:
                    src, rest = line.split(" on ", 1)
                    mnt, opts = rest.rsplit(" (", 1)
                    fs_type = opts.split(",")[0].strip()
                    mounts.append((src, mnt, fs_type, "ro" if "read-only" in opts else "rw"))
        except Exception:
            pass
    try:
        state = str(_state_dir().parent)
    except Exception:
        state = ""
    for src, mnt, fs_type, opts in mounts:
        d = classify_mount(src, mnt, fs_type, opts)
        if not d or not os.path.isdir(mnt):
            continue
        if state and (state == mnt or state.startswith(mnt.rstrip("/") + "/")):
            continue  # the volume holding Javis's own state (/data in Docker) is not the owner's files
        _add_space(d, mnt)
        out.append(d)
    return out


NET_FS = {"cifs", "smbfs", "smb3", "nfs", "nfs4", "afpfs", "webdav", "davfs", "fuse.sshfs"}
_SYSTEM_MOUNTS = ("/boot", "/snap", "/var/lib", "/run", "/sys", "/proc", "/dev", "/etc", "/usr", "/certs")


def _unescape_mount(s: str) -> str:
    """/proc/mounts writes space, tab, newline and backslash as octal escapes (\\040, \\134...)."""
    import re
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), s)


def classify_mount(src: str, mnt: str, fs_type: str, opts: str = "") -> Optional[dict]:
    """One /proc/mounts line -> a drive the owner may scan, or None for system and hidden mounts.

    Docker Desktop on Windows shows a bind-mounted host folder as `9p` with the drive as source (E:\\), so it reads as
    the host drive it is, not as a NAS. Read-only mounts are flagged: they can be scanned, never cleaned."""
    if mnt == "/" or mnt.startswith(_SYSTEM_MOUNTS) or any(part.startswith(".") for part in mnt.split("/") if part):
        return None
    ro = "ro" in opts.split(",")
    if fs_type in NET_FS:
        d = {"path": mnt, "kind": "network", "unc": src, "fs": fs_type}
    elif fs_type == "9p" and ("drvfs" in opts or (len(src) >= 2 and src[1] == ":")):
        d = {"path": mnt, "kind": "local", "host": src, "fs": fs_type}
    elif fs_type in ("9p", "virtiofs", "fakeowner", "grpcfuse", "fuse.grpcfuse", "osxfs"):
        d = {"path": mnt, "kind": "local", "fs": fs_type}
    elif src.startswith("/dev/"):
        d = {"path": mnt, "kind": "removable" if mnt.startswith(("/media", "/Volumes", "/mnt")) else "local", "fs": fs_type}
    else:
        return None
    if ro:
        d["readonly"] = True
    return d


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
         min_size: int = DEFAULT_MIN_SIZE, images: bool = True) -> dict:
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
                             edge_hash=NULL, full_hash=NULL, dhash=NULL, img_w=NULL, img_h=NULL,
                             seen=excluded.seen""", batch)
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
            if images:
                summary["images"] = summary.get("images", 0) + _hash_images(con, root, cancel, progress)
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


# ---------------------------------------------------------------- look-alike photos

def pillow_ready() -> bool:
    try:
        import PIL.Image  # noqa: F401
        return True
    except Exception:
        return False


def _to_signed(v: int) -> int:
    return v - (1 << 64) if v >= (1 << 63) else v


def _to_unsigned(v: int) -> int:
    return v + (1 << 64) if v < 0 else v


def image_dhash(path: str) -> Tuple[int, int, int]:
    """(dhash as a signed 64-bit int, width, height). Raises when the file is not an image Pillow can open."""
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        w, h = im.size
        try:
            im.draft("L", (64, 64))  # JPEG: decode at 1/8 scale, many times faster
        except Exception:
            pass
        if getattr(im, "is_animated", False):
            im.seek(0)
        small = ImageOps.exif_transpose(im) if hasattr(ImageOps, "exif_transpose") else im
        exif_rot = False
        try:
            exif_rot = im.getexif().get(0x0112, 1) in (5, 6, 7, 8)
        except Exception:
            pass
        if exif_rot:
            w, h = h, w
        g = small.convert("L").resize((9, 8), Image.BILINEAR)
        px = list(g.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return _to_signed(bits), int(w), int(h)


def _hash_images(con: sqlite3.Connection, root: str, cancel: threading.Event,
                 progress: Callable[[dict], None]) -> int:
    if not pillow_ready():
        return 0
    marks = ",".join("?" * len(IMAGE_EXTS))
    rows = con.execute(
        f"""SELECT path FROM files WHERE root = ? AND offline = 0 AND size >= ? AND dhash IS NULL
            AND (img_w IS NULL OR img_w >= 0) AND ext IN ({marks})""",
        [root, IMAGE_MIN_BYTES] + list(IMAGE_EXTS)).fetchall()
    done = 0
    for i, (path,) in enumerate(rows):
        if cancel.is_set():
            raise Cancelled()
        try:
            dh, w, h = image_dhash(path)
            con.execute("UPDATE files SET dhash = ?, img_w = ?, img_h = ? WHERE path = ?", (dh, w, h, path))
            done += 1
        except OSError as e:
            if os.path.exists(path) and "cannot identify" not in str(e).lower():
                continue  # a read error (NAS hiccup): try again next scan
            con.execute("UPDATE files SET img_w = -1 WHERE path = ?", (path,))
        except Exception:
            con.execute("UPDATE files SET img_w = -1 WHERE path = ?", (path,))
        if i % 200 == 0:
            progress({"phase": "image", "done": i, "total": len(rows)})
            con.commit()
    con.commit()
    return done


def _hamming(a: int, b: int) -> int:
    return bin(_to_unsigned(a) ^ _to_unsigned(b)).count("1")


def similar(roots: Optional[List[str]] = None, bits: int = SIMILAR_BITS,
            con: Optional[sqlite3.Connection] = None) -> List[dict]:
    """Groups of look-alike photos that are NOT all byte-identical (those are in duplicates()). The suggested keeper
    is the largest picture, then the biggest file, then the oldest."""
    bits = max(0, min(int(bits), 12))
    own = con is None
    con = con or connect()
    try:
        where, params = _root_filter(roots)
        rows = con.execute(
            f"""SELECT path, size, mtime, dhash, img_w, img_h, COALESCE(full_hash, 'e:' || edge_hash, 'p:' || path)
                FROM files WHERE dhash IS NOT NULL AND img_w > 0 AND offline = 0 {where}""", params).fetchall()
    finally:
        if own:
            con.close()
    n = len(rows)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Split the 64 bits into bits+1 bands: two hashes within `bits` differences share at least one whole band.
    bands = bits + 1
    width = 64 // bands or 1
    buckets: Dict[tuple, List[int]] = {}
    for i, r in enumerate(rows):
        u = _to_unsigned(r[3])
        for b in range(bands):
            lo = b * width
            hi = 64 if b == bands - 1 else lo + width
            key = (b, (u >> lo) & ((1 << (hi - lo)) - 1))
            buckets.setdefault(key, []).append(i)
    for members in buckets.values():
        if len(members) < 2 or len(members) > 400:  # a huge bucket is flat images (blank, black): skip, too costly
            continue
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                a, b = members[x], members[y]
                if find(a) != find(b) and _hamming(rows[a][3], rows[b][3]) <= bits:
                    parent[find(a)] = find(b)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        items = [rows[i] for i in members]
        if len({it[6] for it in items}) < 2:
            continue  # all byte-identical: already a duplicate group
        items.sort(key=lambda it: (-(it[4] * it[5]), -it[1], it[2], it[0]))
        files = [{"path": it[0], "size": it[1], "mtime": it[2], "w": it[4], "h": it[5]} for it in items]
        out.append({"count": len(files), "keep": files[0]["path"], "files": files,
                    "bytes": sum(f["size"] for f in files[1:])})
    out.sort(key=lambda g: (-g["bytes"], g["keep"]))
    return out


def thumbnail(path: str, side: int = 240) -> Optional[bytes]:
    """A small JPEG of an INDEXED photo, or None (not indexed, not a photo, no Pillow)."""
    con = connect()
    try:
        row = con.execute("SELECT ext FROM files WHERE path = ?", (path,)).fetchone()
    finally:
        con.close()
    if not row or row[0] not in IMAGE_EXTS or not pillow_ready():
        return None
    try:
        import io
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            try:
                im.draft("RGB", (side * 2, side * 2))
            except Exception:
                pass
            if getattr(im, "is_animated", False):
                im.seek(0)
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((side, side))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=78)
            return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------- quarantine (the only part that moves files)

class QuarantineError(Exception):
    pass


def _identity(row) -> Optional[tuple]:
    size, edge, full = row
    if full:
        return (size, "f", full)
    if edge and size <= 2 * EDGE_BYTES:
        return (size, "e", edge)
    return None


def _still_same(path: str, size: int, mtime: float) -> bool:
    try:
        st = os.stat(path)
    except OSError:
        return False
    return st.st_size == size and abs(st.st_mtime - mtime) < 0.001


def _keeper_for(con: sqlite3.Connection, row: tuple, chosen: set, allow_similar: bool) -> Optional[str]:
    """Another copy that stays where it is, still on disk and unchanged, or None."""
    path, size, mtime, edge, full, dh = row[0], row[2], row[3], row[5], row[6], row[7]
    ident = _identity((size, edge, full))
    if ident:
        col = "full_hash" if ident[1] == "f" else "edge_hash"
        for p, s, m in con.execute(f"SELECT path, size, mtime FROM files WHERE size = ? AND {col} = ? AND path != ?",
                                   (size, ident[2], path)):
            if p not in chosen and _still_same(p, s, m):
                return p
    if allow_similar and dh is not None:
        for p, s, m, odh in con.execute(
                "SELECT path, size, mtime, dhash FROM files WHERE dhash IS NOT NULL AND img_w > 0 AND path != ?", (path,)):
            if p not in chosen and _hamming(dh, odh) <= SIMILAR_BITS and _still_same(p, s, m):
                return p
    return None


def quarantine(paths: List[str], allow_similar: bool = False, note: str = "",
               con: Optional[sqlite3.Connection] = None) -> dict:
    """Move the chosen copies into quarantine. Every path is checked on its own; a refused path never stops the others.
    Returns {batch, moved: [...], refused: [{path, reason}], bytes}."""
    own = con is None
    con = con or connect()
    chosen = {str(p) for p in paths if str(p or "").strip()}
    batch = time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex()
    moved, refused, total = [], [], 0
    try:
        con.execute("INSERT INTO batches(id, at, note) VALUES(?,?,?)", (batch, time.time(), str(note or "")[:200]))
        con.commit()
        for path in sorted(chosen):
            row = con.execute("""SELECT path, root, size, mtime, ext, edge_hash, full_hash, dhash, img_w, img_h
                                 FROM files WHERE path = ?""", (path,)).fetchone()
            if not row:
                refused.append({"path": path, "reason": "not_indexed"})
                continue
            if not _still_same(path, row[2], row[3]):
                refused.append({"path": path, "reason": "changed"})
                continue
            keeper = _keeper_for(con, row, chosen, allow_similar)
            if not keeper:
                refused.append({"path": path, "reason": "last_copy"})
                continue
            root = row[1]
            rel = os.path.relpath(path, root)
            if rel.startswith(".."):
                refused.append({"path": path, "reason": "outside_root"})
                continue
            dst = os.path.join(root, QUARANTINE_DIR, batch, rel)
            con.execute("INSERT INTO moves VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (batch, path, dst, root, row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9],
                         "moving", time.time()))
            con.commit()
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.replace(path, dst)
                except OSError:
                    import shutil
                    shutil.move(path, dst)
            except OSError as e:
                con.execute("DELETE FROM moves WHERE batch = ? AND src = ?", (batch, path))
                con.commit()
                refused.append({"path": path, "reason": "os_error", "detail": str(e)[:200]})
                continue
            con.execute("UPDATE moves SET state = 'quarantined' WHERE batch = ? AND src = ?", (batch, path))
            con.execute("DELETE FROM files WHERE path = ?", (path,))
            con.commit()
            moved.append({"path": path, "keeper": keeper, "size": row[2]})
            total += row[2]
        if moved:
            con.execute("UPDATE batches SET files = ?, bytes = ? WHERE id = ?", (len(moved), total, batch))
        else:
            con.execute("DELETE FROM batches WHERE id = ?", (batch,))
            batch = ""
        con.commit()
        return {"batch": batch, "moved": moved, "refused": refused, "bytes": total}
    finally:
        if own:
            con.close()


def batches(con: Optional[sqlite3.Connection] = None) -> List[dict]:
    own = con is None
    con = con or connect()
    try:
        out = []
        for bid, at, note, n, b, state in con.execute(
                "SELECT id, at, note, files, bytes, state FROM batches ORDER BY at DESC"):
            files = [{"src": s, "dst": d, "size": z, "state": st} for s, d, z, st in con.execute(
                "SELECT src, dst, size, state FROM moves WHERE batch = ? ORDER BY src", (bid,))]
            out.append({"id": bid, "at": at, "note": note, "files": n, "bytes": b, "state": state, "items": files})
        return out
    finally:
        if own:
            con.close()


def _prune_empty(folder: str, stop: str) -> None:
    """Remove empty folders from `folder` up to (not including) `stop`. Called on quarantine paths only, so the folders
    climbed are the batch folders and `.javis-quarantine` itself."""
    folder, stop = os.path.abspath(folder), os.path.abspath(stop)
    while folder.startswith(stop) and folder != stop:
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def restore(batch: str, con: Optional[sqlite3.Connection] = None) -> dict:
    """Put a batch back where each file came from. A file whose original place is taken again stays in quarantine."""
    own = con is None
    con = con or connect()
    restored, kept = [], []
    try:
        rows = con.execute("""SELECT src, dst, root, size, mtime, ext, edge_hash, full_hash, dhash, img_w, img_h
                              FROM moves WHERE batch = ? AND state IN ('quarantined', 'moving')""", (batch,)).fetchall()
        if not rows:
            raise QuarantineError("no_batch")
        for src, dst, root, size, mtime, ext, edge, full, dh, w, h in rows:
            if not os.path.exists(dst):
                if os.path.exists(src):  # a move that never happened (crash between journal and rename)
                    con.execute("DELETE FROM moves WHERE batch = ? AND src = ?", (batch, src))
                    continue
                kept.append({"path": src, "reason": "missing"})
                con.execute("UPDATE moves SET state = 'missing' WHERE batch = ? AND src = ?", (batch, src))
                continue
            if os.path.exists(src):
                kept.append({"path": src, "reason": "taken"})
                continue
            try:
                os.makedirs(os.path.dirname(src), exist_ok=True)
                try:
                    os.replace(dst, src)
                except OSError:
                    import shutil
                    shutil.move(dst, src)
            except OSError as e:
                kept.append({"path": src, "reason": "os_error", "detail": str(e)[:200]})
                continue
            con.execute("UPDATE moves SET state = 'restored' WHERE batch = ? AND src = ?", (batch, src))
            con.execute("""INSERT OR REPLACE INTO files(path, root, size, mtime, ext, offline, edge_hash, full_hash, seen,
                           dhash, img_w, img_h) VALUES(?,?,?,?,?,0,?,?,?,?,?,?)""",
                        (src, root, size, mtime, ext, edge, full, time.time(), dh, w, h))
            _prune_empty(os.path.dirname(dst), root)
            restored.append(src)
        _close_batch(con, batch)
        con.commit()
        return {"batch": batch, "restored": restored, "kept": kept}
    finally:
        if own:
            con.close()


def purge(batch: str, con: Optional[sqlite3.Connection] = None) -> dict:
    """Delete for good the files of one batch that are still in quarantine. Nothing outside quarantine is touched."""
    own = con is None
    con = con or connect()
    deleted, failed, freed = [], [], 0
    try:
        rows = con.execute("SELECT src, dst, root, size FROM moves WHERE batch = ? AND state = 'quarantined'",
                           (batch,)).fetchall()
        if not rows:
            raise QuarantineError("no_batch")
        for src, dst, root, size in rows:
            qroot = os.path.join(root, QUARANTINE_DIR, batch)
            if not _under(dst, qroot):
                failed.append({"path": dst, "reason": "outside_quarantine"})
                continue
            try:
                if os.path.exists(dst):
                    os.remove(dst)
                    freed += size
            except OSError as e:
                failed.append({"path": dst, "reason": "os_error", "detail": str(e)[:200]})
                continue
            con.execute("UPDATE moves SET state = 'purged' WHERE batch = ? AND src = ?", (batch, src))
            _prune_empty(os.path.dirname(dst), root)
            deleted.append(dst)
        _close_batch(con, batch)
        con.commit()
        return {"batch": batch, "deleted": len(deleted), "failed": failed, "bytes": freed}
    finally:
        if own:
            con.close()


def _close_batch(con: sqlite3.Connection, batch: str) -> None:
    left = con.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM moves WHERE batch = ? AND state = 'quarantined'",
                       (batch,)).fetchone()
    states = {r[0] for r in con.execute("SELECT DISTINCT state FROM moves WHERE batch = ?", (batch,))}
    state = "quarantined" if left[0] else ("purged" if "purged" in states else "restored")
    con.execute("UPDATE batches SET files = ?, bytes = ?, state = ? WHERE id = ?", (left[0], left[1], state, batch))


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
              on_done: Optional[Callable[[dict], None]] = None, images: bool = True) -> bool:
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
                    res = scan(roots, excludes, cancel=cancel, progress=self._progress, min_size=min_size,
                               images=images)
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
