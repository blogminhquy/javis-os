"""Trang .html chia sẻ không còn chết vì localStorage.

    python tests/run.py chia_se_kho_luu_tru

Chủ repo báo 21/09: app .html chia sẻ qua `/s/<token>/` mở ra TRẮNG TRANG, trong khi tab
Network xanh hết và `data.json` bên cạnh đã tải xong.

Nguyên nhân nằm ở chính chốt an toàn của tính năng. `CSP_HTML` cố ý không có
`allow-same-origin`, nên trang nhận gốc "null"; mà theo chuẩn, tài liệu gốc null KHÔNG có kho
lưu trữ - chạm vào `window.localStorage` là trình duyệt ném SecurityError. Lỗi ném ở DÒNG ĐẦU
chạm vào kho nên nó giết cả script, chứ không chỉ hỏng cái tính năng nhớ tông màu. Mà lưu một
bộ lọc hay một tông màu thì gần như mọi trang dashboard do AI viết đều làm.

Ba điểm đáng canh, vì cả ba đều có cách làm sai trông hợp lý hơn:

1. CHỖ CHÈN. Bản vá phải chạy TRƯỚC mọi script của trang. Nhét trước `<!doctype>` là trình
   duyệt rơi vào chế độ quirks và bố cục của người ta vỡ - đổi một lỗi lấy một lỗi khác.

2. CHỈ VÁ KHI CẦN. Trang mở ở nơi có kho thật thì phải giữ kho thật, không thì dữ liệu người
   ta đã lưu bỗng biến mất sau một bản cập nhật.

3. KHÔNG NỚI LỚP CÁCH LY. Cách "dễ" là thêm `allow-same-origin` vào CSP; làm thế là gỡ đúng
   cái chốt khiến Javis dám phục vụ HTML người dùng viết trên cùng tên miền với dashboard.
   Test này khoá chuyện đó lại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-cskl-")
_BRAINS = tempfile.mkdtemp(prefix="javis-cskl-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS

BRAIN = os.path.join(_BRAINS, "brain")
os.makedirs(os.path.join(BRAIN, "apps"), exist_ok=True)
with open(os.path.join(BRAIN, "apps", "bang.html"), "w", encoding="utf-8") as f:
    f.write("<!doctype html><html><head><meta charset=\"utf-8\"><title>Bảng</title></head>"
            "<body><h1>Bảng giá</h1><script>localStorage.setItem('tong','toi')</script>"
            "</body></html>")
with open(os.path.join(BRAIN, "ghi-chu.md"), "w", encoding="utf-8") as f:
    f.write("# Ghi chú\n\nChữ thường.\n")

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import share_render  # noqa: E402

fails = []


def check(ten, dk, them=""):
    print(("ok   " if dk else "FAIL ") + ten + (("  [" + str(them) + "]") if not dk and them else ""))
    if not dk:
        fails.append(ten)


# ============================================================
# 1. Chỗ chèn: trước mọi script, sau doctype
# ============================================================
VA = share_render.chen_polyfill_luu_tru

r = VA('<!doctype html><html><head><title>x</title></head><body><script>a()</script></body></html>')
check("có <head> thì chèn ngay sau <head>", r.index("__javis_thu__") > r.index("<head>")
      and r.index("__javis_thu__") < r.index("<title>"), r[:120])
check("và vẫn đứng trước script của trang", r.index("__javis_thu__") < r.index("a()"))

r2 = VA('<!doctype html><h1>App</h1><script>a()</script>')
check("không có <head> thì chèn sau doctype", r2.lower().startswith("<!doctype html>"), r2[:60])
check("và vẫn trước script của trang", r2.index("__javis_thu__") < r2.index("a()"))

r3 = VA('<html><body>x</body></html>')
check("không doctype nhưng có <html> thì chèn sau <html>",
      r3.index("__javis_thu__") > r3.index("<html>"), r3[:80])

r4 = VA('<div>manh vun</div>')
check("mảnh HTML rời cũng vá được", "__javis_thu__" in r4 and r4.endswith("<div>manh vun</div>"))

# Doctype phải là thứ ĐẦU TIÊN trong file, không thì trình duyệt vào chế độ quirks.
for goc in ('<!doctype html><html><head></head></html>', '<!DOCTYPE HTML><html></html>'):
    check("doctype vẫn đứng đầu file sau khi vá (không rơi vào quirks mode)",
          VA(goc).lstrip().lower().startswith("<!doctype"), VA(goc)[:40])

check("bản vá là script nội tuyến, không tải gì từ ngoài",
      "<script>" in share_render.POLYFILL_LUU_TRU and "src=" not in share_render.POLYFILL_LUU_TRU)

# ============================================================
# 2. Chạy thật qua route /s/<token>/
# ============================================================
main.cfgmod.gate_active = lambda: False
c = TestClient(main.app, base_url="http://127.0.0.1")

rs = c.post("/share/create", json={"brain": BRAIN, "path": "apps/bang.html"})
TOK = (rs.json() or {}).get("token", "")
check("chia sẻ được trang .html", bool(TOK), rs.text[:160])

h = c.get("/s/" + TOK + "/")
check("mở được trang", h.status_code == 200, h.status_code)
check("nội dung của người dùng còn NGUYÊN VĂN", "<h1>Bảng giá</h1>" in h.text)
check("bản vá kho lưu trữ được chèn vào", "__javis_thu__" in h.text)
check("và đứng trước script của trang",
      h.text.index("__javis_thu__") < h.text.index("localStorage.setItem"))

# Đây là cái chốt chính của cả tính năng chia sẻ. Thêm allow-same-origin để "chữa"
# localStorage là trao cookie đăng nhập của chủ cho một file .html do AI viết.
csp = h.headers.get("content-security-policy") or ""
check("CSP KHÔNG hề nới ra: vẫn sandbox, vẫn không allow-same-origin",
      "sandbox" in csp and "allow-same-origin" not in csp, csp)

# Trang .md/.txt do server tự dựng, không có script nào và bị cách ly chặt hơn (CSP_TINH).
# Nhét một thẻ <script> vào đó là phá đúng cái tính chất ấy.
rm = c.post("/share/create", json={"brain": BRAIN, "path": "ghi-chu.md"})
m = c.get("/s/" + (rm.json() or {}).get("token", ""))
check("trang .md KHÔNG bị chèn script", "<script" not in m.text.lower(), m.text[:120])
check("và vẫn cách ly ở mức chặt nhất",
      (m.headers.get("content-security-policy") or "") == share_render.CSP_TINH)

# ============================================================
# 3. Hành vi của chính đoạn script
# ============================================================
# Chạy THẬT bằng node (kho hỏng thì thay, kho thật thì giữ nguyên, thăm dò không để lại rác):
# xem tests/js/test_kho_luu_tru_trang_chia_se.js. Ở đây chỉ canh hai tính chất thuộc về phía
# máy chủ.
check("bản vá thăm dò bằng một lượt ghi-rồi-xoá thật, không chỉ xem biến có tồn tại",
      "setItem(" in share_render.POLYFILL_LUU_TRU
      and "removeItem(" in share_render.POLYFILL_LUU_TRU)
check("vá cả sessionStorage chứ không riêng localStorage",
      "sessionStorage" in share_render.POLYFILL_LUU_TRU
      and "localStorage" in share_render.POLYFILL_LUU_TRU)

if fails:
    print(f"\nFAIL {len(fails)} muc: " + ", ".join(fails))
    raise SystemExit(1)
print("\nOK - test_chia_se_kho_luu_tru: tat ca pass")
