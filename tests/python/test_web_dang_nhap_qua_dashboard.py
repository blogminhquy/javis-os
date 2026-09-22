"""Đăng nhập ChatGPT nhìn qua dashboard, để engine Web chạy được trên VPS không màn hình.

    python tests/run.py web_dang_nhap

Vì sao có màn này: bản 0.64.6 mở một cửa sổ Chromium THẬT cho chủ máy gõ mật khẩu. Đúng về
mặt giữ bí mật, nhưng nó khiến cả tính năng không dùng được trên VPS - nơi không có màn hình
nào để mở cửa sổ. Nay Javis chụp trang gửi lên dashboard và chuyển ngược cú bấm với phím gõ
xuống, nên chủ máy thao tác lên ĐÚNG trang ChatGPT thật mà máy chủ không cần màn hình.

Đánh đổi chủ repo đã duyệt (22/09): phím gõ, gồm cả mật khẩu, đi qua máy chủ Javis. Đây là máy
cá nhân của chính họ, nơi đã giữ token OAuth và khoá kết nối. Hai hệ quả phải khoá bằng test:
KHÔNG ghi nội dung phím ở bất kỳ đâu, và đường vào đòi PHIÊN ĐĂNG NHẬP THẬT chứ không nhận
API token như hàng rào chung.

Ba tầng phép thử:
  1. **Một thread cố định.** Playwright bản đồng bộ bám vào greenlet của đúng thread đã khởi
     tạo nó. Đây là lỗi THẬT của bản trước, đã dựng lại bằng thí nghiệm: `asyncio.to_thread`
     dùng lại một thread khi các lời gọi nối đuôi nhau, nhưng hai request CHỒNG NHAU thì rơi
     sang thread khác và chết `greenlet.error: Cannot switch to a different thread`. Màn đăng
     nhập vừa chụp màn hình vừa nhận phím nên luôn gọi chồng nhau.
  2. **Thuần:** phân loại thao tác, từ chối khi chưa mở trang hoặc đang bận.
  3. **Chạy THẬT trong Chromium:** chụp được ảnh, bấm và gõ vào một trang tĩnh rồi đọc lại
     đúng thứ vừa gõ. Không cần tài khoản ChatGPT, không cần mạng ra ngoài.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import http.server
import os
import socketserver
import sys
import tempfile
import threading

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-wdn-"))
os.environ["JAVIS_ENABLE_WEB_CHAT"] = "true"

import web_transport as wt  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def _tr():
    return wt.ChatGPTWebTransport(profile_dir=tempfile.mkdtemp(prefix="javis-wdn-p-"))


# ============================================================
# 1) MỘT thread cố định cho mọi lời gọi Playwright
# ============================================================

t = _tr()
check("transport có máy chạy riêng", t._may is not None)
check("ĐÚNG MỘT worker (nhiều hơn là quay lại đúng lỗi cũ)", t._may._max_workers == 1)

_threads = set()


def _ghi_ten():
    _threads.add(threading.current_thread().name)
    return len(_threads)


for _ in range(8):
    t._chay(_ghi_ten)
check("tám lời gọi liên tiếp chạy trên CÙNG một thread", len(_threads) == 1, _threads)

# Gọi CHỒNG NHAU: đây là cảnh làm bản cũ chết. Máy một worker phải xếp hàng chứ không toé ra
# nhiều thread.
_threads.clear()
_loi = []


def _goi_lau():
    try:
        t._chay(_ghi_ten)
    except Exception as e:
        _loi.append(e)


_ts = [threading.Thread(target=_goi_lau) for _ in range(6)]
[x.start() for x in _ts]
[x.join() for x in _ts]
check("sáu lời gọi SONG SONG vẫn dồn về một thread", len(_threads) == 1, _threads)
check("và không lời gọi nào nổ", not _loi, _loi[:1])

_src = (SERVER / "web_transport.py").read_text(encoding="utf-8")
check("mọi hàm chạm Playwright đều có bản _that đi qua máy",
      all(f"def _{x}_that(" in _src for x in ("mo", "dong", "gui", "chup", "bam", "go", "phim")))
check("vỏ công khai `gui` đi qua _chay chứ không gọi thẳng",
      "self._chay(self._gui_that" in _src)
check("có ghi lại vì sao phải một thread (greenlet)", "greenlet" in _src)


# ============================================================
# 2) Thuần: từ chối đúng lúc, không nổ
# ============================================================

check("chưa mở trang -> chụp trả lý do nói được", _tr().chup() == (b"", "Chưa mở trình duyệt."))
check("chưa mở trang -> thao tác cũng từ chối",
      "Chưa mở" in _tr().thao_tac("bam", x=1, y=1))

t2 = _tr()
t2._page = object()          # giả vờ đã mở để qua cửa đầu
check("thao tác lạ -> nói rõ không có thao tác đó",
      "không có thao tác" in t2.thao_tac("nhay-mua").lower())
check("bốn thao tác thật đều được nhận (không rơi vào nhánh lạ)",
      all("không có thao tác" not in (t2.thao_tac(x) or "").lower()
          for x in ("bam", "go", "phim", "cuon")))

t2._khoa.acquire()
try:
    check("đang có lượt chat chạy dở -> KHÔNG chụp (không chen vào giữa lượt)",
          "đang có một lượt chat" in t2.chup()[1].lower())
    check("đang có lượt chat chạy dở -> KHÔNG nhận thao tác",
          "đang có một lượt chat" in t2.thao_tac("bam", x=1, y=1).lower())
finally:
    t2._khoa.release()

check("khung nhìn CỐ ĐỊNH (toạ độ cú bấm mới quy đổi được)",
      isinstance(wt.KHUNG, dict) and wt.KHUNG["width"] > 0 and wt.KHUNG["height"] > 0)
check("mặc định chạy ẨN (VPS không có màn hình nào để hiện cửa sổ)",
      wt.ChatGPTWebTransport().headless is True)


# ============================================================
# 3) KHÔNG ghi lại thứ người dùng gõ
# ============================================================
#
# Mật khẩu ChatGPT đi qua đây. Một dòng print gỡ lỗi sót lại là mật khẩu nằm trong log máy chủ.

import re  # noqa: E402

_than_go = _src[_src.index("def _go_that"):_src.index("def _phim_that")]
check("hàm gõ chữ KHÔNG in ra gì", not re.search(r"\bprint\(", _than_go))
check("hàm gõ chữ KHÔNG giữ lại chuỗi vừa gõ",
      "self._da_go" not in _than_go and "append" not in _than_go)

_m = (SERVER / "main.py").read_text(encoding="utf-8")
_than_ep = _m[_m.index('@app.post("/web-chat/input")'):]
_than_ep = _than_ep[:_than_ep.index("\n@app.")] if "\n@app." in _than_ep else _than_ep
check("endpoint nhận phím KHÔNG in ra gì", not re.search(r"\bprint\(", _than_ep))
check("endpoint nhận phím KHÔNG vọng lại thứ vừa gõ trong câu trả về",
      '"chu"' not in _than_ep.split("return")[-1])
check("có ghi rõ luật không ghi nhật ký phím", "KHÔNG ghi lại nội dung phím" in _m)


# ============================================================
# 4) Bảo mật: chỉ phiên đăng nhập THẬT, không nhận API token
# ============================================================

check("có cổng riêng cho nhóm /web-chat", "def _web_chat_chan(" in _m)
check("cổng đó soi cookie phiên", "cfgmod.valid_session(request.cookies" in
      _m[_m.index("def _web_chat_chan("):_m.index("def _web_chat_chan(") + 900])
for _ep in ("/web-chat/status", "/web-chat/login", "/web-chat/check", "/web-chat/reset",
            "/web-chat/screen", "/web-chat/input"):
    _i = _m.index(f'"{_ep}"')
    _khuc = _m[_i:_i + 1600]
    check(f"{_ep} có gọi cổng chặn", "_web_chat_chan(request)" in _khuc)


# ============================================================
# 5) Chạy THẬT trong Chromium: chụp, bấm, gõ
# ============================================================

def _tim_chrome():
    import glob
    for m in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
              "/opt/pw-browsers/chromium*/chrome-linux/headless_shell"):
        h = sorted(glob.glob(m))
        if h:
            return h[-1]
    return ""


try:
    import playwright  # noqa: F401
    _co_pw = True
except ImportError:
    _co_pw = False
_chrome = _tim_chrome()

if not _co_pw or not _chrome:
    print("bỏ qua tầng Chromium: " + ("thiếu playwright" if not _co_pw else "không thấy Chromium"))
    print("   (ba tầng trên đã phủ phần logic; tầng này chứng minh chụp/bấm/gõ chạy thật)")
else:
    TRANG = b"""<html><body style="margin:0">
      <input id="o" style="position:absolute;left:40px;top:60px;width:400px;height:40px;font-size:20px">
      <div id="ra" style="position:absolute;left:40px;top:140px;font-size:20px">chua-bam</div>
      <script>document.getElementById('o').addEventListener('focus',
        () => document.getElementById('ra').textContent = 'da-bam');</script>
    </body></html>"""

    class _Tay(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(TRANG)

    with socketserver.TCPServer(("127.0.0.1", 0), _Tay) as srv:
        cong = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        tr = wt.ChatGPTWebTransport(profile_dir=tempfile.mkdtemp(prefix="javis-wdn-r-"),
                                    headless=True, executable_path=_chrome,
                                    url=f"http://127.0.0.1:{cong}/")
        try:
            ok, ly_do = tr.mo_dang_nhap()
            check("mở được trang mà KHÔNG cần màn hình (headless)", ok, ly_do)
            if ok:
                anh, loi = tr.chup()
                check("chụp được khung hình", len(anh) > 500, loi)
                check("ảnh đúng là JPEG", anh[:2] == b"\xff\xd8")

                check("bấm vào ô nhập: không lỗi", tr.thao_tac("bam", x=200, y=80) == "")
                check("ô nhập NHẬN được cú bấm (toạ độ khớp khung)",
                      tr._chay(lambda: tr._page.inner_text("#ra")) == "da-bam")

                check("gõ chữ: không lỗi", tr.thao_tac("go", chu="Xin chào 123") == "")
                check("trang nhận ĐÚNG NGUYÊN VĂN chữ vừa gõ, kể cả tiếng Việt có dấu",
                      tr._chay(lambda: tr._page.input_value("#o")) == "Xin chào 123")

                check("nhấn phím điều khiển: không lỗi", tr.thao_tac("phim", ten="Backspace") == "")
                check("Backspace xoá đúng một ký tự",
                      tr._chay(lambda: tr._page.input_value("#o")) == "Xin chào 12")

                check("cuộn: không lỗi", tr.thao_tac("cuon", dy=100) == "")
                check("khung ảnh đúng kích thước đã khai",
                      tr._chay(lambda: tr._page.viewport_size) == wt.KHUNG)
        finally:
            tr.dong()
        srv.shutdown()

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_web_dang_nhap_qua_dashboard: tất cả pass")
