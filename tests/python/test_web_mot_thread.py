"""Mọi lời gọi Playwright đi qua ĐÚNG MỘT thread, và nhóm /web-chat đòi phiên đăng nhập thật.

    python tests/run.py mot_thread

File này là phần còn sống của test_web_dang_nhap_qua_dashboard.py. Bản 0.64.12 bỏ màn đăng
nhập chụp màn hình (xem CHANGELOG), nên mấy tầng kiểm chụp/bấm/gõ đi theo nó. Hai tầng dưới
đây thì KHÔNG dính gì tới màn đó và vẫn khoá những thứ hỏng im lặng:

  1. **Một thread cố định.** Playwright bản đồng bộ bám vào greenlet của đúng thread đã khởi
     tạo nó. Đây là lỗi THẬT của bản 0.64.0, đã dựng lại bằng thí nghiệm: `asyncio.to_thread`
     dùng lại một thread khi các lời gọi nối đuôi nhau, nhưng hai request CHỒNG NHAU thì rơi
     sang thread khác và chết `greenlet.error: Cannot switch to a different thread`.
  2. **Cổng vào.** Nhóm `/web-chat` mở trình duyệt trên máy chủ và nhận cookie phiên ChatGPT
     của chủ máy, nên nó đòi PHIÊN ĐĂNG NHẬP THẬT chứ không nhận API token như hàng rào chung.
     "Một script có token cũng lái được phiên ChatGPT của chủ máy" là thứ không nên có đường
     tồn tại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import threading

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-mt-"))

import web_transport as wt  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def _tr():
    return wt.ChatGPTWebTransport(profile_dir=tempfile.mkdtemp(prefix="javis-mt-p-"))


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
      all(f"def _{x}_that(" in _src for x in ("mo", "dong", "gui", "nap_cookie")))
check("vỏ công khai `gui` đi qua _chay chứ không gọi thẳng",
      "self._chay(self._gui_that" in _src)
check("có ghi lại vì sao phải một thread (greenlet)", "greenlet" in _src)

check("mặc định chạy ẨN (VPS không có màn hình nào để hiện cửa sổ)",
      wt.ChatGPTWebTransport().headless is True)
check("khung nhìn cố định (selector viết theo bố cục rộng)",
      isinstance(wt.KHUNG, dict) and wt.KHUNG["width"] >= 1024)


# ============================================================
# 2) Cổng vào: chỉ phiên đăng nhập THẬT, không nhận API token
# ============================================================

_m = (SERVER / "main.py").read_text(encoding="utf-8")
check("có cổng riêng cho nhóm /web-chat", "def _web_chat_chan(" in _m)
check("cổng đó soi cookie phiên", "cfgmod.valid_session(request.cookies" in
      _m[_m.index("def _web_chat_chan("):_m.index("def _web_chat_chan(") + 900])

# Quét ĐỘNG: mọi đường /web-chat có trong mã nguồn đều phải qua cổng. Liệt kê tay thì thêm
# một endpoint mới là nó lọt lưới im lặng, đúng kiểu sai sót không ai phát hiện ra.
import re  # noqa: E402

_duong = sorted(set(re.findall(r'@app\.(?:get|post)\("(/web-chat/[a-z-]+)"\)', _m)))
check(f"tìm thấy các đường /web-chat: {_duong}", len(_duong) >= 3)
for _ep in _duong:
    _i = _m.index(f'"{_ep}"')
    check(f"{_ep} có gọi cổng chặn", "_web_chat_chan(request)" in _m[_i:_i + 1600])


# ============================================================
# 3) Màn đăng nhập chụp màn hình đã đi hẳn
# ============================================================
#
# Bỏ một tính năng mà để sót một nửa thì nửa đó chết âm thầm: endpoint còn mà giao diện không
# gọi nữa, hoặc ngược lại. Mấy phép dưới đây canh đúng chuyện đó.

for _x in ("/web-chat/login", "/web-chat/screen", "/web-chat/input"):
    check(f"endpoint {_x} đã bỏ", _x not in _m)
for _x in ("def mo_dang_nhap", "def thao_tac", "def chup", "def _bam_that", "def _go_that"):
    check(f"transport: {_x} đã bỏ", _x not in _src)

_js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
for _x in ("moManDangNhap", "webManHinh", "data-weblogin", "/web-chat/screen"):
    check(f"dashboard: {_x} đã bỏ", _x not in _js)

# Và đường CÒN LẠI phải luôn nhìn thấy được. Nút cũ bị giấu sau `kha_dung` nên đúng lúc chủ
# máy cần nó nhất thì nó không có ở đó (22/09). Đường duy nhất còn lại mà lặp lại lỗi ấy thì
# thẻ ChatGPT thành một cái ngõ cụt.
_khoi = _js[_js.index("async function veThreChatGPTWeb"):]
_khoi = _khoi[:_khoi.index("async function renderModelsCloudTab")]
# 0.64.13 bỏ khối <details> bọc ngoài (thẻ gọn lại, xem test_trang_code_dien_thoai.js), nên
# soi thẳng ô nhập. Bất biến giữ nguyên và vẫn là bất biến đáng giữ nhất ở đây: ô dán cookie
# là đường đăng nhập DUY NHẤT còn lại, giấu nó sau `kha_dung` là lặp lại đúng lỗi đã khiến
# chủ repo mắc kẹt với cái nút cũ.
_i_ck = _khoi.index('id="webCookie"')
_truoc = _khoi[max(0, _i_ck - 260):_i_ck]
check("ô dán cookie KHÔNG bị giấu sau điều kiện kha_dung",
      "kha_dung" not in _truoc, _truoc[-120:])
check("nhưng thẻ vẫn nói rõ khi máy chưa đủ đồ", "kha_dung" in _khoi)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_web_mot_thread: tất cả pass")
