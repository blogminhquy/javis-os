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
- it needs the room it will take on the disk, with KEEP_FREE left over, and stops if the sizes it announced lie;
- it always becomes a NEW brain folder, never written over an existing one, extracted into a work folder first and
  moved into place only once complete;
- whatever would run on its own is switched off: plugins (real Python), loops and pending reminders. The owner switches
  back on what they want, on this machine, knowingly.

Limits (owner, same day: "20.000 file ... file text 1gb sẽ được rất nhiều"): no fixed size cap. What protects the server
is its free disk: a job starts only when the disk keeps KEEP_FREE after it. The file count cap is a million, only there
to stop a zip of countless empty entries.

Sized for Cloudflare Tunnel, the HTTPS path DEPLOY.md recommends, which cuts a request body past about 100MB and a reply
that has not started within about 100 seconds:
- an export is packed in the background (start, then poll the progress) and downloaded once ready, so the download
  starts at once whatever the size;
- an upload is sent in CHUNK pieces and put together on the server; a piece that fails is sent again from where the
  server says it stopped.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

import brain_label
import fastyaml
import git_brain
import localefmt

MAX_FILES = 1_000_000                  # only against a zip of countless empty entries
KEEP_FREE = 1024 * 1024 * 1024         # the disk keeps at least this much free after an export or an import
CHUNK = 32 * 1024 * 1024               # one upload piece: well under Cloudflare's ~100MB per request
MANIFEST = "javis-brain.json"
IMPORT_PREFIX = ".javis-import-"
_ID = re.compile(r"^[0-9a-f]{32}$")

_SECRET_NAMES = {".env", ".mcp.json", ".mcp_hub.json", ".javis-learn.lock", ".ds_store"}
_SECRET_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
_SECRET_SUFFIXES = (".tmp", ".pem", ".key", ".p12", ".pfx")
_SKIP_DIRS = {".git", ".trash"}


class TooBig(Exception):
    """Over MAX_FILES."""


class NoSpace(Exception):
    """The disk would keep less than KEEP_FREE. Carries what is needed and what is free, in bytes."""

    def __init__(self, need: int, free: int):
        super().__init__(f"need {need}, free {free}")
        self.need, self.free = need, free


def free_bytes(path) -> int:
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(str(p)).free
    except OSError:
        return 0


def need_space(path, need: int) -> None:
    """Raise NoSpace unless `need` bytes fit under `path` with KEEP_FREE left over."""
    free = free_bytes(path)
    if need + KEEP_FREE > free:
        raise NoSpace(int(need) + KEEP_FREE, free)


def gb(n) -> str:
    return f"{max(0, n) / 1024 / 1024 / 1024:.1f} GB"


def no_space_text(e: "NoSpace") -> str:
    return localefmt.chu(f"Máy chủ không đủ chỗ trống: cần khoảng {gb(e.need)}, còn {gb(e.free)}.",
                         f"Not enough free disk on the server: about {gb(e.need)} needed, {gb(e.free)} free.")


def too_many_text() -> str:
    return localefmt.chu(f"Quá nhiều file (trần {MAX_FILES:,}).", f"Too many files (limit {MAX_FILES:,}).")


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
    """(files, bytes) the export of this brain would hold. Raises TooBig past MAX_FILES."""
    root = Path(root)
    files = total = 0
    for p, _rel in _walk(root):
        try:
            total += p.stat().st_size
        except OSError:
            continue
        files += 1
        if files > MAX_FILES:
            raise TooBig()
    return files, total


def export_zip(root, dst: str, app_version: str = "", progress=None) -> tuple:
    """Write the brain at `root` into the zip `dst`, under one top folder named like the brain's folder, with a small
    manifest (label, folder, date) at the top so an import keeps the name. Returns (files, bytes).
    `progress(files_done)` is called every few hundred files."""
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
            if files > MAX_FILES:
                raise TooBig()
            try:
                zf.write(p, top + "/" + rel)
            except (OSError, ValueError):
                continue
            if progress and files % 200 == 0:
                progress(files)
    if progress:
        progress(files)
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
    import yaml   # writing only; reading goes through fastyaml like every other module
    n = 0
    for d in (root / "plugins", root / "Javis" / "plugins"):
        if not d.is_dir():
            continue
        for f in list(d.glob("*/plugin.yaml")) + list(d.glob("*/plugin.yml")):
            try:
                m = fastyaml.safe_load(f.read_text(encoding="utf-8")) or {}
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
        declared = sum(i.file_size for i, _rel in members)
        need_space(brains_dir, declared)

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
                        if total > declared:
                            raise BadFile("sizes lie")   # more data than the zip announced: stop before the disk fills
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


