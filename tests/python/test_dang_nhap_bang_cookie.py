"""Đăng nhập ChatGPT Web bằng cookie dán từ trình duyệt đã đăng nhập sẵn.

    python tests/run.py cookie

Chủ repo hỏi 22/09: "sao cách xử lý cồng kềnh vậy, dán cookie như MCP Substack không được à".
Câu trả lời quyết định cả thiết kế, nên chép lại đây:

  Substack không có lớp chống bot trước API - có cookie là gọi API được, hết. chatgpt.com có
  hai lớp nữa, và CẢ HAI đều không mang cookie sang máy khác được:
    1. Cloudflare buộc `cf_clearance` vào IP + User-Agent + chữ ký TLS của máy đã giải thử thách.
    2. Sentinel của OpenAI đòi token proof-of-work do JavaScript TRONG TRANG tự tính.
  Trình duyệt thật giải cả hai miễn phí, nên trình duyệt PHẢI ở lại.

  Nhưng cookie PHIÊN thì không buộc vào IP. Nên cắt được phần nặng nhất về trải nghiệm: màn
  đăng nhập chụp màn hình, và mật khẩu đi qua máy chủ Javis.

Ba tầng:
  1. Đọc thứ người dùng dán: ba định dạng, và các nhánh từ chối phải nói được.
  2. Bí mật: giá trị cookie KHÔNG được ghi ra log hay vọng lại câu trả về.
  3. Chạy THẬT trong Chromium: nạp cookie vào một trang tĩnh rồi đọc lại đúng cookie đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import http.server
import os
import re
import socketserver
import sys
import tempfile
import threading

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ck-"))

import web_transport as wt  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


TOKEN = "eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..gia-lap-token"


# ============================================================
# 1) Đọc ba kiểu dán
# ============================================================
#
# Ba kiểu vì người dùng lấy cookie bằng ba đường khác nhau và không ai nhớ mình đang cầm kiểu
# nào. Bắt họ đoán đúng định dạng là dựng thêm một bước thất bại không cần tồn tại.

_ck, _loi = wt.doc_cookie(TOKEN)
check("dán MỖI giá trị token -> hiểu là cookie phiên", not _loi and len(_ck) == 1, _loi)
check("và gắn đúng tên cookie", _ck and _ck[0]["name"] == wt.TEN_COOKIE_PHIEN)
check("và đúng miền chatgpt.com", _ck and _ck[0]["domain"] == wt.MIEN_COOKIE)
check("và giữ NGUYÊN VĂN giá trị", _ck and _ck[0]["value"] == TOKEN)
# `secure` KHÔNG phải cho đẹp: Chrome cưỡng chế tiền tố `__Secure-` trong tên cookie và từ
# chối thẳng cookie nào mang tên đó mà thiếu cờ này ("Invalid cookie fields"). Đặt sai là cả
# đường đăng nhập bằng cookie chết, mà câu lỗi thì không nhắc gì tới tiền tố.
check("đánh dấu secure + httpOnly (cookie phiên thật cũng vậy)",
      _ck and _ck[0]["secure"] and _ck[0]["httpOnly"])
check("mọi cookie dựng ra đều secure (tiền tố __Secure- đòi vậy)",
      all(c["secure"] for c in wt.doc_cookie(f"a=1; {wt.TEN_COOKIE_PHIEN}={TOKEN}")[0]))

_ck, _loi = wt.doc_cookie(f"  {TOKEN}\n ")
check("thừa khoảng trắng và xuống dòng -> vẫn đọc được",
      not _loi and _ck[0]["value"] == TOKEN, _loi)

_ck, _loi = wt.doc_cookie(f'oai-did=abc; {wt.TEN_COOKIE_PHIEN}={TOKEN}; _ga=GA1.1.9')
check("dán CẢ CHUỖI cookie -> tách ra đủ", not _loi and len(_ck) == 3, _loi)
check("và tìm đúng cookie phiên trong đám đó",
      any(c["name"] == wt.TEN_COOKIE_PHIEN and c["value"] == TOKEN for c in _ck))

_json = ('[{"name":"oai-did","value":"abc"},'
         f'{{"name":"{wt.TEN_COOKIE_PHIEN}","value":"{TOKEN}"}}]')
_ck, _loi = wt.doc_cookie(_json)
check("dán JSON xuất từ tiện ích cookie -> đọc được", not _loi and len(_ck) == 2, _loi)
check("JSON: giá trị token đúng nguyên văn",
      any(c["value"] == TOKEN for c in _ck))

_ck, _loi = wt.doc_cookie('{"name":"%s","value":"%s"}' % (wt.TEN_COOKIE_PHIEN, TOKEN))
check("JSON một object (không bọc mảng) -> vẫn nhận", not _loi and len(_ck) == 1, _loi)


# ============================================================
# 1b) Từ chối phải NÓI ĐƯỢC PHẢI LÀM GÌ
# ============================================================

check("dán rỗng -> nói rõ", wt.doc_cookie("")[1] and wt.doc_cookie("   ")[1])

_, _loi = wt.doc_cookie('[{"name":')
check("JSON gãy -> nói là copy thiếu chứ không nôn stack trace",
      "JSON" in _loi and "Traceback" not in _loi, _loi)

_, _loi = wt.doc_cookie("oai-did=abc; _ga=GA1.1.9")
check("có cookie nhưng THIẾU cookie phiên -> gọi tên cookie còn thiếu",
      wt.TEN_COOKIE_PHIEN in _loi, _loi)

# cf_clearance là cái bẫy đáng nói riêng: người dùng copy cả đám cookie thì nó đi theo, mà nó
# buộc vào IP + User-Agent + chữ ký TLS của máy đã giải thử thách. Nhét bản của máy khác vào
# KHÔNG vô hại - Cloudflare thấy vé không khớp và chặn, trong khi Chromium ở đây thừa sức tự
# xin vé đúng của mình nếu ta để yên.
_ck, _loi = wt.doc_cookie(f"cf_clearance=xyz; {wt.TEN_COOKIE_PHIEN}={TOKEN}")
check("cookie buộc vào IP bị BỎ, không mang sang",
      not _loi and not any(c["name"] == "cf_clearance" for c in _ck), _loi)
check("nhưng cookie phiên vẫn giữ", any(c["name"] == wt.TEN_COOKIE_PHIEN for c in _ck))

_, _loi = wt.doc_cookie("cf_clearance=xyz; __cf_bm=abc")
check("dán MỖI cookie buộc IP -> giải thích vì sao vô dụng, không im lặng báo thành công",
      "IP" in _loi, _loi)

check("danh sách bỏ qua có đủ họ cookie Cloudflare",
      set(wt.COOKIE_BO_QUA) >= {"cf_clearance", "__cf_bm"})


# ============================================================
# 2) Bí mật: cookie mạnh ngang mật khẩu
# ============================================================

_src = (SERVER / "web_transport.py").read_text(encoding="utf-8")
_than = _src[_src.index("def doc_cookie"):_src.index("def _tim_chromium")]
check("hàm đọc cookie KHÔNG in ra gì", not re.search(r"\bprint\(", _than))

_i = _src.index("def _nap_cookie_that")
_nap = _src[_i:_src.index("\n    # ----", _i)]
check("hàm nạp cookie KHÔNG in ra gì", not re.search(r"\bprint\(", _nap))
check("nạp cookie XOÁ cookie cũ trước (kẻo trang chạy bằng phiên cũ mà tưởng cookie mới ăn)",
      "clear_cookies()" in _nap)

_m = (SERVER / "main.py").read_text(encoding="utf-8")
_ep = _m[_m.index('@app.post("/web-chat/cookie")'):]
_ep = _ep[:_ep.index("\n@app.")]
check("endpoint cookie KHÔNG in ra gì", not re.search(r"\bprint\(", _ep))
check("endpoint KHÔNG vọng lại giá trị cookie trong câu trả về",
      '"cookie"' not in _ep.split("return {")[-1])
check("endpoint có ghi rõ luật không lưu cookie", "KHÔNG ghi giá trị cookie" in _ep)
check("endpoint đi qua cổng chặn đòi phiên đăng nhập thật",
      "_web_chat_chan(request)" in _ep)
check("và vẫn hỏi trình duyệt có sẵn sàng không trước khi làm gì",
      "web_transport.kha_dung()" in _ep)

_js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
_khuc = _js[_js.index("data-webcookie"):]
_khuc = _khuc[:_khuc.index("goi(\"[data-webreset]")] if "goi(\"[data-webreset]" in _khuc else _khuc
check("màn hình xoá ô nhập sau khi gửi, cả khi hỏng",
      "o.value = \"\"" in _khuc)
check("màn hình KHÔNG nhét cookie vào localStorage",
      "localStorage" not in _khuc)


# ============================================================
# 3) Chạy THẬT trong Chromium: cookie nạp vào có tới nơi không
# ============================================================
#
# Hai tầng trên soi hình dạng dữ liệu. Tầng này trả lời câu duy nhất người dùng quan tâm:
# dán cookie vào thì trang có NHẬN không. Dùng một trang tĩnh chạy trên máy, không cần tài
# khoản ChatGPT và không cần mạng ra ngoài.

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
else:
    class _Tay(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>trang gia lap</body></html>")

    with socketserver.TCPServer(("127.0.0.1", 0), _Tay) as srv:
        cong = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        tr = wt.ChatGPTWebTransport(profile_dir=tempfile.mkdtemp(prefix="javis-ck-p-"),
                                    headless=True, executable_path=_chrome,
                                    url=f"http://127.0.0.1:{cong}/")
        try:
            # Miền phải khớp trang đang mở, nếu không Chromium vứt cookie đi.
            #
            # `secure: True` là BẮT BUỘC, không phải cho đẹp: Chrome cưỡng chế tiền tố
            # `__Secure-` trong tên cookie, thiếu cờ đó là nó từ chối thẳng với câu
            # "Invalid cookie fields". Chính tầng này bắt được lỗi đó khi bản nháp đặt False,
            # và đấy là lý do tầng chạy thật đáng có - hai tầng trên đọc hình dạng dữ liệu
            # nên không bao giờ thấy luật này. http://127.0.0.1 vẫn nhận cookie Secure vì
            # Chrome coi localhost là nguồn đáng tin.
            ck = [{"name": wt.TEN_COOKIE_PHIEN, "value": TOKEN, "domain": "127.0.0.1",
                   "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax"}]
            da_dn, loi = tr.nap_cookie(ck)
            check("nạp cookie không nổ", loi == "", loi)
            # Trang giả lập không có ô soạn của ChatGPT nên `da_dang_nhap` phải là False. Đó là
            # điều ĐÚNG: nó chứng minh Javis không báo bừa đã đăng nhập chỉ vì cookie nạp trót lọt.
            check("KHÔNG báo bừa đã đăng nhập khi trang không có dấu hiệu đăng nhập", da_dn is False)

            thay = tr._chay(lambda: {c["name"]: c["value"] for c in tr._ctx.cookies()})
            check("trình duyệt THẬT SỰ giữ cookie vừa nạp", wt.TEN_COOKIE_PHIEN in thay, list(thay))
            check("và giữ đúng nguyên văn giá trị", thay.get(wt.TEN_COOKIE_PHIEN) == TOKEN)

            # Nạp lần hai phải thay thế, không chồng lên.
            tr.nap_cookie([dict(ck[0], value=TOKEN + "-moi")])
            thay2 = tr._chay(lambda: [c for c in tr._ctx.cookies()
                                      if c["name"] == wt.TEN_COOKIE_PHIEN])
            check("nạp lần hai -> đúng MỘT cookie phiên, không chồng hai cái", len(thay2) == 1, thay2)
            check("và là giá trị MỚI", thay2 and thay2[0]["value"] == TOKEN + "-moi")
        finally:
            tr.dong()
        srv.shutdown()

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_dang_nhap_bang_cookie: tất cả pass")
