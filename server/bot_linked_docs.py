"""Google Docs and Google Sheets linked from a dedicated bot's Agent, read as bot documents (0.84.10).

Why. An owner attaches "Bảng giá" as a Google Sheets link on the Agent (or pastes the link into the
Agent text) and expects the bot to answer from it. Before this module the bot only searched `.md` and
`.txt` files on disk (`chatbot_grounding`), so the link was invisible: a bot told "answer only from the
documents" said "chưa có thông tin" about every product in the sheet.

How, and why this way rather than through an MCP connector:

1. **Only links the OWNER wrote.** URLs come from the Agent file (its `assets.links` plus links in its
   text), never from a customer message. A customer pasting a link gets nothing fetched.
2. **Only Google's public export endpoint, rebuilt from the document id.** The owner's URL is parsed
   for a document id and Javis requests `docs.google.com/<kind>/d/<id>/export?...` itself, so the URL
   cannot steer the request anywhere else. This needs the document shared as "Anyone with the link can
   view"; a private one comes back as a Google sign-in page, which is reported to the owner as exactly
   that, so the fix is one click in Google, not a guess.
3. **No connector, no extra permission level.** Fetching happens in Javis' own code before the turn,
   like the keyword search, so it works at every bot level including the default read-only one, on
   every engine, on every fork. Going through a hub connector would hand a stranger-steered turn a
   live data source, which is what the "read_docs" level was built to avoid.
4. **Cached, stale-while-revalidate.** A fresh copy is reused for `FRESH_S`; after that the old copy
   still answers while one background thread refreshes it, so a busy bot does not wait on Google every
   few minutes. Only the very first read of a link blocks a turn.

The documents go into the same keyword index as the brain's files (see `chatbot_grounding.thu_thap`'s
`extra`), cut by headings for Docs and by sheet tab for Sheets, one row per line with its column names
so a chunk stands on its own.
"""
from __future__ import annotations

import concurrent.futures
import io
import re
import sys
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import agent_assets
from localefmt import chu

FRESH_S = 300               # a fetched copy is reused this long without asking Google again
RETRY_ERR_S = 60            # a link that failed is retried at most this often
KEEP_STALE_S = 24 * 3600    # an old copy keeps answering this long while Google is unreachable
TIMEOUT_S = 12.0
MAX_LINKS = 10              # per Agent, so one Agent cannot make every turn fetch dozens of files
MAX_DOWNLOAD = 8_000_000    # bytes of one export
MAX_XML = 40_000_000        # bytes of an ODS content.xml once unzipped (zip bomb guard)
MAX_TEXT = 120_000          # characters kept per document, same cap as a brain file
MAX_ROWS = 3_000            # rows read per sheet tab
MAX_CELL = 2_000            # characters kept per sheet cell

_ID = r"([A-Za-z0-9_-]{20,})"
_DOC_RE = re.compile(r"^https?://docs\.google\.com/document/(?:u/\d+/)?d/" + _ID, re.I)
_SHEET_RE = re.compile(r"^https?://docs\.google\.com/spreadsheets/(?:u/\d+/)?d/" + _ID, re.I)
_GID_RE = re.compile(r"[#?&]gid=(\d+)")
_GOOGLE_HOST_RE = re.compile(r"^https?://(?:docs|drive)\.google\.com/", re.I)
_URL_IN_TEXT_RE = re.compile(r"https?://(?:docs|drive)\.google\.com/[^\s<>\"')\]]+", re.I)

_NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_T = "{%s}" % _NS["table"]
_TX = "{%s}" % _NS["text"]


_TRANSPORT = None            # tests swap in an httpx.MockTransport; None = the real network


class LinkError(Exception):
    """A link that could not be read, with a message the owner can act on."""


# ============================================================
# Which links
# ============================================================
def parse(url: str) -> Optional[dict]:
    """{"kind": "doc"|"sheet", "id", "gid"} for a Google Docs/Sheets URL, else None.

    Published-to-web links (`/d/e/2PACX.../pub`) are not parsed: their id is not the document id, so
    they are reported as unsupported rather than fetched wrong."""
    u = str(url or "").strip()
    if "/d/e/" in u:
        return None
    m = _DOC_RE.match(u)
    if m:
        return {"kind": "doc", "id": m.group(1), "gid": ""}
    m = _SHEET_RE.match(u)
    if m:
        g = _GID_RE.search(u)
        return {"kind": "sheet", "id": m.group(1), "gid": g.group(1) if g else ""}
    return None


