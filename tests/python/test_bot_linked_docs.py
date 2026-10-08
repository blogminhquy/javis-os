"""Dedicated bots read the Google Docs/Sheets linked from their Agent (0.84.10).

    python tests/run.py bot_linked_docs      (no network: Google is an httpx.MockTransport)

The bug: an owner attached a Google Sheets price list to the Agent, told the Agent "answer only from the
documents", and the bot answered "chưa có thông tin" about every product, because the pre-turn search
only read `.md`/`.txt` files of the brain. What this file pins down:

1. Which links are read: the owner's (Agent links and Agent text), Google Docs/Sheets only, never a link
   a customer types.
2. What comes back: Docs as Markdown without inline base64 images, Sheets as every tab with column names
   on every row, so a chunk cut in the middle of a long tab still says which number is the price.
3. That a private file is reported to the owner as "not shared publicly" instead of silently answering
   without it, and that an old copy keeps answering while Google is down.
4. That the linked text reaches the bot through the same keyword search as brain files, and that two bots
   on one brain with different Agents never see each other's links.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-bld-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import bot_linked_docs as bld  # noqa: E402
import chatbot_grounding  # noqa: E402
import chatbot_runtime  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


DOC_ID = "1DocAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
SHEET_ID = "1SheetBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
PRIVATE_ID = "1PrivCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
GONE_ID = "1GoneDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
DOC_URL = f"https://docs.google.com/document/d/{DOC_ID}/edit?usp=sharing"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?usp=sharing"
PRIVATE_URL = f"https://docs.google.com/spreadsheets/d/{PRIVATE_ID}/edit"


def _ods(tabs):
    """A minimal ODS file the way Google exports one: trailing empty cells as ONE repeated cell."""
    T = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    X = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    parts = []
    for name, rows in tabs:
        rs = []
        for r in rows:
            cells = "".join(f'<table:table-cell><text:p>{c}</text:p></table:table-cell>' if c else
                            '<table:table-cell/>' for c in r)
            rs.append(f'<table:table-row>{cells}<table:table-cell table:number-columns-repeated="1000"/>'
                      f'</table:table-row>')
        rs.append('<table:table-row table:number-rows-repeated="998">'
                  '<table:table-cell table:number-columns-repeated="1024"/></table:table-row>')
        parts.append(f'<table:table table:name="{name}">' + "".join(rs) + "</table:table>")
    content = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content '
               f'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="{T}" '
               f'xmlns:text="{X}"><office:body><office:spreadsheet>' + "".join(parts) +
               "</office:spreadsheet></office:body></office:document-content>")
    meta = ('<?xml version="1.0" encoding="UTF-8"?><office:document-meta '
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><office:meta><dc:title>Bảng giá shop</dc:title>'
            '</office:meta></office:document-meta>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", content)
        z.writestr("meta.xml", meta)
    return buf.getvalue()


SHEET_ODS = _ods([
    ("Sản phẩm", [["Tên sản phẩm", "Giá", "Tồn kho"],
                  ["Kìm cắt Stanley 8 inch", "185.000đ", "12"],
                  ["Búa đinh Total 500g", "95.000đ", ""],
                  ["Thước cuộn 5m", "45.000đ", "40"]]),
    ("Chính sách", [["Mục", "Nội dung"], ["Bảo hành", "Bảo hành 6 tháng cho dụng cụ điện"]]),
])
DOC_MD = ("﻿# Hướng dẫn tư vấn\n\n## Giờ mở cửa\n\nCửa hàng mở cửa từ 7 giờ sáng tới 9 giờ tối.\n\n"
          "![][image1]\n\n[image1]: <data:image/png;base64," + "A" * 5000 + ">\n")

CALLS = []
STATE = {"down": False}


def _google(request: httpx.Request) -> httpx.Response:
    """Google's export endpoints, the way they behave for public, private and deleted files."""
    CALLS.append(str(request.url))
    if STATE["down"]:
        raise httpx.ConnectError("offline")
    url = str(request.url)
    host = request.url.host
    if host.endswith("googleusercontent.com"):
        if request.url.path == "/doc":
            return httpx.Response(200, headers={"content-type": "text/x-markdown; charset=utf-8"},
                                  content=DOC_MD.encode("utf-8"))
        if request.url.path == "/csv":
            return httpx.Response(200, headers={"content-type": "text/csv; charset=utf-8"},
                                  content="Tên,Giá\nỐc vít M6,2.000đ\n".encode("utf-8"))
        return httpx.Response(200, headers={"content-type": "application/vnd.oasis.opendocument.spreadsheet"},
                              content=SHEET_ODS)
    if host == "accounts.google.com":
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>Sign in</html>")
    if PRIVATE_ID in url:
        return httpx.Response(302, headers={"location": "https://accounts.google.com/ServiceLogin?continue=x"})
    if GONE_ID in url:
        return httpx.Response(404, headers={"content-type": "text/html"}, content=b"<html>404</html>")
    if f"/document/d/{DOC_ID}/export?format=md" in url:
        return httpx.Response(307, headers={"location": "https://doc-0g.docstext.googleusercontent.com/doc"})
    if f"/spreadsheets/d/{SHEET_ID}/export?format=ods" in url:
        return httpx.Response(307, headers={"location": "https://doc-08.sheets.googleusercontent.com/ods"})
    if f"/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=42" in url:
        return httpx.Response(307, headers={"location": "https://doc-08.sheets.googleusercontent.com/csv"})
    return httpx.Response(500)


