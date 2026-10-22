"""Integrity check for the npx cache folder behind an `npx -y <package>` MCP connector.

The first time npx runs a package it installs it into `<npm cache>/_npx/<hash>/`, and every later
run reuses that folder without checking it. When that first install is cut short (the process tree
killed in the middle of the download, the container stopped, the disk full), the folder keeps
package directories that have no package.json. npx still finds the connector's own package.json,
treats the folder as installed and runs it, and Node then fails with MODULE_NOT_FOUND on every
start. Pressing Check only respawns npx, which reuses the same broken folder.

Seen on a VPS 2026-10-13 to 2026-10-16: `mcp-server-gsc` had `node_modules/ajv` and
`node_modules/hono` without package.json after the hub killed npx during its first install.

`prepare()` runs before a stdio session spawns its process. It finds the folder npx is going to
use and, when that folder is a broken install that nobody is writing to, moves it out of the way
so npx installs the package again. It never touches a folder that looks healthy, a folder another
session in this server is starting from, or a folder that was written to in the last minutes.

Known limits, all of which fail safe (the folder then reads as absent or healthy and is never
repaired by mistake): the npm cache location comes from `npm_config_cache`, `--cache` and the
`cache=` line of ~/.npmrc only, and a package cut off after all of its own files were written
passes the check.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

NPX_NAMES = {"npx", "npx.cmd", "npx.exe", "npx.ps1"}

# npx flags that take no value. Anything else that starts with "-" and is not of the form
# --key=value makes the parser give up: guessing which argument is the package would point the
# check at the wrong folder.
_FLAGS_NO_VALUE = {"-y", "--yes", "-q", "--quiet", "-s", "--silent", "--no", "-n",
                   "--prefer-offline", "--prefer-online", "--offline", "--no-update-notifier",
                   "--ignore-scripts", "--no-audit", "--no-fund"}

# A folder whose newest entry is younger than this may still be mid-install by a process this
# server does not know about (a second Javis, a terminal). Leave it alone.
QUIET_SECONDS = 120

# Folders that sessions of this server are currently starting from, with a count: two
# connections can run the same package (see claim/release).
_starting: dict[str, int] = {}
_starting_lock = threading.Lock()


def package_specs(command: str, args) -> tuple[list[str], str | None] | None:
    """(package specs, cache override) for an npx command line, or None when it is not npx or
    when the line cannot be read with certainty."""
    if Path(str(command or "")).name.lower() not in NPX_NAMES:
        return None
    packages: list[str] = []
    cache = None
    first_positional = None
    items = [str(a) for a in (args or [])]
    i = 0
    while i < len(items):
        a = items[i]
        if a == "--":
            if i + 1 < len(items):
                first_positional = items[i + 1]
            break
        if a in ("-p", "--package"):
            if i + 1 >= len(items):
                return None
            packages.append(items[i + 1])
            i += 2
            continue
        if a.startswith("--package="):
            packages.append(a.split("=", 1)[1])
            i += 1
            continue
        if a == "--cache":
            if i + 1 >= len(items):
                return None
            cache = items[i + 1]
            i += 2
            continue
        if a.startswith("--cache="):
            cache = a.split("=", 1)[1]
            i += 1
            continue
        if a in ("-c", "--call") or a.startswith("--call="):
            return None
        if a.startswith("-"):
            if a in _FLAGS_NO_VALUE or (a.startswith("--") and "=" in a):
                i += 1
                continue
            return None
        first_positional = a
        break
    if not packages:
        if not first_positional:
            return None
        packages = [first_positional]
    for p in packages:
        # npm hashes a local directory spec by its resolved absolute path; not worth mirroring.
        if p.startswith((".", "/", "~", "file:")) or "\\" in p or (len(p) > 1 and p[1] == ":"):
            return None
    return packages, cache


def _npmrc_cache(home: str) -> str | None:
    try:
        for line in Path(home, ".npmrc").read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip().lower() == "cache" and value.strip():
                return value.strip()
    except OSError:
        return None
    return None


def npx_root(env: dict | None = None, cache_override: str | None = None) -> Path | None:
    """`<npm cache>/_npx` for the given environment (the one the process will be started with)."""
    env = dict(env if env is not None else os.environ)
    low = {k.lower(): v for k, v in env.items()}
    cache = cache_override or low.get("npm_config_cache")
    home = env.get("HOME") or env.get("USERPROFILE") or os.path.expanduser("~")
    if not cache and home:
        cache = _npmrc_cache(home)
    if not cache:
        if os.name == "nt":
            base = env.get("LOCALAPPDATA") or (os.path.join(home, "AppData", "Local") if home else "")
            cache = os.path.join(base, "npm-cache") if base else ""
        else:
            cache = os.path.join(home, ".npm") if home else ""
    if not cache:
        return None
    return Path(os.path.expanduser(cache)) / "_npx"


def _hash(packages: list[str]) -> str:
    return hashlib.sha512("\n".join(packages).encode("utf-8")).hexdigest()[:16]


def install_dir(packages: list[str], root: Path) -> Path:
    """The folder npx uses: sha512 of the sorted specs joined by newlines, first 16 hex chars
    (libnpmexec). npm sorts with `localeCompare(b, 'en')`; for several packages try the two
    orders that collation can produce for plain package names and keep the one that exists."""
    if len(packages) == 1:
        return root / _hash(packages)
    candidates = [sorted(packages), sorted(packages, key=lambda s: (s.lower(), s))]
    for order in candidates:
        d = root / _hash(order)
        if d.exists():
            return d
    return root / _hash(candidates[0])


def _package_dirs(node_modules: Path):
    # Symlinked entries are skipped: npx installs real folders, and a link back up the tree
    # (a cycle) would make this walk recurse until the path is too long.
    try:
        names = sorted(os.listdir(node_modules))
    except OSError:
        return
    for name in names:
        if name.startswith("."):
            continue
        p = node_modules / name
        if p.is_symlink():
            continue
        if name.startswith("@"):
            try:
                subs = sorted(os.listdir(p))
            except OSError:
                continue
            for sub in subs:
                q = p / sub
                if q.is_dir() and not q.is_symlink():
                    yield q
                    yield from _package_dirs(q / "node_modules")
        elif p.is_dir() and not p.is_symlink():
            yield p
            yield from _package_dirs(p / "node_modules")


def _resolve(root: Path, start: Path, dep: str) -> Path | None:
    cur = start
    while True:
        cand = cur / "node_modules" / dep
        if cand.is_dir():
            return cand
        if cur == root or root not in cur.parents:
            return None
        cur = cur.parent
        # Step out of "node_modules/<pkg>" (and "@scope") back to the folder that holds them.
        while cur.name == "node_modules" or cur.name.startswith("@"):
            if cur == root:
                break
            cur = cur.parent


def inspect_tree(folder: Path, limit: int = 20) -> list[str]:
    """Problems that npx will not repair by itself: package folders without package.json, and
    declared dependencies that do not resolve. Empty list = healthy (or nothing installed yet)."""
    nm = folder / "node_modules"
    if not nm.is_dir():
        return []
    problems: list[str] = []
    for pkg in _package_dirs(nm):
        pj = pkg / "package.json"
        rel = pkg.relative_to(folder).as_posix()
        if not pj.is_file():
            problems.append(f"{rel}: no package.json")
        else:
            try:
                meta = json.loads(pj.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                problems.append(f"{rel}: unreadable package.json")
                meta = None
            if isinstance(meta, dict):
                optional = set((meta.get("optionalDependencies") or {}).keys())
                for dep in (meta.get("dependencies") or {}):
                    if dep in optional:
                        continue
                    target = _resolve(folder, pkg, dep)
                    if target is None:
                        problems.append(f"{rel}: dependency {dep} missing")
                    elif not (target / "package.json").is_file():
                        problems.append(f"{rel}: dependency {dep} has no package.json")
        if len(problems) >= limit:
            break
    return problems


def _newest_mtime(folder: Path, limit: int = 20000) -> float:
    """Newest mtime among the folder's directories and its two top files. Extracting a package
    adds entries to the directories it writes into, so directory mtimes show recent writes
    without a stat on every file. Bounded: a huge tree only gets its first `limit` directories."""
    newest = 0.0
    for p in (folder / "package.json", folder / "package-lock.json"):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    seen = 0
    for dp, dns, _ in os.walk(folder, followlinks=False):
        try:
            newest = max(newest, os.stat(dp).st_mtime)
        except OSError:
            pass
        seen += 1
        if seen >= limit:
            break
    return newest


def claim(folder: str | None) -> None:
    """A session of this server is starting from `folder`: never move it meanwhile."""
    if folder:
        with _starting_lock:
            _starting[folder] = _starting.get(folder, 0) + 1


def release(folder: str | None) -> None:
    if folder:
        with _starting_lock:
            n = _starting.get(folder, 0) - 1
            if n > 0:
                _starting[folder] = n
            else:
                _starting.pop(folder, None)


def _remove_old_broken(root: Path, older_than: float = 3600) -> None:
    """Delete `<hash>.broken-<ts>` folders a previous repair could not finish deleting (a file
    lock on Windows). Best effort."""
    try:
        names = os.listdir(root)
    except OSError:
        return
    now = time.time()
    for name in names:
        head, sep, ts = name.partition(".broken-")
        if sep and len(head) == 16 and ts.isdigit() and now - int(ts) > older_than:
            shutil.rmtree(root / name, ignore_errors=True)


def prepare(command: str, args, env: dict | None = None, quiet_seconds: float = QUIET_SECONDS) -> dict:
    """Check the npx folder this command will use; move it aside when it is a broken install.

    Returns {"state": ..., "dir": ..., "problems": [...]} where state is:
      skipped  - not an npx command line (or one this parser does not read with certainty)
      absent   - nothing installed yet: npx will download the package (a cold start)
      ok       - installed and complete
      busy     - broken, but someone may be writing to it right now; left alone
      repaired - broken; moved aside so npx installs it again (also a cold start)
      error    - broken, but moving it failed (permissions); left alone
    """
    parsed = package_specs(command, args)
    if not parsed:
        return {"state": "skipped"}
    packages, cache = parsed
    root = npx_root(env, cache)
    if root is None:
        return {"state": "skipped"}
    folder = install_dir(packages, root)
    out = {"dir": str(folder)}
    if not folder.exists():
        return {**out, "state": "absent"}
    problems = inspect_tree(folder)
    if not problems:
        return {**out, "state": "ok"}
    out["problems"] = problems[:5]
    with _starting_lock:
        in_use = str(folder) in _starting
    if in_use or time.time() - _newest_mtime(folder) < quiet_seconds:
        return {**out, "state": "busy"}
    aside = folder.with_name(f"{folder.name}.broken-{int(time.time())}")
    try:
        os.replace(folder, aside)
    except OSError as e:
        return {**out, "state": "error", "error": f"{type(e).__name__}: {e}"}
    shutil.rmtree(aside, ignore_errors=True)
    _remove_old_broken(root)
    print(f"[npx cache] {folder.name}: broken install moved aside ({'; '.join(problems[:3])}),"
          " npx will install it again", file=sys.stderr)
    return {**out, "state": "repaired"}
