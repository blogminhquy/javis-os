"""Locale: múi giờ, tiền tệ, định dạng. TÁCH KHỎI ngôn ngữ, và đó là cả điểm của file này.

Ngôn ngữ và locale hay bị gộp làm một, nhưng chúng độc lập thật sự: một người dùng đọc giao
diện tiếng Anh, bảo Javis trả lời tiếng Anh, mà vẫn ngồi ở Việt Nam nên vẫn xài UTC+7 và VND.
Gộp hai thứ là ép họ chọn giữa "hiểu được chữ" và "xem đúng giờ".

**TÊN FILE KHÔNG PHẢI NGẪU NHIÊN.** Nó KHÔNG được đặt là `server/locale.py`: các module trong
`server/` nạp phẳng (`import config`, `import lang`), nên một file tên `locale.py` sẽ che
`locale` của thư viện chuẩn Python với mọi thứ import nó, và hỏng theo kiểu rất khó truy.

Trước file này, UTC+7 nằm nhúng cứng ở 12 chỗ dưới dạng `timezone(timedelta(hours=7))`. Không
ai cố ý làm thế; nó tích tụ từng dòng một, mỗi lần một người cần "bây giờ mấy giờ" và viết ra
cái nhanh nhất.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

import config as cfgmod
import lang_registry


# Múi giờ dùng khi cấu hình trống hoặc hỏng. Việt Nam không có giờ mùa hè nên UTC+7 là hằng
# số, không phụ thuộc tzdata của máy chủ - đó là lý do 12 chỗ cũ viết thẳng `hours=7` và
# không sai. Giữ nguyên nó làm lưới an toàn.
TZ_MAC_DINH = timezone(timedelta(hours=7))
TEN_TZ_MAC_DINH = "Asia/Ho_Chi_Minh"

# Cache theo TÊN múi giờ. `ZoneInfo` phải đọc tzdata từ đĩa, mà `now()` bị gọi ở đường nóng
# của mọi lượt chat.
_CACHE: dict[str, tzinfo] = {}


def _tu_ten(ten: str) -> tzinfo:
    ten = str(ten or "").strip() or TEN_TZ_MAC_DINH
    if ten in _CACHE:
        return _CACHE[ten]
    try:
        from zoneinfo import ZoneInfo
        z = ZoneInfo(ten)
    except Exception:
        # Máy thiếu tzdata (hay gặp trên image Docker gọn) hoặc tên múi giờ gõ sai. Rơi về
        # UTC+7 chứ KHÔNG ném lỗi: đây là đường nóng của mọi lượt chat, và một ngoại lệ ở đây
        # giết cả câu trả lời chỉ vì một dòng cấu hình.
        z = TZ_MAC_DINH
    _CACHE[ten] = z
    return z


def _cau_hinh() -> dict:
    try:
        return cfgmod.read_settings().get("locale") or {}
    except Exception:
        return {}


def ten_tz() -> str:
    return str(_cau_hinh().get("tz") or TEN_TZ_MAC_DINH)


def tz() -> tzinfo:
    """Múi giờ đang cấu hình. Không bao giờ ném lỗi."""
    return _tu_ten(ten_tz())


def now() -> datetime:
    """"Bây giờ" theo múi giờ người dùng đã chọn. Thay cho mọi
    `datetime.now(timezone(timedelta(hours=7)))` rải rác."""
    return datetime.now(tz())


def today_str() -> str:
    return now().strftime("%Y-%m-%d")


def doi_mui(moc: datetime) -> datetime:
    """Đưa một mốc thời gian về múi giờ đang cấu hình. Mốc không mang múi giờ được coi là UTC,
    cùng quy ước với `usage_parsers`."""
    if moc.tzinfo is None:
        moc = moc.replace(tzinfo=timezone.utc)
    return moc.astimezone(tz())


# ---------------------------------------------------------------- tiền tệ

# Ký hiệu và cách đặt. Chỉ khai những đồng Javis thật sự chạm tới; đồng lạ thì in mã tiền tệ
# đằng sau con số, một cách hiển thị đúng ở mọi nơi dù không đẹp.
_TIEN = {
    "VND": {"ky_hieu": "đ", "sau": True, "le": 0},
    "USD": {"ky_hieu": "$", "sau": False, "le": 2},
    "EUR": {"ky_hieu": "€", "sau": False, "le": 2},
}


def ma_tien() -> str:
    return str(_cau_hinh().get("currency") or "VND").upper()


def fmt_tien(so: float, ma: str = "") -> str:
    """Số tiền thành chữ theo đồng tiền đang cấu hình.

    KHÔNG tự quy đổi tỉ giá, và đây là chuyện có chủ ý: quy đổi cần một tỉ giá THẬT, cập nhật
    theo ngày. Trang Mức dùng từng quy đổi USD sang đồng bằng một tỉ giá viết cứng, và phần
    đó đã bị gỡ ở 0.32.1 chính vì con số nó hiện ra không đúng với thực tế người dùng trả.
    Hàm này chỉ ĐỊNH DẠNG con số đã có, đúng đồng tiền của nó.
    """
    m = (ma or ma_tien()).upper()
    d = _TIEN.get(m)
    try:
        v = float(so)
    except (TypeError, ValueError):
        v = 0.0
    if not d:
        return f"{v:,.2f} {m}"
    s = f"{v:,.{d['le']}f}"
    return (s + d["ky_hieu"]) if d["sau"] else (d["ky_hieu"] + s)


# ---------------------------------------------------------------- cho dashboard

def cho_giao_dien() -> dict:
    """Gói locale gửi kèm /settings để dashboard định dạng số và ngày cho đúng.

    Dashboard KHÔNG tự suy locale từ ngôn ngữ: hai thứ đó tách rời (xem đầu file), và suy một
    cái từ cái kia là tái lập đúng sự nhập nhằng file này sinh ra để gỡ.
    """
    ma = ma_tien()
    return {
        "tz": ten_tz(),
        "currency": ma,
        "number_locale": lang_registry.get(
            _cau_hinh().get("ui_lang") or lang_registry.MAC_DINH).number_locale,
        "utc_offset_minutes": int(now().utcoffset().total_seconds() // 60),
    }