def is_google(url: str) -> bool:
    return bool(_GOOGLE_HOST_RE.match(str(url or "").strip()))


def links_of_agent(meta: Optional[dict], body: str = "") -> List[dict]:
    """Google links the owner attached to the Agent, then Google links written in its text.

    Returns [{"url", "label"}], deduplicated by document, at most `MAX_LINKS`. Non-Google links are left
    out: they are web pages, not documents this module can read."""
    out: List[dict] = []
    seen = set()

    def add(url: str, label: str) -> None:
        url = str(url or "").strip().rstrip(".,;:")
        if not is_google(url):
            return
        p = parse(url)
        key = (p["kind"], p["id"], p["gid"]) if p else url
        if key in seen:
            return
        seen.add(key)
        out.append({"url": url, "label": str(label or "").strip()})

    try:
        for link in agent_assets.doc(meta or {}).get("links") or []:
            add(link.get("url"), link.get("label"))
    except Exception as e:      # noqa: BLE001 - a hand-broken frontmatter must not stop the bot
        print(f"[bot linked docs] reading Agent links failed: {type(e).__name__}: {e}", file=sys.stderr)
    for m in _URL_IN_TEXT_RE.finditer(str(body or "")):
        add(m.group(0), "")
    return out[:MAX_LINKS]


# ============================================================
# Fetch and convert
# ============================================================
def _export_url(p: dict, fmt: str) -> str:
    base = "spreadsheets" if p["kind"] == "sheet" else "document"
    url = f"https://docs.google.com/{base}/d/{p['id']}/export?format={fmt}"
    if p.get("gid") and fmt == "csv":
        url += f"&gid={p['gid']}"
    return url


