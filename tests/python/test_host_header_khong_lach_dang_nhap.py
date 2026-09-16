"""Một dấu "/" trong header Host KHÔNG được lách cổng đăng nhập.

    python tests/run.py host_header     (KHÔNG mạng)

Bối cảnh 0.59.16. _auth_guard quyết định "đường này có công khai không" bằng
`request.url.path`. Nhưng Starlette dựng request.url bằng cách NỐI CHUỖI
"{scheme}://{header Host}{path}" rồi phân tích lại, và nó không kiểm header Host một chữ nào
(PYSEC-2026-161). Nên:

    GET /agents  kèm  Host: vps-cua-toi.com/static
    -> request.url.path == "/static/agents"  -> hàng rào thấy tiền tố công khai "/static"
    -> router vẫn chọn                /agents -> endpoint thật chạy, KHÔNG cần đăng nhập

Đo thật ngày 16/09 trên chính app này (uvicorn + socket thô, và cả TestClient): request đó
trả 200 kèm danh sách trợ lý thay vì 401. Tức mọi Javis mở ra Internet (VPS, Docker, bất cứ
máy nào đặt mật khẩu) đều bị đọc và ghi API không cần đăng nhập, chỉ bằng một header.

Hai lớp canh, test cả hai:
  1. Hàng rào hỏi scope["path"] (đường dẫn ROUTER dùng), không hỏi url.path.
  2. Header Host méo bị chặn 400 ngay.
Kèm một canary: cấm `request.url.path` quay lại trong hai middleware gác cổng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-hosthdr-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"   # bật cổng đăng nhập mà không cần đặt mật khẩu

from fastapi.testclient import TestClient   # noqa: E402
import main            # noqa: E402
import web_security    # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


cl = TestClient(main.app, base_url="http://127.0.0.1:7777")


def ma(duong, host=None):
    return cl.get(duong, headers=({"host": host} if host else None)).status_code


# ---- 1) Cổng đăng nhập phải đóng, kể cả khi Host bị nhét đường công khai vào ----
check("chưa đăng nhập: GET /agents trả 401", ma("/agents") == 401)

# Đòi ĐÚNG 401, không phải "khác 200": 401 là chữ ký của LỚP MỘT (hàng rào đăng nhập đọc
# scope["path"]). Lớp hai chặn Host méo trả 400, mà nó nằm SAU _auth_guard trong chồng
# middleware - nhận 400 nghĩa là lớp một đã mở cửa và chỉ còn lớp hai gánh. Cả hai lớp đều
# giữ request khỏi endpoint, nhưng test phải đo được từng lớp một.
for host in ("127.0.0.1:7777/static",          # tiền tố trong _AUTH_PUBLIC_PREFIX
             "127.0.0.1:7777/health",
             "127.0.0.1:7777/static/..",       # lách bằng đường đi lùi
             "127.0.0.1:7777/",                # tiền tố là chính "/" trong _AUTH_PUBLIC_EXACT
             "127.0.0.1:7777/auth/login"):     # đường công khai trong _AUTH_PUBLIC_EXACT
    check(f"Host {host!r}: /agents vẫn trả 401 (lớp một chặn)", ma("/agents", host) == 401)

# Phải là ĐÚNG 401. Nếu chỉ đòi "khác 200" thì ca chưa vá cũng lọt: hàng rào mở ra rồi,
# endpoint mới là chỗ trả 422 vì thiếu field - đọc vội tưởng đã chặn.
check("Host méo POST /kanban/task trả 401 (chặn ở hàng rào, không phải 422 ở endpoint)",
      cl.post("/kanban/task", headers={"host": "127.0.0.1:7777/static"},
              json={"title": "x"}).status_code == 401)

# ---- 2) Host méo bị chặn thẳng ở web_security, không chỉ "không lọt" ----
for xau in ("127.0.0.1:7777/static", "a.com@evil.com", "a.com\\static", "a b.com",
            "a.com?x=1", "a.com#f"):
    check(f"host_hop_le({xau!r}) là False", web_security.host_hop_le(xau) is False)

for tot in ("127.0.0.1:7777", "localhost", "[::1]:7777", "javis.example.com", ""):
    check(f"host_hop_le({tot!r}) là True", web_security.host_hop_le(tot) is True)

d = web_security.csrf_decision("GET", "127.0.0.1:7777/static", None, True)
check("csrf_decision chặn 400 với Host méo", bool(d) and d[0] == 400)
check("csrf_decision vẫn cho qua Host bình thường",
      web_security.csrf_decision("GET", "127.0.0.1:7777", None, True) is None)

# ---- 3) Đường dẫn bình thường KHÔNG bị khoá nhầm (rào mới không được bắt oan) ----
check("/health vẫn mở không cần đăng nhập", ma("/health") == 200)
check("/auth/status vẫn mở không cần đăng nhập", ma("/auth/status") == 200)
check("/static/app.js vẫn mở không cần đăng nhập", ma("/static/app.js") == 200)

# ---- 4) Canary: middleware gác cổng không được đọc lại request.url.path ----
src = (SERVER / "main.py").read_text(encoding="utf-8", errors="replace")


def than_ham(ten):
    """Thân hàm, đã BỎ chú thích: comment cố ý nhắc chữ 'url.path' để cảnh báo người sau,
    đếm cả comment thì canary tự đỏ vì đúng dòng cảnh báo nó muốn có."""
    m = re.search(r"async def " + ten + r"\(request.*?\n(?=\n\n)", src, re.S)
    if not m:
        return ""
    return "\n".join(d.split("#", 1)[0] for d in m.group(0).split("\n"))


for ten in ("_auth_guard", "_csrf_guard"):
    than = than_ham(ten)
    check(f"bóc được thân {ten}", bool(than))
    check(f"{ten} KHÔNG dùng request.url.path (phải hỏi duong_dan_router)",
          "url.path" not in than)

check("duong_dan_router đọc scope['path']",
      'scope.get("path")' in src or "scope['path']" in src)

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - host_header_khong_lach_dang_nhap")
