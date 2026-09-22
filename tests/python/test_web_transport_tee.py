"""Transport engine Web: bóc chữ khỏi luồng SSE, và đoạn tee chạy thật trong Chromium.

    python tests/run.py web_transport_tee

Hai tầng phép thử:

  1. **`ghep_delta` là hàm THUẦN** - chạy được mọi nơi, không cần trình duyệt. Đây là chỗ dễ
     sai nhất vì khuôn sự kiện của trang đổi theo đợt, nên nó phải nhận nhiều khuôn và bỏ qua
     cái không hiểu thay vì nổ.
  2. **Đoạn tee chạy THẬT** trong Chromium, trên một trang tĩnh tự phát SSE. Không cần tài
     khoản ChatGPT, không cần mạng ra ngoài. Nếu máy không có Playwright hoặc Chromium thì
     tầng này tự bỏ qua và nói rõ, chứ không đỏ oan.

Thứ KHÔNG test được ở đây, và phải nói thẳng: bấm đúng ô soạn của chatgpt.com thật. Cái đó
cần một phiên đăng nhập thật và chỉ chủ máy chạy được.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-webtrans-"))

import web_transport as wt  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def sse(*objs):
    """Một mẩu SSE như trang thật gửi."""
    return "".join("data: " + json.dumps(o) + "\n\n" for o in objs)


# ============================================================
# 1) ghep_delta: thuần, nhận nhiều khuôn
# ============================================================

check("khuôn delta gọn: ghép đúng thứ tự",
      wt.ghep_delta([sse({"v": "Xin "}), sse({"v": "chào"})]) == "Xin chào")

check("một mẩu chứa nhiều dòng data vẫn ghép đủ",
      wt.ghep_delta([sse({"v": "a"}, {"v": "b"}, {"v": "c"})]) == "abc")

check("o=append vẫn tính",
      wt.ghep_delta([sse({"o": "append", "v": "x"}, {"o": "append", "v": "y"})]) == "xy")

check("delta trỏ vào parts/0 vẫn tính",
      wt.ghep_delta([sse({"p": "/message/content/parts/0", "v": "ok"})]) == "ok")

check("delta trỏ chỗ KHÁC (metadata) thì bỏ qua, không lẫn vào câu trả lời",
      wt.ghep_delta([sse({"v": "thật"}, {"p": "/message/metadata/x", "v": "RÁC"})]) == "thật")

check("khuôn cũ: mỗi mẩu mang toàn văn -> lấy mẩu cuối, không nối chồng",
      wt.ghep_delta([sse({"message": {"content": {"parts": ["Xin"]}}}),
                     sse({"message": {"content": {"parts": ["Xin chào bạn"]}}})])
      == "Xin chào bạn")

check("[DONE] không thành chữ", "DONE" not in wt.ghep_delta([sse({"v": "a"}), "data: [DONE]\n\n"]))
check("mốc xong nội bộ không thành chữ",
      wt.ghep_delta([sse({"v": "a"}), wt.MOC_XONG]) == "a")

check("JSON hỏng giữa luồng: bỏ qua mẩu đó, KHÔNG nổ",
      wt.ghep_delta([sse({"v": "a"}), "data: {khong-phai-json\n\n", sse({"v": "b"})]) == "ab")
check("dòng không phải data: thì bỏ qua",
      wt.ghep_delta(["event: ping\n\n", sse({"v": "a"})]) == "a")
check("luồng rỗng -> chuỗi rỗng, không nổ", wt.ghep_delta([]) == "")
check("None không nổ", wt.ghep_delta(None) == "")
check("khuôn hoàn toàn lạ -> rỗng (để lớp trên báo TRANSPORT_BROKEN, không trả chữ bịa)",
      wt.ghep_delta([sse({"khuon_la": 1})]) == "")


# ============================================================
# 2) Đoạn JS tee: có đủ thứ phải có
# ============================================================

js = wt.js_tee()
check("JS tee có nhét danh sách đường dẫn cần bắt", "/backend-api/conversation" in js)
check("JS tee dùng res.body.tee(), tức KHÔNG cướp luồng của trang", ".tee()" in js)
check("JS tee trả lại Response cho trang (giao diện vẫn chạy bình thường)",
      "new Response(" in js)
check("JS tee không đụng cookie", "cookie" not in js.lower())
check("JS tee không đụng token/authorization",
      "token" not in js.lower() and "authorization" not in js.lower())
check("JS tee tự chặn chạy hai lần", "__javisTee" in js)

_src = (SERVER / "web_transport.py").read_text(encoding="utf-8")
check("mọi selector nằm trong ĐÚNG một hằng số", _src.count("SELECTORS = {") == 1)
check("có ghi phiên bản transport và selector (spec mục 22)",
      "TRANSPORT_VERSION" in _src and "SELECTOR_VERSION" in _src)
check("transport không biết gì về tool", "javis_run_command" not in _src)
check("transport không biết gì về mức quyền", "permission_mode" not in _src)
for cam in ("import main", "from main", "fastapi"):
    check(f"transport thuần, không '{cam}'", cam not in _src)


# ============================================================
# 2b) Về ĐÚNG cuộc chat trước khi gõ
# ============================================================
#
# Transport là MỘT trình duyệt dùng chung cho mọi hội thoại Javis. Thiếu bước này thì hội
# thoại B gõ tiếp vào cuộc chat mà hội thoại A vừa mở, hai mạch trộn làm một, và người dùng
# thấy Javis "nhớ" những thứ họ nói ở chỗ khác. Đây là lỗi im lặng, không có thông báo nào.

class _TrangGia:
    """Chỉ đủ bề mặt mà `_ve_dung_luong` đụng tới."""

    def __init__(self, url):
        self.url = url
        self.da_di = []

    def goto(self, url, **kw):
        self.da_di.append(url)
        self.url = url

    def evaluate(self, *a, **k):
        return None


def _di_den(url_dang_o, thread_id):
    tr = wt.ChatGPTWebTransport(profile_dir=tempfile.mkdtemp(prefix="javis-luong-"))
    tr._page = _TrangGia(url_dang_o)
    ok2, loi2 = tr._ve_dung_luong(thread_id)
    return ok2, loi2, tr._page.da_di


_ok, _loi, _di = _di_den("https://chatgpt.com/c/68d1f0a2-4c3b-4f11-9c7e-aaaaaaaaaaaa", "68d1f0a2-4c3b-4f11-9c7e-bbbbbbbbbbbb")
check("đang ở cuộc A mà cần cuộc B -> điều hướng sang B",
      _ok and _di == ["https://chatgpt.com/c/68d1f0a2-4c3b-4f11-9c7e-bbbbbbbbbbbb"])

_ok, _loi, _di = _di_den("https://chatgpt.com/c/68d1f0a2-4c3b-4f11-9c7e-aaaaaaaaaaaa", "68d1f0a2-4c3b-4f11-9c7e-aaaaaaaaaaaa")
check("đã ở đúng cuộc -> KHÔNG tải lại trang (tải lại là mất vài giây mỗi vòng)",
      _ok and _di == [])

_ok, _loi, _di = _di_den("https://chatgpt.com/c/68d1f0a2-4c3b-4f11-9c7e-aaaaaaaaaaaa", "")
check("hội thoại CHƯA có cuộc chat -> mở cuộc MỚI, không gõ tiếp vào cuộc đang hiện",
      _ok and _di == [wt.URL_GOC])

_ok, _loi, _di = _di_den(wt.URL_GOC, "")
check("đang ở trang gốc và chưa có cuộc -> không đi đâu cả", _ok and _di == [])

_ok, _loi, _di = _di_den("https://example.com/lac-duong", "")
check("lạc sang trang khác -> về trang gốc", _ok and _di == [wt.URL_GOC])

check("đọc được id cuộc chat từ URL",
      (lambda t: (setattr(t, "_page", _TrangGia("https://chatgpt.com/c/68d1f0a2-4c3b-4f11-9c7e-cccccccccccc")),
                  t.thread_hien_tai())[1])(
          wt.ChatGPTWebTransport(profile_dir=tempfile.mkdtemp(prefix="javis-id-")))
      == "68d1f0a2-4c3b-4f11-9c7e-cccccccccccc")
check("trang gốc thì id rỗng, không bịa ra một id",
      (lambda t: (setattr(t, "_page", _TrangGia(wt.URL_GOC)), t.thread_hien_tai())[1])(
          wt.ChatGPTWebTransport(profile_dir=tempfile.mkdtemp(prefix="javis-id2-"))) == "")


# ============================================================
# 3) Bật engine: TỰ DÒ, biến môi trường chỉ để ép
# ============================================================
#
# Bản 0.64.0 bắt đặt `JAVIS_ENABLE_WEB_CHAT=true` mới thấy model. Đó là bắt người dùng khai
# một thứ máy tự biết, và tệ hơn: biến đó KHÔNG tạo ra được playwright, nên máy thiếu thư
# viện mà đặt biến thì model hiện trong ô chọn rồi hỏng đúng lúc được chọn. Từ 0.64.6 câu
# trả lời đến từ việc DÒ máy, còn biến chỉ còn vai trò ép tắt.

os.environ.pop("JAVIS_ENABLE_WEB_CHAT", None)
check("chưa đặt biến -> TỰ DÒ (không mặc định tắt nữa)", wt._cong_moi_truong() is None)
for _v in ("1", "true", "YES", "on"):
    os.environ["JAVIS_ENABLE_WEB_CHAT"] = _v
    check(f"'{_v}' -> cho phép", wt._cong_moi_truong() is True)
for _v in ("0", "false", "NO", "off"):
    os.environ["JAVIS_ENABLE_WEB_CHAT"] = _v
    check(f"'{_v}' -> ép tắt", wt._cong_moi_truong() is False)
os.environ["JAVIS_ENABLE_WEB_CHAT"] = "hoi-ki-cuc"
check("giá trị lạ -> vẫn tự dò, không coi là bật", wt._cong_moi_truong() is None)

# Ép tắt phải thắng MỌI thứ, kể cả máy có đủ đồ.
os.environ["JAVIS_ENABLE_WEB_CHAT"] = "0"
wt.dat_lai_do()
_ok_tat, _ly_do_tat = wt.kha_dung()
check("ép tắt -> không khả dụng dù máy có đủ đồ", not _ok_tat)
check("câu từ chối nói rõ là do biến môi trường", "JAVIS_ENABLE_WEB_CHAT" in _ly_do_tat)

# Thiếu thư viện: câu từ chối phải NÓI ĐƯỢC VIỆC CẦN LÀM, vì nó hiện thẳng trên trang Models.
os.environ.pop("JAVIS_ENABLE_WEB_CHAT", None)
wt.dat_lai_do()
_that = __import__("builtins").__import__


def _chan_playwright(ten, *a, **k):
    if ten == "playwright" or ten.startswith("playwright."):
        raise ImportError("giả vờ chưa cài")
    return _that(ten, *a, **k)


__import__("builtins").__import__ = _chan_playwright
try:
    wt.dat_lai_do()
    _ok_tv, _ly_do_tv = wt.co_trinh_duyet()
    check("thiếu playwright -> không khả dụng", not _ok_tv)
    check("và nói đúng lệnh cần chạy", "pip install playwright" in _ly_do_tv)
finally:
    __import__("builtins").__import__ = _that
    wt.dat_lai_do()

# Có thư viện nhưng KHÔNG có trình duyệt: cũng phải từ chối, và chỉ đúng chỗ bấm.
#
# Phải DỰNG SẴN một module playwright giả khi máy chưa có, chứ không giả định máy có: CI
# chạy trên máy KHÔNG cài playwright, nên bản đầu của phép thử này rơi vào nhánh "thiếu thư
# viện" rồi đỏ vì câu lỗi nói về pip chứ không nói về trang Công cụ. Xanh trên máy dev, đỏ
# trên CI, và đỏ vì phép thử sai chứ không phải vì mã sai.
_tim_that = wt._tim_chromium
wt._tim_chromium = lambda: ""
_da_nhet_gia = False
try:
    import playwright  # noqa: F401
except ImportError:
    import types as _types
    sys.modules["playwright"] = _types.ModuleType("playwright")
    _da_nhet_gia = True
try:
    wt.dat_lai_do()
    _ok_kb, _ly_do_kb = wt.co_trinh_duyet()
    check("có playwright nhưng chưa có trình duyệt -> không khả dụng", not _ok_kb)
    check("và chỉ đúng chỗ tải trình duyệt", "Công cụ" in _ly_do_kb)
finally:
    wt._tim_chromium = _tim_that
    if _da_nhet_gia:
        sys.modules.pop("playwright", None)
    wt.dat_lai_do()

# Nhớ kết quả dò, và quên được khi người dùng vừa cài thêm đồ.
wt.dat_lai_do()
wt._NHO_DO["kq"] = (True, "")
wt._tim_chromium = lambda: ""
try:
    check("có nhớ kết quả dò (không quét đĩa mỗi lần vẽ trang)", wt.co_trinh_duyet()[0])
    wt.dat_lai_do()
    check("dat_lai_do() quên kết quả cũ, dò lại từ đầu", not wt.co_trinh_duyet()[0])
finally:
    wt._tim_chromium = _tim_that
    wt.dat_lai_do()

os.environ["JAVIS_ENABLE_WEB_CHAT"] = "true"
wt.dat_lai_do()


# ============================================================
# 4) Tee chạy THẬT trong Chromium, trên trang tĩnh tự phát SSE
# ============================================================

def _tim_chrome():
    import glob
    for m in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
              "/opt/pw-browsers/chromium-*/chrome-win/chrome.exe"):
        h = sorted(glob.glob(m))
        if h:
            return h[-1]
    return ""


try:
    from playwright.sync_api import sync_playwright
    _co_pw = True
except ImportError:
    _co_pw = False

_chrome = _tim_chrome()

if not _co_pw or not _chrome:
    print("bỏ qua tầng Chromium: "
          + ("thiếu playwright" if not _co_pw else "không tìm thấy Chromium"))
    print("   (tầng THUẦN ở trên đã phủ phần logic; tầng này chỉ chứng minh đoạn JS chạy thật)")
else:
    THAN = (sse({"v": "Xin "}) + sse({"v": "chào "}) + sse({"v": "anh"})
            + "data: [DONE]\n\n")

    class _Tay(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/backend-api/conversation"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for dong in THAN.split("\n\n"):
                    if dong.strip():
                        self.wfile.write((dong + "\n\n").encode())
                        self.wfile.flush()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>trang gia</h1></body></html>")

    with socketserver.TCPServer(("127.0.0.1", 0), _Tay) as srv:
        cong = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        prof = tempfile.mkdtemp(prefix="javis-pw-")
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                prof, headless=True, executable_path=_chrome)
            try:
                ctx.add_init_script(wt.js_tee())
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(f"http://127.0.0.1:{cong}/", wait_until="domcontentloaded")

                # Trang tự gọi fetch, đúng như chatgpt.com làm khi gửi tin nhắn. Đọc HẾT body
                # để chứng minh nhánh của trang vẫn nguyên vẹn.
                da_doc = page.evaluate(
                    """async () => {
                        const r = await fetch('/backend-api/conversation');
                        return await r.text();
                    }"""
                )
                check("nhánh của TRANG vẫn đọc được nguyên vẹn (tee không cướp luồng)",
                      "Xin " in da_doc and "[DONE]" in da_doc)

                for _ in range(40):
                    chunks = page.evaluate("window.__javisChunks || []")
                    if chunks and chunks[-1] == wt.MOC_XONG:
                        break
                    page.wait_for_timeout(100)
                chunks = page.evaluate("window.__javisChunks || []")

                check("nhánh của JAVIS bắt được luồng", len(chunks) > 0)
                check("có mốc kết thúc", chunks and chunks[-1] == wt.MOC_XONG)
                check("ghép lại ra ĐÚNG NGUYÊN VĂN câu trả lời",
                      wt.ghep_delta(chunks) == "Xin chào anh")

                # Request KHÔNG phải đường luồng thì không được tee.
                page.evaluate("window.__javisChunks = []")
                page.evaluate("async () => { await fetch('/khong-phai-luong'); }")
                page.wait_for_timeout(300)
                check("request ngoài danh sách đường dẫn KHÔNG bị tee",
                      page.evaluate("(window.__javisChunks || []).length") == 0)
            finally:
                ctx.close()
        srv.shutdown()

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_web_transport_tee: tất cả pass")
