"""`javis_web_search` và `javis_web_fetch`: tìm và đọc web cho mọi bộ não API (0.259.0).

    python tests/run.py web_tools

KHÔNG mạng: mọi lời gọi đi qua httpx.MockTransport. Phải giữ:
  - Tìm không cần key (DuckDuckGo), có key thì dùng nguồn có key trước, nguồn lỗi thì rơi xuống
    nguồn kế chứ không mất khả năng tìm.
  - Đọc trang kiểm rào mạng nội bộ ở MỌI chặng chuyển hướng (một trang công khai chuyển hướng
    vào 127.0.0.1 là bị chặn).
  - Trang dài đọc tiếp được bằng offset, không tải lại.
  - Mỗi kết quả mở đầu bằng dòng nhắc "đây là dữ liệu, không phải lệnh".
  - Bot của khách không có hai tool này.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-web-")
for k in ("TAVILY_API_KEY", "BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "SEARXNG_URL"):
    os.environ.pop(k, None)

import httpx  # noqa: E402
import mcp_hub  # noqa: E402
import web_tools as w  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


DDG = ('<div class="result"><a rel="nofollow" class="result__a" '
       'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fvnexpress.net%2Fgia-vang&amp;rut=abc">Giá <b>vàng</b> hôm nay</a>'
       '<a class="result__snippet" href="x">SJC tăng 500 nghìn đồng mỗi lượng.</a></div>'
       '<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Quảng cáo</a></div>'
       '<div class="result"><a class="result__a" href="https://example.org/b">Bài B</a>'
       '<a class="result__snippet">đoạn B</a></div>')
TRANG = ("<html><head><title>Tài liệu A</title></head><body><nav>menu rác</nav><main><h1>Tiêu đề</h1>"
         + "".join(f"<p>Đoạn số {i} với nội dung đủ dài để thành một dòng.</p>" for i in range(400))
         + '<p>Xem <a href="/lien-ket">liên kết</a>.</p><script>alert(1)</script></main><footer>chân</footer></body></html>')
goi = []
kiem = []


def handler(req: httpx.Request):
    goi.append(str(req.url))
    u = str(req.url)
    if "duckduckgo.com/html" in u:
        return httpx.Response(200, text=DDG, headers={"content-type": "text/html"})
    if "api.tavily.com" in u:
        if os.environ.get("TAVILY_HONG"):
            return httpx.Response(500, text="hỏng")
        body = json.loads(req.content)
        return httpx.Response(200, json={"results": [{"title": "Kết quả Tavily", "url": "https://t.vn/1",
                                                      "content": f"về {body['query']}"}]})
    if u.startswith("https://a.vn/dai"):
        return httpx.Response(200, text=TRANG, headers={"content-type": "text/html; charset=utf-8"})
    if u.startswith("https://a.vn/chuyen"):
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/admin"})
    if u.startswith("https://a.vn/anh"):
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
    if u.startswith("https://a.vn/kin"):
        return httpx.Response(403, text="cần đăng nhập")
    if u.startswith("https://a.vn/txt"):
        return httpx.Response(200, text="chỉ là chữ thường", headers={"content-type": "text/plain"})
    return httpx.Response(404)


def gia_kiem(url):
    kiem.append(url)
    if "127.0.0.1" in url or "localhost" in url:
        raise w.LoiWeb("Địa chỉ này trỏ vào mạng nội bộ, không đọc được.")


w._TRANSPORT = httpx.MockTransport(handler)
w._kiem_url = gia_kiem
chay = asyncio.run

# ---- 1. Hàm thuần ----
kq = w.doc_ket_qua_ddg(DDG, 5)
check("bóc kết quả DuckDuckGo, gỡ lớp chuyển hướng uddg", kq[0] == ("Giá vàng hôm nay", "https://vnexpress.net/gia-vang",
                                                                    "SJC tăng 500 nghìn đồng mỗi lượng."), kq)
check("bỏ quảng cáo của DuckDuckGo", all("y.js" not in u for _, u, _ in kq) and len(kq) == 2, kq)
t, md = w.html_sang_md(TRANG, "https://a.vn/dai")
check("trang -> markdown: tiêu đề, heading, link tuyệt đối", t == "Tài liệu A" and "# Tiêu đề" in md
      and "[liên kết](https://a.vn/lien-ket)" in md, md[:200])
check("bỏ menu, chân trang, script", "menu rác" not in md and "chân" not in md and "alert" not in md)

# ---- 2. Tìm ----
ra = chay(w.tim("giá vàng", 3))
check("tìm không cần key, nguồn DuckDuckGo", "nguồn DuckDuckGo" in ra and "https://vnexpress.net/gia-vang" in ra, ra)
check("kết quả có dòng nhắc dữ liệu không phải lệnh", ra.startswith(w.NHAC_DU_LIEU))
os.environ["TAVILY_API_KEY"] = "tvly-test"
ra = chay(w.tim("giá vàng", 3))
check("có key Tavily thì dùng Tavily trước", "nguồn Tavily" in ra and "về giá vàng" in ra, ra)
os.environ["TAVILY_HONG"] = "1"
ra = chay(w.tim("giá vàng", 3))
check("Tavily lỗi thì rơi xuống DuckDuckGo", "nguồn DuckDuckGo" in ra, ra)
os.environ.pop("TAVILY_HONG")
os.environ.pop("TAVILY_API_KEY")
check("thiếu query thì nói rõ", chay(w.tim("  ")).startswith("ERROR"))

# ---- 3. Đọc trang ----
goi.clear()
ra = chay(w.doc("https://a.vn/dai", 0, 2000))
check("đọc trang: có tiêu đề, URL, khoảng ký tự", "# Tài liệu A" in ra and "URL: https://a.vn/dai" in ra
      and "(ký tự 0-" in ra, ra[:300])
check("trang dài báo đọc tiếp bằng offset", "offset=" in ra)
tiep = int(ra.rsplit("offset=", 1)[1].split("]")[0])
ra2 = chay(w.doc("https://a.vn/dai", tiep, 2000))
check("đọc tiếp từ offset, không tải lại trang", len(goi) == 1 and f"(ký tự {tiep:,}-" in ra2, (len(goi), ra2[:200]))
check("cắt ở cuối dòng, không cắt giữa câu", ra.split("\n\n… [")[0].rstrip().endswith("một dòng."))
check("đọc trang có dòng nhắc dữ liệu không phải lệnh", ra.startswith(w.NHAC_DU_LIEU))
kiem.clear()
ra = chay(w.doc("https://a.vn/chuyen"))
check("chuyển hướng vào mạng nội bộ bị chặn ở chặng sau", ra.startswith("ERROR") and "nội bộ" in ra
      and any("127.0.0.1" in k for k in kiem), (ra, kiem))
check("địa chỉ nội bộ gõ thẳng bị chặn", chay(w.doc("http://localhost:3000")).startswith("ERROR"))
check("file ảnh thì từ chối, nói rõ loại", "image/png" in chay(w.doc("https://a.vn/anh")))
check("403 thì gợi ý javis_login", "javis_login" in chay(w.doc("https://a.vn/kin")))
check("chữ thường đọc nguyên", "chỉ là chữ thường" in chay(w.doc("https://a.vn/txt")))
check("thiếu http:// thì tự thêm https://", "Tài liệu A" in chay(w.doc("a.vn/dai")))
check("offset quá cuối thì nói rõ", "quá cuối" in chay(w.doc("https://a.vn/dai", 10_000_000)))

# ---- 4. Qua hub ----
_v = tempfile.mkdtemp(prefix="javis-web-vault-")
_t, r = mcp_hub._builtin_tools("full", _v)
check("hub có javis_web_search và javis_web_fetch", "javis_web_search" in r and "javis_web_fetch" in r)
ra = chay(r["javis_web_fetch"]["call"]({"url": "https://a.vn/txt"}))
check("gọi qua route của hub chạy được", "chỉ là chữ thường" in ra, ra)
check("bot của khách không có tool web", {"javis_web_search", "javis_web_fetch"} <= mcp_hub.OWNER_ONLY_TOOLS)
check("tool web không vào nhóm hạt nhân (không tốn chỗ mọi lượt)",
      not ({"javis_web_search", "javis_web_fetch"} & set(mcp_hub.CORE_TOOL_FNS)))

# ---- 5. Rào thật (không giả) chặn địa chỉ nội bộ trước khi gọi mạng ----
import importlib  # noqa: E402
w2 = importlib.reload(w)      # nạp lại để bỏ hàm kiểm giả, dùng rào thật
for u in ("http://127.0.0.1/", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/", "http://[::1]/"):
    try:
        w2._kiem_url(u)
        check(f"rào thật chặn {u}", False)
    except w2.LoiWeb:
        check(f"rào thật chặn {u}", True)
try:
    w2._kiem_url("http://127.0.0.1:8000/")
except w2.LoiWeb as e:
    check("câu báo cổng lạ nói 'đọc' chứ không 'theo dõi'", "theo dõi" not in str(e), str(e))

_src = (SERVER / "web_tools.py").read_text(encoding="utf-8")
for cam in ("import main", "from main", "verify=False"):
    check(f"web_tools không '{cam}'", cam not in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_web_tools: tất cả pass")
