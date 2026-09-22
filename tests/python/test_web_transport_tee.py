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
# 3) Cổng môi trường: tắt thì engine tự ẩn
# ============================================================

os.environ.pop("JAVIS_ENABLE_WEB_CHAT", None)
ok, ly_do = wt.kha_dung()
check("chưa bật cổng môi trường -> không khả dụng", not ok)
check("câu từ chối chỉ đúng biến cần bật", "JAVIS_ENABLE_WEB_CHAT" in ly_do)
os.environ["JAVIS_ENABLE_WEB_CHAT"] = "true"


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
