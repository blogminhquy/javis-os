"""Tải Chromium xong thì MỌI chỗ trong Javis phải thấy nó.

    python tests/run.py do_trinh_duyet

Lỗi thật, chủ repo báo 22/09 kèm ảnh hai trang cãi nhau trên CÙNG một máy:

    trang Công cụ  ->  "Trình duyệt (Chromium)  ● Sẵn sàng  · 260 MB"
    trang Models   ->  "Chưa có trình duyệt nào Javis lái được. Mở trang Công cụ rồi bấm tải"

Hệ quả không nhìn thấy ngay: nút "Đăng nhập ChatGPT" chỉ vẽ khi engine Web báo dùng được, nên
chủ repo tải đủ 400 MB rồi vẫn không có chỗ nào bấm để kết nối.

Nguyên nhân: MỘT lệnh `playwright install chromium` để lại HAI thư mục, và hai file chạy mang
TÊN KHÁC NHAU (đã soi bản Playwright thật trong container này):

    chromium-1194/chrome-linux/chrome
    chromium_headless_shell-1194/chrome-linux/headless_shell

Bản cũ lấy thư mục đầu tiên `iterdir()` đưa ra - thứ tự trên đĩa, không sắp xếp - rồi chỉ tìm
mỗi tên `chrome`. Rơi vào thư mục headless_shell là không thấy gì. Trang Công cụ thì chỉ hỏi
"có thư mục không" nên vẫn báo xong. Không bên nào sai theo logic của chính nó, và đó đúng là
lý do phải gộp về một nguồn thay vì vá từng bên.

Bất biến phải giữ, viết dưới dạng một câu:
**trang Công cụ báo "Sẵn sàng" khi và chỉ khi engine Web lái được.**
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-dotd-")

import optional_tools as ot  # noqa: E402
import web_transport as wt  # noqa: E402

# Engine Web cần HAI thứ: thư viện `playwright` và một trình duyệt. File này nói về thứ THỨ
# HAI. Máy CI cố ý không cài playwright (46 MB tải về cho một thứ phần lớn máy không dùng), nên
# ở đó `co_trinh_duyet()` luôn False vì lý do KHÁC hẳn. Trộn hai thứ vào một phép so là phép
# thử đỏ trên CI mà xanh ở máy dev - đúng cái bẫy đã sập ở lần đẩy đầu.
try:
    import playwright  # noqa: F401
    CO_PW = True
except ImportError:
    CO_PW = False

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def _dung(*cac_ban):
    """Dựng lại BROWSERS_DIR với đúng các thư mục build được kê, trả về đường dẫn mong đợi."""
    import shutil
    shutil.rmtree(ot.BROWSERS_DIR, ignore_errors=True)
    for ten, binary in cac_ban:
        p = ot.BROWSERS_DIR / ten / binary
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    wt.dat_lai_do()


DAY_DU = ("chromium-1194", "chrome-linux/chrome")
RUT_GON = ("chromium_headless_shell-1194", "chrome-linux/headless_shell")


# ============================================================
# 1) Cảnh của chủ repo: một lệnh cài, hai thư mục
# ============================================================

_dung(DAY_DU, RUT_GON)
_mong = str(ot.BROWSERS_DIR / "chromium-1194" / "chrome-linux" / "chrome")

check("tìm ra file chạy được", ot.duong_dan_chrome() == _mong, ot.duong_dan_chrome())
check("ưu tiên bản ĐẦY ĐỦ, không phải bản headless rút gọn",
      "headless_shell" not in ot.duong_dan_chrome())
check("engine Web tìm ra ĐÚNG file đó", wt._tim_chromium() == _mong, wt._tim_chromium())
check("trang Công cụ báo Sẵn sàng", ot.trang_thai("browser")["trang_thai"] == "san_sang")
if CO_PW:
    check("engine Web lái được", wt.co_trinh_duyet(dung_nho=False) == (True, ""))
else:
    # Máy không có thư viện: engine vẫn phải từ chối, nhưng vì ĐÚNG lý do. Báo nhầm là thiếu
    # trình duyệt thì người dùng đi tải thêm 400 MB nữa mà vẫn không chạy được.
    check("thiếu thư viện -> nói thiếu THƯ VIỆN, không đổ cho trình duyệt",
          "thư viện" in wt.co_trinh_duyet(dung_nho=False)[1].lower())

# CANARY: dựng lại ĐÚNG thuật toán cũ và chứng minh nó ra rỗng trên chính cảnh này. Không có
# mục này thì phép thử trên chỉ nói "hiện tại chạy được", không nói nó từng hỏng ở đâu.
def _ban_cu():
    thu_muc = ""
    for d in ot.BROWSERS_DIR.iterdir():          # KHÔNG sắp xếp, y như bản cũ
        if d.is_dir() and d.name.startswith("chromium"):
            thu_muc = str(d)
            break
    if not thu_muc:
        return ""
    for ten in ("chrome-linux/chrome", "chrome-win/chrome.exe",
                "chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
        if (Path(thu_muc) / ten).is_file():
            return str(Path(thu_muc) / ten)
    return ""


# Thứ tự iterdir phụ thuộc đĩa nên bản cũ hỏng KHÔNG CHẮC CHẮN. Ép nó vào đúng nhánh xấu bằng
# cách bỏ hẳn bản đầy đủ đi: lúc đó bản cũ SAI CHẮC CHẮN, còn bản mới vẫn phải chạy.
_dung(RUT_GON)
check("CANARY: bản cũ mù trước thư mục headless_shell", _ban_cu() == "")
check("chỉ có bản rút gọn -> bản mới VẪN tìm ra file chạy",
      ot.duong_dan_chrome().endswith("headless_shell"), ot.duong_dan_chrome())
check("chỉ có bản rút gọn -> engine Web vẫn tìm ra file chạy",
      wt._tim_chromium().endswith("headless_shell"), wt._tim_chromium())
check("chỉ có bản rút gọn -> trang Công cụ vẫn Sẵn sàng",
      ot.trang_thai("browser")["trang_thai"] == "san_sang")


# ============================================================
# 1b) BỐ CỤC LẠ: quét tìm file chạy thay vì đoán đường dẫn
# ============================================================
#
# 0.64.9 chữa phần chọn SAI thư mục, nhưng phần dò file chạy vẫn là một danh sách đường dẫn gõ
# cứng. Chủ repo cập nhật xong vẫn thấy y nguyên câu "chưa có trình duyệt" (22/09), vì máy họ
# để file chạy ở một bố cục không nằm trong danh sách. Playwright đã đổi bố cục vài lần và còn
# tách thư mục theo kiến trúc máy - `chrome-linux64`, `chrome-linux-arm64` đều có thật, đọc
# thẳng trong playwright-core mới thấy. Gõ cứng đường dẫn của thứ người khác sinh ra là cược
# rằng họ không bao giờ đổi nữa.

for _ten_bo_cuc, _duong in (
        ("máy ARM64", "chrome-linux-arm64/headless_shell"),
        ("tên thư mục có hậu tố 64", "chrome-linux64/chrome"),
        ("bố cục chưa từng thấy", "build/v3/nested/deep/chrome"),
):
    _dung(("chromium_headless_shell-1243", _duong))
    check(f"{_ten_bo_cuc}: vẫn tìm ra file chạy",
          ot.duong_dan_chrome().endswith(_duong.rsplit("/", 1)[-1]), ot.duong_dan_chrome())
    check(f"{_ten_bo_cuc}: trang Công cụ báo Sẵn sàng",
          ot.trang_thai("browser")["trang_thai"] == "san_sang")

# Quét KHÔNG được vơ bừa: một thư mục đầy file mà không có file chạy nào thì phải nói là không
# có, chứ không phải trả về file đầu tiên nhìn thấy.
_dung(("chromium-1243", "chrome-linux/libEGL.so"), ("chromium-1243", "chrome-linux/icudtl.dat"))
if not ot._chrome_he_thong():
    check("thư mục đầy file nhưng KHÔNG có file chạy -> nói không có",
          ot.duong_dan_chrome() == "", ot.duong_dan_chrome())

# Có cả hai thì vẫn ưu tiên bản đầy đủ, kể cả khi bản đầy đủ nằm ở bố cục lạ hơn.
_dung(("chromium_headless_shell-1243", "chrome-linux/headless_shell"),
      ("chromium-1243", "chrome-linux-arm64/chrome"))
check("có cả hai ở bố cục lạ -> vẫn lấy bản đầy đủ",
      ot.duong_dan_chrome().endswith("chrome"), ot.duong_dan_chrome())


# ============================================================
# 1c) Câu báo lỗi phải nói ĐÃ TÌM Ở ĐÂU, THẤY GÌ
# ============================================================
#
# "Chưa có trình duyệt nào Javis lái được" là câu cụt: người đọc nó đã bấm tải và đã thấy báo
# xong. Nó nói họ sai mà không nói sai ở đâu, nên mỗi vòng hỏi lại tốn một lần cập nhật.

_dung()
_cd = ot.chan_doan_trinh_duyet()
check("chưa tải gì -> chẩn đoán nói rõ thư mục rỗng hoặc chưa có",
      str(ot.BROWSERS_DIR) in _cd and ("rỗng" in _cd or "chưa có" in _cd), _cd)

_dung(("chromium_headless_shell-1243", "chrome-linux/khong-phai-file-chay"))
_cd = ot.chan_doan_trinh_duyet()
check("có thư mục nhưng không có file chạy -> chẩn đoán GỌI TÊN thư mục đó",
      "chromium_headless_shell-1243" in _cd, _cd)
# Cần CẢ HAI điều kiện: có thư viện (không thì engine dừng ở câu thiếu thư viện, chưa tới
# nhánh trình duyệt) và máy không có Chrome sẵn (không thì nó tìm thấy Chrome đó, chẳng còn
# lỗi nào để báo).
if CO_PW and not ot._chrome_he_thong():
    check("và câu engine Web trả về có kèm chẩn đoán đó",
          "chromium_headless_shell-1243" in wt.co_trinh_duyet(dung_nho=False)[1])
    check("vẫn giữ câu bảo phải làm gì (mở trang Công cụ)",
          "trang Công cụ" in wt.co_trinh_duyet(dung_nho=False)[1])


# ============================================================
# 2) Bất biến: hai trang KHÔNG BAO GIỜ nói ngược nhau
# ============================================================
#
# Đây là mục đáng giá nhất của file. Ba mục trên khoá một lỗi đã biết; mục này khoá cái LỚP
# lỗi đó - bất kỳ ai sau này vá một bên mà quên bên kia đều làm nó đỏ.

for _ten, _cac_ban in (("đủ hai thư mục", (DAY_DU, RUT_GON)),
                       ("chỉ bản đầy đủ", (DAY_DU,)),
                       ("chỉ bản rút gọn", (RUT_GON,)),
                       ("thư mục rỗng (tải hỏng dở)", (("chromium-1194", "README"),)),
                       ("chưa tải gì", ())):
    _dung(*_cac_ban)
    _cong_cu = ot.trang_thai("browser")["trang_thai"] == "san_sang"
    _engine = bool(wt._tim_chromium())
    # So theo ĐÚNG câu hỏi chung của hai bên: "máy này có trình duyệt chạy được không". Không
    # hỏi `co_trinh_duyet()` ở đây vì nó còn gánh thêm câu hỏi về thư viện playwright.
    # Máy chạy test có thể có sẵn Chrome hệ thống; lúc đó CẢ HAI cùng đúng, và bất biến vẫn giữ.
    check(f"{_ten}: trang Công cụ và engine Web nói CÙNG một câu",
          _cong_cu == _engine, f"cong_cu={_cong_cu} engine={_engine}")

# Tải hỏng dở: không được báo xong, nhưng phải GỠ ĐƯỢC. Báo "chưa cài" rồi khoá luôn nút Gỡ là
# người dùng mắc kẹt với một thư mục rác mà giao diện coi như không tồn tại.
_dung(("chromium-1194", "README"))
_tt = ot.trang_thai("browser")
if not ot._chrome_he_thong():
    check("tải hỏng dở -> KHÔNG báo Sẵn sàng", _tt["trang_thai"] == "chua_cai", _tt["ly_do"])
    check("tải hỏng dở -> nói rõ phải gỡ rồi tải lại", "tải lại" in _tt["ly_do"])
else:
    print("bỏ qua 2 phép: máy này có sẵn Chrome hệ thống nên nhánh 'hỏng dở' không tới được")
check("tải hỏng dở -> VẪN gỡ được", _tt["go_duoc"])


# ============================================================
# 3) Kết quả dò phải CỐ ĐỊNH, không theo thứ tự đĩa
# ============================================================

_dung(DAY_DU, RUT_GON, ("chromium-1200", "chrome-linux/chrome"))
check("nhiều bản -> chọn bản MỚI NHẤT", "1200" in ot.duong_dan_chrome(), ot.duong_dan_chrome())

_lan = {ot.duong_dan_chrome() for _ in range(20)}
check("gọi 20 lần ra CÙNG một kết quả", len(_lan) == 1, _lan)

_src = (SERVER / "optional_tools.py").read_text(encoding="utf-8")
check("có sắp xếp tường minh chứ không tin vào iterdir", "sorted(" in _src)
check("có ghi lại vì sao (hai thư mục, hai tên binary)", "headless_shell" in _src)

_wt = (SERVER / "web_transport.py").read_text(encoding="utf-8")
check("web_transport KHÔNG còn tự dò một kiểu riêng",
      "chrome-linux/chrome" not in _wt)
check("web_transport hỏi thẳng optional_tools",
      "optional_tools.duong_dan_chrome()" in _wt)


# ============================================================
# 4) Cài xong là thấy ngay, không phải khởi động lại
# ============================================================
#
# `web_transport` nhớ kết quả dò để khỏi quét đĩa mỗi lần vẽ trang Models. Không xoá cái nhớ đó
# sau khi tải xong thì người dùng thấy báo "Xong" rồi thẻ ChatGPT vẫn kêu thiếu - và lời khuyên
# duy nhất còn lại là "khởi động lại", thứ không ai tự đoán ra.

_dung()
wt.co_trinh_duyet()                                  # nhớ lại câu trả lời "chưa có"
check("đã nhớ kết quả dò", "kq" in wt._NHO_DO)

wt._NHO_DO["kq"] = (False, "câu trả lời CŨ")
ot._quen_ket_qua_do()
check("cài xong -> optional_tools bảo engine quên kết quả cũ", "kq" not in wt._NHO_DO)

_dung(DAY_DU)                                        # _dung() gọi dat_lai_do, nên dò lại từ đầu
if CO_PW:
    check("quên xong thì dò lại ra câu MỚI", wt.co_trinh_duyet() == (True, ""))
    check("và nhớ lại, lần sau không quét đĩa nữa", wt._NHO_DO.get("kq") == (True, ""))
else:
    check("quên xong thì dò lại, và lý do không còn là thiếu trình duyệt",
          "thư viện" in wt.co_trinh_duyet()[1].lower())

check("đường cài gọi hàm quên đó", _src.count("_quen_ket_qua_do()") >= 3)
check("hàm quên nuốt lỗi, không làm hỏng lượt cài", "except Exception:" in
      _src[_src.index("def _quen_ket_qua_do"):_src.index("def bat_dau_cai")])


# ============================================================
# 5) Không đụng tới thứ có sẵn của máy
# ============================================================

check("gỡ chỉ xoá thư mục Javis tải", "goc = PYLIBS_DIR if cong_cu ==" in _src)
check("vẫn dò Chrome/Edge có sẵn trên máy trước khi bắt tải",
      "_chrome_he_thong()" in _src[_src.index("def duong_dan_chrome"):])


# ============================================================
# 6) Dấu vân tay: Javis không được TỰ KHAI mình là máy tự động
# ============================================================
#
# Đây là mục đắt nhất trong file và cũng là mục quan trọng nhất, vì nó khoá lại đúng cái lỗi
# đã ngốn ba phiên bản. Việc DUY NHẤT của trình duyệt này là qua cửa Cloudflare của
# chatgpt.com. Đo trên Chromium 141 thật, cùng một máy, chỉ khác cách chạy:
#
#     headless_shell        : plugins 0, window.chrome undefined, UA HeadlessChrome, webdriver True
#     chrome ẩn             : plugins 5, window.chrome object,    UA HeadlessChrome, webdriver True
#     chrome + màn hình ảo  : plugins 5, window.chrome object,    UA Chrome,          webdriver False
#
# Chỉ dòng thứ ba mới có cửa. Hai dòng đầu trượt ngay ở byte đầu tiên của User-Agent.

check("trình cài tải bản ĐẦY ĐỦ, không phải --only-shell",
      "--only-shell" not in ot._lenh_cai("browser")[0])
check("và lệnh cài vẫn là playwright install chromium",
      ot._lenh_cai("browser")[0][-1] == "chromium")

check("có hàm dựng màn hình ảo", hasattr(wt, "man_hinh_ao"))
check("có hàm đóng màn hình ảo lại", hasattr(wt, "dong_man_hinh_ao"))

_src_wt = (SERVER / "web_transport.py").read_text(encoding="utf-8")
_mo = _src_wt[_src_wt.index("def _mo_that"):]
_mo = _mo[:_mo.index("\n    def ")]
check("mở trình duyệt thì HỎI màn hình ảo trước", "man_hinh_ao()" in _mo)
check("có màn hình thì chạy CÓ cửa sổ (headless False)", '"headless": False if man else' in _mo)
check("và truyền DISPLAY cho trình duyệt", '"DISPLAY": man' in _mo)
check("vẫn giữ cờ tắt cờ automation", "--disable-blink-features=AutomationControlled" in _mo)
check("đóng transport chung thì đóng luôn màn hình ảo",
      "dong_man_hinh_ao()" in _src_wt[_src_wt.index("def dong_chung"):])
check("tắt được bằng biến môi trường khi máy nào đó không hợp", "JAVIS_WEB_XVFB" in _src_wt)

# Không có DISPLAY và không có Xvfb thì phải trả "" chứ không được ném, và KHÔNG được
# treo: một máy chủ thiếu Xvfb vẫn phải chat được, chỉ là kém cửa hơn.
_nho = (wt._MAN_HINH, wt._TIEN_TRINH_XVFB)
try:
    wt._MAN_HINH, wt._TIEN_TRINH_XVFB = None, None
    _display_cu = os.environ.pop("DISPLAY", None)
    os.environ["JAVIS_WEB_XVFB"] = "0"
    check("tắt bằng biến môi trường -> trả rỗng, không ném", wt.man_hinh_ao() == "")
    check("và câu mô tả thiết lập không ném dù chưa có gì",
          isinstance(wt.mo_ta_thiet_lap(), str))
finally:
    os.environ.pop("JAVIS_WEB_XVFB", None)
    if _display_cu is not None:
        os.environ["DISPLAY"] = _display_cu
    wt._MAN_HINH, wt._TIEN_TRINH_XVFB = _nho

# Máy có DISPLAY sẵn (máy cá nhân có màn hình thật) thì DÙNG LUÔN, không dựng Xvfb thừa.
_nho = (wt._MAN_HINH, wt._TIEN_TRINH_XVFB)
try:
    wt._MAN_HINH, wt._TIEN_TRINH_XVFB = None, None
    os.environ["DISPLAY"] = ":0"
    check("máy đã có màn hình thật -> dùng luôn, không bật Xvfb",
          wt.man_hinh_ao() == ":0" and wt._TIEN_TRINH_XVFB is None)
finally:
    os.environ.pop("DISPLAY", None)
    wt._MAN_HINH, wt._TIEN_TRINH_XVFB = _nho

# Ảnh Docker phải mang sẵn Xvfb: container chạy bằng user thường, KHÔNG apt-get được lúc chạy.
_docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
check("Dockerfile cài xvfb", "xvfb" in _docker)
check("xvfb nằm cùng lớp với thư viện Chromium (tắt chung một cờ)",
      _docker.index("install -y --no-install-recommends xvfb")
      > _docker.index("WITH_BROWSER_DEPS=1"))

# Lớp đắt: có Chromium thật thì ĐO, không tin chữ trong mã. Bỏ qua khi máy không có gì.
def _chrome_that() -> str:
    """Một file chạy Chromium THẬT trên máy này, hoặc "" khi không có.

    KHÔNG hỏi `_tim_chromium()`: các mục trên cố ý dựng file chạy GIẢ trong BROWSERS_DIR để
    thử phần dò đường, nên ở đây nó trả về đúng cái giả đó và mở lên là EACCES.
    """
    for goc in filter(None, [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
                             str(Path.home() / ".cache/ms-playwright")]):
        g = Path(goc)
        if not g.is_dir():
            continue
        for d in sorted(g.glob("chromium-*"), reverse=True):
            for f in d.rglob("chrome"):
                if f.is_file() and os.access(f, os.X_OK):
                    return str(f)
    return ""


_that = _chrome_that()
if CO_PW and _that and wt.man_hinh_ao():
    import tempfile as _tf
    _tp = wt.ChatGPTWebTransport(profile_dir=_tf.mkdtemp(prefix="javis-vantay-"),
                                 executable_path=_that)
    _ok, _ly_do = _tp._chay(_tp._mo_that)
    check("mở được trình duyệt thật", _ok, _ly_do)
    if _ok:
        try:
            _r = _tp._chay(lambda: _tp._page.evaluate(
                "() => ({ua: navigator.userAgent, wd: navigator.webdriver,"
                " plugins: navigator.plugins.length, chrome: typeof window.chrome})"))
            check("ĐO THẬT: User-Agent KHÔNG chứa Headless", "Headless" not in _r["ua"], _r["ua"])
            check("ĐO THẬT: navigator.webdriver là false", not _r["wd"])
            check("ĐO THẬT: có plugin như trình duyệt thường", _r["plugins"] > 0)
            check("ĐO THẬT: có window.chrome", _r["chrome"] == "object")
        finally:
            _tp._chay(_tp._dong_that)
    wt.dong_man_hinh_ao()


print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_do_trinh_duyet: tất cả pass")