def _get(url: str) -> Tuple[bytes, str]:
    """(content, content-type) of a public export, or LinkError saying why not."""
    import httpx
    try:
        with httpx.Client(follow_redirects=True, timeout=TIMEOUT_S, transport=_TRANSPORT) as c:
            with c.stream("GET", url) as r:
                host = (r.url.host or "").lower()
                ctype = (r.headers.get("content-type") or "").lower()
                # A private file redirects to the sign-in page (200 HTML on accounts.google.com) or
                # answers 401/403. Both mean the same thing for the owner: share it publicly.
                if host.startswith("accounts.google.") or (r.status_code == 200 and "text/html" in ctype):
                    raise LinkError(chu(
                        "chưa chia sẻ công khai: mở file trên Google, bấm Chia sẻ, chọn 'Bất kỳ ai có "
                        "đường liên kết' ở quyền Người xem",
                        "is not shared publicly: open it on Google, click Share, choose 'Anyone with the "
                        "link' as Viewer"))
                # Shared, but the owner turned off "viewers can download, print and copy": export is refused.
                if r.status_code in (401, 403):
                    raise LinkError(chu(
                        "bị Google từ chối cho tải: kiểm tra file đã chia sẻ 'Bất kỳ ai có đường liên kết' "
                        "và chưa tắt quyền tải xuống, in, sao chép của Người xem",
                        "was refused by Google: check it is shared with 'Anyone with the link' and that "
                        "downloading, printing and copying are not turned off for viewers"))
                if r.status_code == 404:
                    raise LinkError(chu("không có trên Google (link sai hoặc file đã bị xoá)",
                                        "was not found on Google (wrong link or deleted file)"))
                if r.status_code != 200:
                    raise LinkError(chu("lỗi: Google trả mã {n}", "failed: Google returned {n}",
                                        n=r.status_code))
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_DOWNLOAD:
                        raise LinkError(chu("quá lớn (hơn {n} MB)", "is too large (over {n} MB)",
                                            n=MAX_DOWNLOAD // 1_000_000))
                return bytes(buf), ctype
    except LinkError:
        raise
    except Exception as e:      # noqa: BLE001 - network errors of every kind become one owner message
        raise LinkError(chu("không tải được ({n})", "could not be downloaded ({n})",
                            n=type(e).__name__)) from e


def _clean_markdown(text: str) -> str:
    """Google's Markdown export inlines images as base64 at the bottom. Those are megabytes of noise
    for a keyword index, so the image definitions and any data URI go."""
    text = text.lstrip("﻿")
    text = re.sub(r"^\[[^\]]+\]:\s*<?data:[^\n]*$", "", text, flags=re.M)
    text = re.sub(r"!\[[^\]]*\]\[[^\]]*\]", "", text)
    text = re.sub(r"data:[a-z]+/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _cell_text(cell: ET.Element) -> str:
    parts = []
    for p in cell.iter(_TX + "p"):
        parts.append("".join(p.itertext()))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:MAX_CELL]


def _ods_tables(data: bytes) -> Tuple[str, List[Tuple[str, List[List[str]]]]]:
    """(spreadsheet title, [(tab name, rows)]) from an ODS export, every tab, empty rows dropped."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        info = z.getinfo("content.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise LinkError(chu("bị Google trả về bản bảng tính hỏng",
                            "came back from Google as a broken spreadsheet")) from e
    if info.file_size > MAX_XML:
        raise LinkError(chu("là bảng tính quá lớn để đọc", "is a spreadsheet too large to read"))
    title = ""
    try:
        meta = ET.fromstring(z.read("meta.xml"))
        t = meta.find(".//dc:title", _NS)
        title = (t.text or "").strip() if t is not None else ""
    except Exception:       # noqa: BLE001 - the title is a nicety
        pass
    root = ET.fromstring(z.read("content.xml"))
    tabs = []
    for table in root.iter(_T + "table"):
        name = table.get(_T + "name") or ""
        rows: List[List[str]] = []
        for row in table.iter(_T + "table-row"):
            if len(rows) >= MAX_ROWS:
                break
            cells: List[str] = []
            for cell in row:
                if cell.tag not in (_T + "table-cell", _T + "covered-table-cell"):
                    continue
                txt = _cell_text(cell)
                rep = int(cell.get(_T + "number-columns-repeated") or 1)
                # Empty trailing cells come as one cell repeated a thousand times: never expand those.
                cells.extend([txt] * (min(rep, 50) if txt else min(rep, 200)))
            while cells and not cells[-1]:
                cells.pop()
            if not any(cells):
                continue
            rep_rows = int(row.get(_T + "number-rows-repeated") or 1)
            for _ in range(min(rep_rows, 50)):
                rows.append(cells)
        if rows:
            tabs.append((name, rows))
    return title, tabs


def _csv_rows(data: bytes) -> List[List[str]]:
    import csv
    text = data.decode("utf-8", errors="replace").lstrip("﻿")
    rows = []
    for r in csv.reader(io.StringIO(text)):
        r = [re.sub(r"\s+", " ", c).strip()[:MAX_CELL] for c in r]
        while r and not r[-1]:
            r.pop()
        if any(r):
            rows.append(r)
        if len(rows) >= MAX_ROWS:
            break
    return rows


def rows_to_markdown(tab: str, rows: List[List[str]]) -> str:
    """One heading per tab, then one line per row carrying its column names ("Giá: 120.000").

    Column names ride on every row because the index cuts long tabs into chunks: a chunk that starts at
    row 200 must still say which number is the price."""
    if not rows:
        return ""
    head = rows[0]
    lines = [f"## {tab}" if tab else "## Bảng"]
    if len(rows) == 1:
        lines.append("- " + " | ".join(c for c in head if c))
        return "\n".join(lines)
    for r in rows[1:]:
        parts = []
        for i, v in enumerate(r):
            if not v:
                continue
            k = head[i] if i < len(head) and head[i] else ""
            parts.append(f"{k}: {v}" if k else v)
        if parts:
            lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


def fetch(url: str) -> dict:
    """{"title", "text", "kind"} of one link, or LinkError. Blocking: call it from a thread."""
    p = parse(url)
    if not p:
        raise LinkError(chu(
            "chưa đọc được: Javis mới đọc link Google Docs và Google Sheets dạng docs.google.com/.../d/...",
            "cannot be read: Javis reads Google Docs and Google Sheets links of the form "
            "docs.google.com/.../d/..."))
    if p["kind"] == "doc":
        data, _ = _get(_export_url(p, "md"))
        text = _clean_markdown(data.decode("utf-8", errors="replace"))
        first = next((ln.strip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
        return {"kind": "doc", "title": first[:120], "text": text[:MAX_TEXT]}
    # A link that points at one tab (#gid=...) means that tab; otherwise read every tab.
    if p["gid"]:
        data, _ = _get(_export_url(p, "csv"))
        text = rows_to_markdown("", _csv_rows(data))
        return {"kind": "sheet", "title": "", "text": text[:MAX_TEXT]}
    data, _ = _get(_export_url(p, "ods"))
    title, tabs = _ods_tables(data)
    text = "\n\n".join(rows_to_markdown(name, rows) for name, rows in tabs)
    return {"kind": "sheet", "title": title[:120], "text": text[:MAX_TEXT]}


# ============================================================
# Cache
# ============================================================
_lock = threading.Lock()
_CACHE: Dict[str, dict] = {}     # url -> {"doc", "ok_at", "err", "err_at"}
_REFRESHING: set = set()


def _store(url: str, doc: Optional[dict], err: str) -> None:
    now = time.time()
    with _lock:
        c = _CACHE.setdefault(url, {"doc": None, "ok_at": 0.0, "err": "", "err_at": 0.0})
        if doc is not None:
            c.update(doc=doc, ok_at=now, err="", err_at=0.0)
        else:
            c.update(err=err, err_at=now)
        _REFRESHING.discard(url)


def _fetch_into_cache(url: str) -> None:
    try:
        _store(url, fetch(url), "")
    except LinkError as e:
        _store(url, None, str(e))
    except Exception as e:      # noqa: BLE001 - a parser bug must surface as a warning, not a crash
        print(f"[bot linked docs] {url}: {type(e).__name__}: {e}", file=sys.stderr)
        _store(url, None, chu("đọc lỗi ({n})", "failed to read ({n})", n=type(e).__name__))


def _plan(urls: List[str]) -> Tuple[List[str], List[str]]:
    """(urls that must be fetched now because nothing usable is cached, urls to refresh in background)."""
    now = time.time()
    must, background = [], []
    with _lock:
        for u in urls:
            c = _CACHE.get(u)
            if u in _REFRESHING:
                continue
            if not c or (c["doc"] is None and now - c["err_at"] >= RETRY_ERR_S) or (
                    c["doc"] is not None and now - c["ok_at"] >= KEEP_STALE_S):
                must.append(u)
                _REFRESHING.add(u)
            # A copy that failed its last refresh is retried on the error clock, so the owner's warning
            # clears a minute after Google recovers instead of FRESH_S later.
            elif (now - c["err_at"] >= RETRY_ERR_S) if c["err"] else (now - c["ok_at"] >= FRESH_S):
                background.append(u)
                _REFRESHING.add(u)
    return must, background


def collect(links: List[dict]) -> dict:
    """Documents and owner warnings for a bot's linked Google files.

    Returns {"docs": [{"path", "title", "text"}], "warnings": [str]}. `path` is a display name for the
    source line ("Google Sheets: Bảng giá"); it is not a file and the document tools never open it."""
    urls = [l["url"] for l in links if l.get("url")]
    must, background = _plan(urls)
    if must:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(must))) as ex:
            list(ex.map(_fetch_into_cache, must))
    for u in background:
        threading.Thread(target=_fetch_into_cache, args=(u,), daemon=True,
                         name="bot-linked-doc-refresh").start()

    docs, warnings = [], []
    with _lock:
        snapshot = {u: dict(_CACHE.get(u) or {}) for u in urls}
    for link in links:
        url = link.get("url") or ""
        c = snapshot.get(url) or {}
        label = link.get("label") or ""
        doc = c.get("doc")
        if c.get("err"):
            name = label or (doc or {}).get("title") or url
            warnings.append(chu("Link Google '{name}' {err}", "Google link '{name}' {err}",
                                name=name[:80], err=c["err"])
                            + (chu(" (bot đang dùng bản đọc được lần trước)",
                                   " (the bot uses the last copy it read)") if doc else ""))
        if not doc or not (doc.get("text") or "").strip():
            continue
        kind = "Google Sheets" if doc.get("kind") == "sheet" else "Google Docs"
        title = label or doc.get("title") or kind
        docs.append({"path": f"{kind}: {title}", "title": title, "text": doc["text"]})
    return {"docs": docs, "warnings": warnings}


def clear_cache() -> None:
    with _lock:
        _CACHE.clear()
        _REFRESHING.clear()