bld._TRANSPORT = httpx.MockTransport(_google)


# ============================================================
# 1. Which links
# ============================================================
check("parse: Google Docs link", bld.parse(DOC_URL) == {"kind": "doc", "id": DOC_ID, "gid": ""})
check("parse: Google Sheets link", bld.parse(SHEET_URL) == {"kind": "sheet", "id": SHEET_ID, "gid": ""})
check("parse: a Sheets link to one tab keeps the tab",
      bld.parse(SHEET_URL.replace("?usp=sharing", "#gid=42"))["gid"] == "42")
check("parse: account-switch form /u/1/d/ still parses",
      (bld.parse(f"https://docs.google.com/document/u/1/d/{DOC_ID}/edit") or {}).get("id") == DOC_ID)
check("parse: published-to-web link is NOT read as a document id",
      bld.parse("https://docs.google.com/spreadsheets/d/e/2PACX-1vQabcdefghijklmnopqrstuvwxyz/pubhtml") is None)
check("parse: a look-alike host is not Google", bld.parse(f"https://docs.google.com.evil.io/document/d/{DOC_ID}") is None)

meta = {"assets": {"links": [
    {"id": "a", "url": SHEET_URL, "label": "Bảng giá", "pinned": True, "added_at": 2},
    {"id": "b", "url": "https://vi.wikipedia.org/wiki/Kim_khí", "label": "wiki", "added_at": 1},
]}}
body = f"Tư vấn theo tài liệu.\nXem thêm hướng dẫn: {DOC_URL}.\nBảng giá: {SHEET_URL.replace('?usp=sharing', '')}"
links = bld.links_of_agent(meta, body)
check("Agent links come first, with their label", links and links[0] == {"url": SHEET_URL, "label": "Bảng giá"})
check("a Google link written in the Agent text is read too", any(l["url"] == DOC_URL for l in links))
check("the same sheet linked twice is read once", sum(SHEET_ID in l["url"] for l in links) == 1)
check("non-Google links are not documents", not any("wikipedia" in l["url"] for l in links))
check("at most MAX_LINKS per Agent",
      len(bld.links_of_agent({}, " ".join(f"https://docs.google.com/document/d/{i:0>30}/edit" for i in range(30))))
      == bld.MAX_LINKS)


# ============================================================
# 2. What comes back
# ============================================================
sheet = bld.fetch(SHEET_URL)
check("sheet: every tab is read", "## Sản phẩm" in sheet["text"] and "## Chính sách" in sheet["text"])
check("sheet: each row carries its column names", "Tên sản phẩm: Kìm cắt Stanley 8 inch; Giá: 185.000đ" in sheet["text"])
check("sheet: empty cells are skipped, not printed as 'Tồn kho: '", "Búa đinh Total 500g; Giá: 95.000đ\n" in sheet["text"])
check("sheet: Google's thousand repeated empty cells/rows are not expanded", len(sheet["text"]) < 1000)
check("sheet: spreadsheet title comes from the file", sheet["title"] == "Bảng giá shop")

one_tab = bld.fetch(SHEET_URL.replace("?usp=sharing", "#gid=42"))
check("sheet link to one tab reads that tab as CSV", "Tên: Ốc vít M6; Giá: 2.000đ" in one_tab["text"])

doc = bld.fetch(DOC_URL)
check("doc: Markdown kept, headings intact", "## Giờ mở cửa" in doc["text"])
check("doc: inline base64 images are dropped", "base64" not in doc["text"] and len(doc["text"]) < 300)
check("doc: BOM stripped and first line is the title", doc["title"] == "Hướng dẫn tư vấn")

try:
    bld.fetch(PRIVATE_URL)
    check("private file raises", False)
except bld.LinkError as e:
    check("private file: owner is told to share it publicly", any(k in str(e) for k in ("chưa chia sẻ công khai", "not shared publicly")))
try:
    bld.fetch(f"https://docs.google.com/document/d/{GONE_ID}/edit")
    check("deleted file raises", False)
except bld.LinkError as e:
    check("deleted file: owner is told the link is wrong or gone", any(k in str(e) for k in ("không có trên Google", "not found on Google")))


# ============================================================
# 3. Cache and warnings
# ============================================================
bld.clear_cache()
CALLS.clear()
links2 = [{"url": SHEET_URL, "label": "Bảng giá"}, {"url": PRIVATE_URL, "label": "Kho nội bộ"}]
r1 = bld.collect(links2)
n_first = len(CALLS)
r2 = bld.collect(links2)
check("collect: the readable link becomes a document", [d["path"] for d in r1["docs"]] == ["Google Sheets: Bảng giá"])
check("collect: the private link becomes ONE owner warning naming it",
      len(r1["warnings"]) == 1 and "Kho nội bộ" in r1["warnings"][0] and any(k in r1["warnings"][0] for k in ("chưa chia sẻ", "not shared")))
