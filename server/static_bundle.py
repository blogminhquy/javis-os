"""One bundle for the dashboard's startup scripts, built when the page is served (2026-11-09).

WHY
index.html loads about 110 classic scripts before the app can draw anything. Measured on 2026-11-09 with the page set to
the Partners page: 1.3 MB in all, so bandwidth is not the cost, but every file is one request. Over plain HTTP/1.1 (Javis
reached at http://<vps-ip>:7777) the browser opens 6 connections per host, so 110 files queue in about 19 rounds, and
each request also walks the server's whole Python middleware stack. With 150 ms to the VPS the list showed after 4.7 s;
the same files as one bundle: 1.7 s (60 ms: 2.1 s down to 0.95 s), with no page error.

WHAT
`apply(html, dashboard_dir)` takes the page as root() is about to send it (every `?v=` already the file's crc) and
replaces each run of consecutive plain `<script src="/static/x.js?v=crc"></script>` tags with ONE tag for a bundle served
at /static/_bundle/<id>.js, placed where the LAST tag of the run stood. The source tree does not change: files stay
separate for reading and editing, and tests that read index.html keep working.

RULES THAT KEEP THE OLD BEHAVIOUR
- A run is broken by any script that executes in place (inline code, a script with other attributes such as `id` or
  `type="module"`). JSON data blocks and `defer` scripts do not break it: they do not run where they stand.
- Files keep their order. Moving a script later in the page only means more of the page exists when it runs.
- Error isolation, which separate files gave for free: the bundle counts each file it finishes
  (`window.__javisBundle[id] = n`) and a small inline script right after it loads, one by one in order, every file the
  bundle did not finish: after a file that threw, the ones after it; after a syntax error, a missing bundle or a network
  failure, all of them. So one broken file still costs only itself, as before.
- The first statement of the bundle is that counter, so a file's leading "use strict" can never turn the whole bundle
  strict.
- Line numbers: the minifier keeps every file's line count, and the bundle starts with a table of where each file
  begins (`window.__javisBundleMap`); loi-may-khach.js uses it to report errors against the original file and line.
- freshness.js checks what the browser runs against the server: bundled files are replaced in `javis-fresh` by the
  bundle itself (`_bundle/<id>.js`), fetched from cache under the same URL the page used.

Switch off with JAVIS_BUNDLE=0 (the page then loads every file separately, exactly as before).
"""
from __future__ import annotations

import gzip
import json
import os
import re
import threading
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tinh_gon

PREFIX = "_bundle/"
MAX_KEPT = 8                     # bundles kept in memory (an update makes a new one; old tabs may still ask once)

_TOKEN = re.compile(r"<!--[\s\S]*?-->|<script\b([^>]*)>([\s\S]*?)</script>", re.I)
_PLAIN_SRC = re.compile(r'\s*src="/static/([\w./-]+\.js)\?v=([\w.]+)"\s*', re.I)
_TYPE = re.compile(r'\btype\s*=\s*"([^"]*)"', re.I)

_bundles: Dict[str, Tuple[bytes, bytes, str]] = {}   # file name -> (bytes, gzip, crc)
_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("JAVIS_BUNDLE", "1").strip().lower() not in ("0", "false", "no", "off")


def _is_data_block(attrs: str) -> bool:
    m = _TYPE.search(attrs or "")
    if not m:
        return False
    t = m.group(1).strip().lower()
    return t not in ("", "text/javascript", "application/javascript", "module")


def _runs_in_place(attrs: str, body: str) -> bool:
    """Does this <script> execute where it stands (so it must keep its order against the bundled files)?"""
    if _is_data_block(attrs):
        return False
    a = (attrs or "").lower()
    if re.search(r"\bsrc\s*=", a) and re.search(r"\b(defer|async)\b", a) and not body.strip():
        return False
    return True