# ---- export in the background: start, poll, download ----

_JOBS: dict = {}
_LOCK = threading.Lock()
_DONE_KEEP_S = 1800      # a finished file waits this long for its download (a retry included), then is swept


def _sweep_exports(out_dir: Path) -> None:
    now = time.time()
    with _LOCK:
        for jid, j in list(_JOBS.items()):
            if j["status"] in ("done", "error") and now - j.get("finished", now) > _DONE_KEEP_S:
                _JOBS.pop(jid, None)
                if j.get("path"):
                    try:
                        os.unlink(j["path"])
                    except OSError:
                        pass
        live = {j.get("path") for j in _JOBS.values()}
    try:
        for p in Path(out_dir).glob("*.zip"):
            if str(p) not in live and now - p.stat().st_mtime > _DONE_KEEP_S:
                p.unlink()
    except OSError:
        pass


def _run_export(job: dict, root: Path, app_version: str) -> None:
    def set_(**kw):
        with _LOCK:
            job.update(kw)
    try:
        files, total = scan(root)
        set_(total=files, status="pack")
        need_space(Path(job["path"]).parent, total)   # deflate never makes the file bigger than the raw data
        export_zip(root, job["path"], app_version, progress=lambda n: set_(done=n))
        set_(status="done", done=files, finished=time.time())
    except TooBig:
        set_(status="error", error=too_many_text(), finished=time.time())
    except NoSpace as e:
        set_(status="error", error=no_space_text(e), finished=time.time())
    except Exception as e:  # noqa: BLE001
        set_(status="error", error=localefmt.chu(f"Nén thất bại: {e}", f"Compression failed: {e}"), finished=time.time())
    if job["status"] == "error":
        try:
            os.unlink(job["path"])
        except OSError:
            pass


def export_start(root, out_dir, name: str, app_version: str = "") -> dict:
    """Start packing `root` in a background thread (or join the run already packing it). Returns the job's view."""
    root = Path(root)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _sweep_exports(out)
    with _LOCK:
        for j in _JOBS.values():
            if j["root"] == str(root) and j["status"] in ("scan", "pack"):
                return _view(j)
        jid = uuid.uuid4().hex
        job = {"id": jid, "root": str(root), "name": name, "status": "scan", "done": 0, "total": 0, "error": "",
               "path": str(out / (jid + ".zip")), "started": time.time()}
        _JOBS[jid] = job
    threading.Thread(target=_run_export, args=(job, root, app_version), name="brain-export", daemon=True).start()
    return _view(job)


def _view(j: dict) -> dict:
    return {"id": j["id"], "status": j["status"], "done": j["done"], "total": j["total"], "error": j["error"],
            "name": j["name"]}


def export_status(jid: str) -> Optional[dict]:
    with _LOCK:
        j = _JOBS.get(jid) if _ID.match(str(jid or "")) else None
        return _view(j) if j else None


def export_file(jid: str) -> Optional[tuple]:
    """(path, download name) of a finished export, or None."""
    with _LOCK:
        j = _JOBS.get(jid) if _ID.match(str(jid or "")) else None
        if not j or j["status"] != "done" or not os.path.isfile(j["path"]):
            return None
        return j["path"], j["name"]


# ---- upload in pieces: start, send each piece, finish ----

class Offset(Exception):
    """A piece arrived for another place in the file than where the server stands. Carries where it stands."""

    def __init__(self, received: int):
        super().__init__(str(received))
        self.received = received


def _part(work: Path, uid: str) -> tuple:
    if not _ID.match(str(uid or "")):
        raise BadFile("bad id")
    return work / (uid + ".part"), work / (uid + ".json")