check("collect: a second turn inside FRESH_S does not ask Google again", len(CALLS) == n_first)
check("collect: the warning stays visible on the next turn", r2["warnings"] == r1["warnings"])

# Google goes down after the copy is old: the old copy keeps answering, the owner is told.
with bld._lock:
    for c in bld._CACHE.values():
        c["ok_at"] -= bld.FRESH_S + 1
        c["err_at"] -= bld.FRESH_S + 1
STATE["down"] = True
bld.collect(links2)                      # schedules the background refresh, answers from the old copy
import threading  # noqa: E402
for t in [t for t in threading.enumerate() if t.name == "bot-linked-doc-refresh"]:
    t.join(5)
r3 = bld.collect(links2)
STATE["down"] = False

# Google is back: a failed copy is retried on the one-minute error clock, not after FRESH_S.
with bld._lock:
    for c in bld._CACHE.values():
        c["err_at"] -= bld.RETRY_ERR_S + 1
bld.collect(links2)
for t in [t for t in threading.enumerate() if t.name == "bot-linked-doc-refresh"]:
    t.join(5)
r4 = bld.collect(links2)
check("Google back: the sheet's warning clears after the retry",
      not any("Bảng giá" in w for w in r4["warnings"]))
check("Google down: the old copy still answers", [d["path"] for d in r3["docs"]] == ["Google Sheets: Bảng giá"])
check("Google down: the owner is told the bot uses the previous copy",
      any("Bảng giá" in w and any(k in w for k in ("bản đọc được lần trước", "last copy")) for w in r3["warnings"]))


# ============================================================
# 4. Through the search, and through the bot runtime
# ============================================================
BRAIN = Path(tempfile.mkdtemp(prefix="javis-bld-brain-"))
(BRAIN / "chinh-sach.md").write_text("# Chính sách\n\n## Giao hàng\n\nNội thành giao trong 24 giờ.\n",
                                     encoding="utf-8")
extra = bld.collect([{"url": SHEET_URL, "label": "Bảng giá"}])["docs"]
no_link = chatbot_grounding.thu_thap(BRAIN, "kìm cắt stanley giá bao nhiêu")
with_link = chatbot_grounding.thu_thap(BRAIN, "kìm cắt stanley giá bao nhiêu", 4, extra)
check("CANARY: without the link the bot finds nothing (the reported bug)", not no_link["co"])
check("with the link the price row is found", with_link["co"] and "185.000đ" in with_link["khoi"])
check("the source line names the Google file", with_link["nguon"][0] == "Google Sheets: Bảng giá")
check("customers typing without accents still hit the sheet",
      chatbot_grounding.thu_thap(BRAIN, "kim cat stanley gia bao nhieu", 4, extra)["co"])
check("brain files still answer next to the linked file",
      chatbot_grounding.thu_thap(BRAIN, "giao hàng nội thành mất bao lâu", 4, extra)["nguon"][0] == "chinh-sach.md")
check("the plain brain index is untouched by another bot's links",
      not chatbot_grounding.thu_thap(BRAIN, "kìm cắt stanley giá bao nhiêu")["co"])

AGENTS = {
    "cskh": ({"name": "CSKH", "assets": {"links": [{"id": "x", "url": SHEET_URL, "label": "Bảng giá"}]}},
             "Chỉ trả lời theo tài liệu."),
    "noi-bo": ({"name": "Nội bộ", "assets": {"links": [{"id": "y", "url": PRIVATE_URL, "label": "Kho nội bộ"}]}},
               "Việc nội bộ."),
    "trong": ({"name": "Trống"}, "Không có link nào."),
}
chatbot_runtime._deps["brain_root"] = lambda b: str(BRAIN)
chatbot_runtime._deps["read_agent"] = lambda b, slug: AGENTS[slug]


def ask(slug, text):
    cfg = {"id": "bot-" + slug, "brain": "b", "agent": {"brain": "b", "slug": slug}}
    return asyncio.run(chatbot_runtime._tra_tai_lieu(cfg["id"], cfg, text))


tl = ask("cskh", "kìm cắt stanley giá bao nhiêu")
check("runtime: the bot of the Agent with the sheet answers from it", tl["co"] and "185.000đ" in tl["khoi"])
check("runtime: a readable link adds no warning", not tl.get("canh_bao_link"))
tl2 = ask("noi-bo", "kìm cắt stanley giá bao nhiêu")
check("runtime: another Agent on the same brain does NOT see that sheet", not tl2["co"])
check("runtime: its private link reaches the bot card as a warning", "Kho nội bộ" in (tl2.get("canh_bao_link") or ""))

CALLS.clear()
tl3 = ask("trong", f"giá trong file này bao nhiêu {SHEET_URL.replace(SHEET_ID, 'X' * 44)}")
check("SECURITY: a link the CUSTOMER types is never fetched", CALLS == [] and not tl3["co"])

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
