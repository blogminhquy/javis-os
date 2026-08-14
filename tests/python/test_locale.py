"""Locale: múi giờ, tiền tệ, định dạng - TÁCH khỏi ngôn ngữ.

    python tests/run.py locale

Vì sao tách. Ngôn ngữ và locale hay bị gộp, nhưng chúng độc lập thật: một người đọc giao diện
tiếng Anh, bảo Javis trả lời tiếng Anh, mà vẫn ngồi ở Việt Nam nên vẫn xài UTC+7 và VND. Gộp
hai thứ là ép họ chọn giữa "hiểu được chữ" và "xem đúng giờ".

Trước tầng này, UTC+7 nằm nhúng cứng ở 16 chỗ dưới dạng `timezone(timedelta(hours=7))`. Không
ai cố ý; nó tích tụ từng dòng một, mỗi lần một người cần "bây giờ mấy giờ" và viết ra cái
nhanh nhất. Hệ quả: đổi múi giờ ở trang Cài đặt không có tác dụng gì, và nhắc hẹn "7h sáng"
là 7h sáng ở Hà Nội chứ không phải ở nơi người dùng ngồi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import pathlib
import re
import sys
from datetime import datetime, timezone

import config as cfgmod
import localefmt
import cron_util
import lang_registry

_loi = []


def check(ten, dieu_kien):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}")
    if not dieu_kien:
        _loi.append(ten)


def _voi_locale(**patch):
    """Chạy với một cụm locale giả. Vá `read_settings` chứ không ghi đĩa."""
    goc = cfgmod.read_settings

    def gia():
        cfg = goc()
        cfg.setdefault("locale", {}).update(patch)
        return cfg
    cfgmod.read_settings = gia
    localefmt._CACHE.clear()
    return goc


def _tra(goc):
    cfgmod.read_settings = goc
    localefmt._CACHE.clear()


# ============================================================
# 1. Múi giờ đọc từ cấu hình, và ĐỔI ĐƯỢC
# ============================================================
check("mặc định là giờ Việt Nam", localefmt.ten_tz() == "Asia/Ho_Chi_Minh")
_off_vn = localefmt.now().utcoffset().total_seconds() / 3600
check("và lệch đúng UTC+7", _off_vn == 7)

_goc = _voi_locale(tz="Asia/Tokyo")
try:
    check("đổi múi giờ sang Tokyo là ăn NGAY, không cần khởi động lại",
          localefmt.ten_tz() == "Asia/Tokyo"
          and localefmt.now().utcoffset().total_seconds() / 3600 == 9)
finally:
    _tra(_goc)
check("trả về đúng múi giờ cũ sau khi hoàn tác", localefmt.ten_tz() == "Asia/Ho_Chi_Minh")

# Máy thiếu tzdata hoặc người dùng gõ sai tên: KHÔNG được ném lỗi giữa lượt chat.
_goc = _voi_locale(tz="Khong/CoThat")
try:
    check("múi giờ sai thì rơi về mặc định chứ không ném lỗi",
          localefmt.now().utcoffset().total_seconds() / 3600 == 7)
finally:
    _tra(_goc)


# ============================================================
# 2. Tiền tệ: định dạng, KHÔNG quy đổi
# ============================================================
check("VND đặt ký hiệu SAU số, không phần lẻ", localefmt.fmt_tien(1250000) == "1,250,000đ")
check("USD đặt ký hiệu TRƯỚC số, hai chữ số lẻ", localefmt.fmt_tien(12.5, "USD") == "$12.50")
check("đồng lạ vẫn in được, dạng số kèm mã", localefmt.fmt_tien(99, "JPY") == "99.00 JPY")
check("giá trị rác không làm nổ", localefmt.fmt_tien("hỏng") == "0đ")

# Đây là ràng buộc CÓ CHỦ Ý, không phải thiếu sót: quy đổi cần tỉ giá THẬT cập nhật theo ngày.
# Trang Mức dùng từng quy đổi USD sang đồng bằng một tỉ giá viết cứng, và phần đó đã bị gỡ ở
# 0.32.1 vì con số nó hiện ra không đúng với thực tế người dùng trả.
_src = pathlib.Path(SERVER, "localefmt.py").read_text(encoding="utf-8")
check("CANARY: localefmt KHÔNG tự quy đổi tỉ giá",
      "ty_gia" not in _src and "exchange" not in _src.lower())


# ============================================================
# 3. Cron đọc thành lời theo ngôn ngữ
# ============================================================
check("cron tiếng Việt giữ nguyên hành vi", cron_util.describe_cron("0 7 * * *") == "7:00 mỗi ngày")
check("cron tiếng Anh đọc được", cron_util.describe_cron("*/30 * * * *", "en") == "every 30 minutes")

# Cron dùng 0 = CHỦ NHẬT, còn `weekdays` của sổ đăng ký theo datetime.weekday() tức 0 = THỨ HAI.
# Lệch một vòng, và quên đổi thì mọi lịch "thứ hai" hiện thành "chủ nhật" - sai im lặng, người
# dùng chỉ phát hiện khi việc chạy nhầm ngày.
check("CANARY: cron 1 là THỨ HAI, không phải chủ nhật",
      "thứ hai" in cron_util.describe_cron("0 9 * * 1").lower())
check("CANARY: cron 0 là CHỦ NHẬT",
      "chủ nhật" in cron_util.describe_cron("0 9 * * 0").lower())
check("và đúng như vậy ở tiếng Anh",
      "monday" in cron_util.describe_cron("0 9 * * 1", "en").lower()
      and "sunday" in cron_util.describe_cron("0 9 * * 0", "en").lower())
check("ngôn ngữ chưa có bộ chữ cron thì rơi về tiếng Việt, KHÔNG rơi về biểu thức thô",
      cron_util.describe_cron("0 7 * * *", "th") == "7:00 mỗi ngày")


# ============================================================
# 4. CHỐT CHẶN: không ai được ghim lại UTC+7
# ============================================================
# Đây là cái chốt giữ cho 16 chỗ vừa dọn không mọc lại. Không có nó thì lần sửa tính năng kế
# tiếp lại có người cần "bây giờ mấy giờ" và viết ra cái nhanh nhất.
_GHIM = re.compile(r"timezone\(\s*timedelta\(\s*hours\s*=\s*7\s*\)\s*\)")
MIEN_TRU = {
    "server/localefmt.py",                      # nơi khai mặc định - việc của nó
    "system/plugins/javis-schedule/plugin.py",  # dự phòng khi chạy ngoài tiến trình server
    "system/plugins/datetime-vn/plugin.py",     # cùng lý do
}
vi_pham = []
for p in sorted(pathlib.Path(ROOT).glob("server/**/*.py")) + \
         sorted(pathlib.Path(ROOT).glob("system/**/*.py")):
    rel = p.relative_to(ROOT).as_posix()
    if rel in MIEN_TRU or "__pycache__" in rel:
        continue
    for i, d in enumerate(p.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        t = d.strip()
        if t.startswith("#") or t.startswith("*"):
            continue
        if _GHIM.search(re.sub(r"`[^`]*`", "", d)):
            vi_pham.append(f"{rel}:{i}")
check("CANARY: không còn chỗ nào ghim cứng UTC+7 ngoài nơi khai mặc định",
      not vi_pham)
if vi_pham:
    print("              " + ", ".join(vi_pham[:6]))


# ============================================================
# 5. Locale gửi cho dashboard
# ============================================================
g = localefmt.cho_giao_dien()
check("gói locale có đủ trường dashboard cần",
      {"tz", "currency", "number_locale", "utc_offset_minutes"} <= set(g))
check("locale định dạng số lấy từ sổ đăng ký ngôn ngữ",
      g["number_locale"] == lang_registry.get(
          (cfgmod.read_settings().get("locale") or {}).get("ui_lang") or "vi").number_locale)

# Ngôn ngữ và locale phải ĐỘC LẬP: đọc tiếng Anh mà vẫn ngồi ở UTC+7 là chuyện bình thường.
_goc = _voi_locale(ui_lang="en", tz="Asia/Ho_Chi_Minh")
try:
    g2 = localefmt.cho_giao_dien()
    check("giao diện tiếng Anh mà vẫn giữ được múi giờ Việt Nam",
          g2["number_locale"] == "en-US" and g2["tz"] == "Asia/Ho_Chi_Minh"
          and g2["utc_offset_minutes"] == 420)
finally:
    _tra(_goc)

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:4]))
    sys.exit(1)
print("Tất cả xanh.")