def find_runs(html: str) -> List[List[Tuple[int, int, str, str]]]:
    """Runs of bundleable tags: lists of (start, end, rel, crc), in page order, two or more tags each."""
    runs, cur = [], []
    for m in _TOKEN.finditer(html):
        if m.group(0).startswith("<!--"):
            continue
        attrs, body = m.group(1) or "", m.group(2) or ""
        pm = _PLAIN_SRC.fullmatch(attrs)
        if pm and not body.strip():
            cur.append((m.start(), m.end(), pm.group(1), pm.group(2)))
            continue
        if _runs_in_place(attrs, body):
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def _line_count(data: bytes) -> int:
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def build(files: List[Tuple[str, bytes]]) -> Tuple[bytes, str, str, List[list]]:
    """The bundle for [(rel, served bytes)]: (bytes, crc, id, [[first line, rel], ...]). `id` names the run in the
    counter and the line table; it depends on the files only."""
    ident = format(zlib.crc32(b"\0".join(r.encode() + b"\1" + d for r, d in files)) & 0xFFFFFFFF, "08x")
    # Line 1: the counter and the line table. Each file then starts on its own line and is followed by one line that
    # bumps the counter, so a file's line k sits at bundle line start + k - 1.
    table: List[list] = []
    parts: List[bytes] = []
    line = 2
    for i, (rel, data) in enumerate(files):
        table.append([line, rel])
        body = data if data.endswith(b"\n") else data + b"\n"
        parts.append(body)
        parts.append(f';window.__javisBundle["{ident}"]={i + 1};\n'.encode())
        line += _line_count(data) + 1
    head = ('window.__javisBundle=window.__javisBundle||{};window.__javisBundle["%s"]=0;'
            'window.__javisBundleMap=window.__javisBundleMap||{};window.__javisBundleMap["%s"]=%s;\n'
            % (ident, ident, json.dumps(table, ensure_ascii=False, separators=(",", ":")))).encode()
    data = head + b"".join(parts)
    crc = format(zlib.crc32(data) & 0xFFFFFFFF, "08x")
    return data, crc, ident, table


def _fallback(ident: str, urls: List[str]) -> str:
    """Inline script after the bundle tag: load, in order, every file the bundle did not finish (see module doc)."""
    return ('<script>(function(i,L){var d=(window.__javisBundle||{})[i];if(d===L.length)return;'
            'for(var k=(typeof d==="number"?d+1:0);k<L.length;k++)'
            'document.write(\'<script src="\'+L[k]+\'"><\\/script>\');})(%s,%s);</script>'
            % (json.dumps(ident), json.dumps(urls)))


def apply(html: str, dashboard_dir: Path) -> Tuple[str, Dict[str, str]]:
    """(page with each run replaced by one bundle tag, {bundled rel: None, bundle rel: crc}) for javis-fresh.

    The second value tells root() how to fix the `javis-fresh` asset list: bundled files drop out (value None) and the
    bundle comes in. Any problem (a file missing, a read error) leaves that run as separate tags."""
    if not enabled():
        return html, {}
    runs = find_runs(html)
    if not runs:
        return html, {}
    fresh: Dict[str, Optional[str]] = {}
    out, pos = [], 0
    for run in runs:
        files = []
        try:
            for _s, _e, rel, crc in run:
                data, real = tinh_gon.ban_phuc_vu(dashboard_dir / rel, rel)
                if real != crc:          # the file changed between fingerprint and now: keep this run as it is
                    raise ValueError(rel)
                files.append((rel, data))
        except (OSError, ValueError):
            continue
        data, crc, ident, _table = build(files)
        name = ident + ".js"     # loi-may-khach.js finds the line table by this name
        with _lock:
            if name not in _bundles:
                if len(_bundles) >= MAX_KEPT:
                    _bundles.pop(next(iter(_bundles)))
                _bundles[name] = (data, gzip.compress(data, tinh_gon.GZIP_LEVEL, mtime=0), crc)
        urls = ["/static/%s?v=%s" % (rel, c) for _s, _e, rel, c in run]
        tag = '<script src="/static/%s%s?v=%s"></script>%s' % (PREFIX, name, crc, _fallback(ident, urls))
        for i, (s, e, rel, _c) in enumerate(run):
            out.append(html[pos:s])
            if i == len(run) - 1:
                out.append(tag)
            pos = e
            fresh[rel] = None
        fresh[PREFIX + name] = crc
    out.append(html[pos:])
    return "".join(out), fresh


def get(rel: str) -> Optional[Tuple[bytes, bytes, str]]:
    """(bytes, gzip, crc) of a bundle by its path under /static/ (`_bundle/<id>.js`), or None."""
    if not rel.startswith(PREFIX):
        return None
    with _lock:
        return _bundles.get(rel[len(PREFIX):])


def warm(dashboard_dir: Path) -> dict:
    """Minify and gzip every dashboard script and style once, so the first page after a restart or an update finds them
    ready; then drop cached outputs of files that no longer exist. Runs on a worker thread at startup; main.py then
    renders the page once so the bundle is ready too."""
    n = 0
    for f in sorted(dashboard_dir.rglob("*")):
        try:
            rel = f.relative_to(dashboard_dir).as_posix()
            if not f.is_file() or not (rel.endswith(".js") or rel.endswith(".css")):
                continue
            if any(p.startswith(".") or p == "node_modules" for p in rel.split("/")):
                continue
            tinh_gon.gzip_of(f, rel)
            n += 1
        except OSError:
            continue
    pruned = tinh_gon.prune_disk_cache()
    return {"files": n, "pruned": pruned}
