"""0.225.0: đổi bộ não tải note nhanh (bộ đệm đồ thị, ETag, nén gzip câu trả lời API).

    python tests/run.py tai_note_nhanh      (KHÔNG mạng)

Chủ dự án 19/10 (ảnh ô "Đang tải..." cạnh ô chọn brain): "khi tải bộ não mới hoặc sang 1 bộ não khác phần tải note đang
rất chậm, tìm cách tăng tốc độ nó lên". Đo trên bộ não 2000 note qua đường 8 Mbps: 1,6 giây, trong đó 1,5 giây là tải
989 KB JSON không nén, và mỗi lần đổi brain server đọc lại trọn 2000 file.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import gzip
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-tainote-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import graph_builder as gb  # noqa: E402
import nen_phan_hoi  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def ghi(p, text, mtime=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if mtime:
        os.utime(p, (mtime, mtime))


V = Path(tempfile.mkdtemp(prefix="vault-"))
ghi(V / "wiki" / "A.md", "# A\n[[B]] [[C]] [[không có]]")
ghi(V / "wiki" / "B.md", "# B\n```bash\n[[ -f x ]]\n```\n[[A]]")
ghi(V / "wiki" / "C.md", "# C")
ghi(V / "zz" / "a.md", "trùng tên A (khác hoa thường): bị bỏ, giữ bản gặp trước")
ghi(V / ".obsidian" / "ẩn.md", "[[A]]")
ghi(V / "wiki" / ".nhap.md", "[[A]]")
ghi(V / "wiki" / "khong-phai-note.txt", "[[A]]")
try:
    os.symlink(str(V / "wiki"), str(V / "wiki" / "vong"))       # liên kết vòng: không được treo
except OSError:
    pass

goi_doc = []
_goc_parse = gb._parse_file


def _dem_parse(fpath, st):
    goi_doc.append(os.path.basename(fpath))
    return _goc_parse(fpath, st)


gb._parse_file = _dem_parse

# ---- 1. Kết quả như cũ ----
e1, d = gb.graph_with_etag([str(V)], include_orphans=True)
ids = sorted(n["id"] for n in d["nodes"])
check("đủ note, bỏ thư mục ẩn, file ẩn và file không phải .md", ids == ["a", "b", "c"], ids)
check("trùng tên giữ bản gặp trước (thứ tự tên thư mục, cố định)", [n["path"] for n in d["nodes"] if n["id"] == "a"][0].endswith("/wiki/A.md"),
      [n["path"] for n in d["nodes"]])
check("liên kết đúng: A-B, A-C, không nối tới note không có, bỏ [[ ]] trong khối mã",
      d["stats"]["total_links"] == 2 and d["stats"]["total_notes"] == 3, d["stats"])
check("không gửi đường dẫn tuyệt đối của máy chủ", all("fullpath" not in n for n in d["nodes"]))
check("liên kết vòng không đọc file lặp lại", len(goi_doc) == 4, goi_doc)
check("build_graph cũ vẫn trả đúng kết quả", gb.build_graph([str(V)], include_orphans=True)["stats"] == d["stats"])

# ---- 2. Lần sau không đọc lại file nào ----
goi_doc.clear()
e2, d2 = gb.graph_with_etag([str(V)], include_orphans=True)
check("vault không đổi: không đọc lại file nào", goi_doc == [], goi_doc)
check("và ETag giữ nguyên", e2 == e1)

# Khởi động lại server (mất bộ nhớ trong RAM): bộ đệm trên đĩa vẫn còn.
gb._file_cache.clear()
gb._result_cache.clear()
e3, d3 = gb.graph_with_etag([str(V)], include_orphans=True)
check("sau khởi động lại: đọc từ bộ đệm trên đĩa, không đọc file", goi_doc == [] and e3 == e1, goi_doc)
check("bộ đệm nằm trong JAVIS_STATE_DIR", any((Path(_STATE) / "cache" / "graph").glob("*.json")))

# ---- 3. File đổi, thêm, xoá ----
ghi(V / "wiki" / "C.md", "# C\n[[B]] mới thêm liên kết", mtime=time.time() + 5)
e4, d4 = gb.graph_with_etag([str(V)], include_orphans=True)
check("sửa một file: chỉ đọc lại đúng file đó", goi_doc == ["C.md"], goi_doc)
check("liên kết mới hiện ra, ETag đổi", d4["stats"]["total_links"] == 3 and e4 != e1, d4["stats"])
goi_doc.clear()
ghi(V / "wiki" / "D.md", "[[A]]")
e5, d5 = gb.graph_with_etag([str(V)], include_orphans=True)
check("thêm file: đọc đúng file mới", goi_doc == ["D.md"] and "d" in {n["id"] for n in d5["nodes"]}, goi_doc)
(V / "wiki" / "D.md").unlink()
e6, d6 = gb.graph_with_etag([str(V)], include_orphans=True)
check("xoá file: note biến mất, ETag đổi", "d" not in {n["id"] for n in d6["nodes"]} and e6 != e5)
check("bộ đệm hỏng trên đĩa: không vỡ, dựng lại", True)
for f in (Path(_STATE) / "cache" / "graph").glob("*.json"):
    f.write_text("hỏng{", encoding="utf-8")
gb._file_cache.clear()
gb._result_cache.clear()
check("bộ đệm hỏng: vẫn ra đúng đồ thị", gb.graph_with_etag([str(V)], include_orphans=True)[1]["stats"] == d6["stats"])
check("orphans=0 và orphans=1 là hai kết quả riêng",
      gb.graph_with_etag([str(V)], include_orphans=False)[0] != gb.graph_with_etag([str(V)], include_orphans=True)[0])
gb._parse_file = _goc_parse

# ---- 4. Endpoint: ETag, 304, gzip ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.get("/graph", params={"path": str(V), "orphans": 1}, headers={"Accept-Encoding": "gzip"})
check("/graph trả ETag và no-cache", r.status_code == 200 and r.headers.get("etag", "").startswith('"g-')
      and r.headers.get("cache-control") == "no-cache", dict(r.headers))
check("/graph trả đúng dữ liệu", r.json()["stats"] == d6["stats"])
r2 = cl.get("/graph", params={"path": str(V), "orphans": 1}, headers={"If-None-Match": r.headers["etag"]})
check("hỏi lại với If-None-Match: 304 trống", r2.status_code == 304 and not r2.content, r2.status_code)

# Gói lớn thì được nén.
for i in range(60):
    ghi(V / "lon" / f"Ghi chú số {i}.md", f"[[Ghi chú số {(i + 1) % 60}]] " + "chữ " * 50)
raw = cl.get("/graph", params={"path": str(V), "orphans": 1}, headers={"Accept-Encoding": "gzip"},
             extensions={})
check("/graph lớn được nén gzip", raw.headers.get("content-encoding") == "gzip", dict(raw.headers))
check("Vary: Accept-Encoding", "Accept-Encoding" in raw.headers.get("vary", ""))
khong = cl.get("/graph", params={"path": str(V), "orphans": 1}, headers={"Accept-Encoding": "identity"})
check("trình duyệt không nhận gzip: trả trần", khong.headers.get("content-encoding") is None and khong.json()["nodes"])


# ---- 5. Middleware nén: chỉ câu trả lời trọn một cục ----
def chay(app, headers=((b"accept-encoding", b"gzip"),), method="GET", path="/x"):
    tin = []

    async def recv():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(m):
        tin.append((time.monotonic(), m))

    asyncio.run(nen_phan_hoi.NenPhanHoi(app)({"type": "http", "method": method, "path": path,
                                              "headers": list(headers)}, recv, send))
    return tin


def app_mot_cuc(body, ct=b"application/json", status=200, extra=()):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", ct), (b"content-length", str(len(body)).encode()), *extra]})
        await send({"type": "http.response.body", "body": body, "more_body": False})
    return app


lon = json.dumps({"x": ["chữ"] * 2000}, ensure_ascii=False).encode()
t = chay(app_mot_cuc(lon))
h = dict(t[0][1]["headers"])
check("JSON lớn: nén, độ dài mới đúng", h.get(b"content-encoding") == b"gzip"
      and int(h[b"content-length"]) == len(t[1][1]["body"]) and gzip.decompress(t[1][1]["body"]) == lon)
t = chay(app_mot_cuc(b'{"ok":true}'))
check("JSON nhỏ: để nguyên", b"content-encoding" not in dict(t[0][1]["headers"]) and t[1][1]["body"] == b'{"ok":true}')
t = chay(app_mot_cuc(lon), headers=())
check("không có Accept-Encoding gzip: để nguyên", t[1][1]["body"] == lon)
t = chay(app_mot_cuc(lon, ct=b"image/png"))
check("ảnh: để nguyên", t[1][1]["body"] == lon)
t = chay(app_mot_cuc(lon, status=206))
check("206 (tải từng đoạn): để nguyên", t[1][1]["body"] == lon)
t = chay(app_mot_cuc(lon, extra=((b"content-encoding", b"br"),)))
check("đã có content-encoding: để nguyên", t[1][1]["body"] == lon)
t = chay(app_mot_cuc(lon), path="/static/app.js")
check("/static/ để cho lớp nén tĩnh có sẵn", t[1][1]["body"] == lon)
t = chay(app_mot_cuc(lon), method="HEAD")
check("HEAD: để nguyên", t[1][1]["body"] == lon)


def app_stream(ct):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", ct)]})
        for i in range(3):
            await send({"type": "http.response.body", "body": (b"data: %d\n\n" % i) * 400, "more_body": True})
            await asyncio.sleep(0.2)
        await send({"type": "http.response.body", "body": b"", "more_body": False})
    return app


t = chay(app_stream(b"text/event-stream"))
check("SSE: tin mở đầu đi ngay, không chờ thân", t[0][1]["type"] == "http.response.start"
      and t[1][0] - t[0][0] < 0.1)
moc = [x[0] for x in t if x[1]["type"] == "http.response.body"]
check("SSE: từng mẩu đi ngay khi có, không bị gom", len(moc) == 4 and moc[1] - moc[0] > 0.15 and moc[2] - moc[1] > 0.15, moc)
check("SSE: không nén", all(b"content-encoding" not in dict(x[1].get("headers") or []) for x in t))
t = chay(app_stream(b"application/json"))
moc = [x[0] for x in t if x[1]["type"] == "http.response.body"]
check("stream JSON (nhiều mẩu): vẫn đi từng mẩu, không nén",
      len(moc) == 4 and moc[1] - moc[0] > 0.15 and b"content-encoding" not in dict(t[0][1]["headers"]), moc)

src = (SERVER / "main.py").read_text(encoding="utf-8")
check("middleware nén gắn TRƯỚC mọi middleware khác (nằm trong cùng)",
      src.index("app.add_middleware(nen_phan_hoi.NenPhanHoi)") < src.index("app.add_middleware(CORSMiddleware"))
check("không middleware nào gắn trước nó", "add_middleware" not in src[:src.index("app.add_middleware(nen_phan_hoi.NenPhanHoi)")]
      and "@app.middleware" not in src[:src.index("app.add_middleware(nen_phan_hoi.NenPhanHoi)")])
trang = cl.get("/", headers={"Accept-Encoding": "gzip"})
check("trang chủ cũng được nén", trang.headers.get("content-encoding") == "gzip", dict(trang.headers))

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_tai_note_nhanh: all pass")