def sweep_uploads(work, older_than_s: int = 86400) -> None:
    """Remove pieces of uploads nobody finished, and import folders a crash left behind."""
    now = time.time()
    try:
        for p in Path(work).iterdir():
            try:
                if now - p.stat().st_mtime <= older_than_s:
                    continue
                if p.is_dir() and p.name.startswith(IMPORT_PREFIX):
                    shutil.rmtree(p, ignore_errors=True)
                elif p.suffix in (".part", ".json"):
                    p.unlink()
            except OSError:
                pass
    except OSError:
        pass


def upload_start(work, size: int, filename: str = "") -> dict:
    """Open an upload of `size` bytes. The disk must hold the file and, later, about as much again unpacked."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    sweep_uploads(work)
    size = int(size or 0)
    if size <= 0:
        raise BadFile("empty")
    need_space(work, size * 2)
    uid = uuid.uuid4().hex
    part, meta = _part(work, uid)
    part.write_bytes(b"")
    meta.write_text(json.dumps({"size": size, "filename": str(filename or "")[:200], "started": time.time()}),
                    encoding="utf-8")
    return {"id": uid, "chunk": CHUNK}


def upload_chunk(work, uid: str, offset: int, data: bytes) -> int:
    """Append one piece at `offset`. Returns the bytes received so far. Raises Offset when `offset` is not where the
    file stands (the client then resends from there), BadFile for an unknown upload or a piece too big."""
    part, meta = _part(Path(work), uid)
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
        have = part.stat().st_size
    except (OSError, ValueError):
        raise BadFile("unknown upload")
    if int(offset) != have:
        raise Offset(have)
    if len(data) > CHUNK or have + len(data) > int(m.get("size") or 0):
        raise BadFile("piece too big")
    with open(part, "ab") as f:
        f.write(data)
    return have + len(data)


def bad_file_text() -> str:
    return localefmt.chu("File này không phải bộ não Javis xuất ra (cần file .zip có ghi chú bên trong).",
                         "This is not a brain file exported by Javis (a .zip with notes inside).")


_IMPORTS: dict = {}


def upload_finish(work, uid: str, brains_dir, label: str = "", after=None) -> dict:
    """Unpack a complete upload into a new brain, in a background thread (a big brain takes longer than a proxy waits
    for a reply). `after(result)` runs in that thread once the brain is in place. Poll with import_status(uid).
    Raises Offset while pieces are missing (nothing is dropped then, so the client can resume)."""
    work = Path(work)
    part, meta = _part(work, uid)
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
        have = part.stat().st_size
    except (OSError, ValueError):
        raise BadFile("unknown upload")
    if have != int(m.get("size") or 0):
        raise Offset(have)
    with _LOCK:
        if uid in _IMPORTS:
            return dict(_IMPORTS[uid])
        job = {"status": "unpack", "error": "", "result": None}
        _IMPORTS[uid] = job

    def run():
        res, err = None, ""
        try:
            with open(part, "rb") as f:
                res = import_zip(f, brains_dir, m.get("filename") or "", label, work)
            if after:
                try:
                    after(res)
                except Exception:  # noqa: BLE001 - the brain is in place; a later scaffold step is not fatal
                    pass
        except TooBig:
            err = too_many_text()
        except NoSpace as e:
            err = no_space_text(e)
        except BadFile:
            err = bad_file_text()
        except Exception as e:  # noqa: BLE001
            err = localefmt.chu(f"Không nhập được: {e}", f"Could not import: {e}")
        finally:
            for p in (part, meta):
                try:
                    p.unlink()
                except OSError:
                    pass
        with _LOCK:
            job.update(status="error" if err else "done", error=err, result=res, finished=time.time())
            for k, j in list(_IMPORTS.items()):   # forget answers nobody came back for
                if j.get("finished") and time.time() - j["finished"] > _DONE_KEEP_S:
                    _IMPORTS.pop(k, None)

    threading.Thread(target=run, name="brain-import", daemon=True).start()
    return dict(job)


def import_status(uid: str) -> Optional[dict]:
    with _LOCK:
        j = _IMPORTS.get(uid) if _ID.match(str(uid or "")) else None
        return dict(j) if j else None
