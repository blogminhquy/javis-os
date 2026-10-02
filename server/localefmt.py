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

import contextvars
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


# Ngôn ngữ giao diện của THIẾT BỊ đang gọi (cookie `javis_lang`, middleware trong main.py đặt
# cho từng request). Cần riêng vì `ui_lang` trong settings là chung CẢ MÁY, còn ngôn ngữ giao
# diện là theo từng trình duyệt: chủ máy đọc tiếng Việt trên điện thoại, nhân viên đọc tiếng Anh
# trên laptop, cùng một Javis. Ngoài request (Telegram, việc nền) biến này rỗng.
_UI_YEU_CAU: contextvars.ContextVar = contextvars.ContextVar("javis_ui_lang", default="")


def dat_ngon_ngu_yeu_cau(ma: str):
    """Đặt ngôn ngữ giao diện cho request hiện tại. Trả token để `bo_ngon_ngu_yeu_cau` gỡ."""
    return _UI_YEU_CAU.set(lang_registry.chuan_hoa(ma or ""))


def bo_ngon_ngu_yeu_cau(token) -> None:
    try:
        _UI_YEU_CAU.reset(token)
    except Exception:
        pass   # token của context khác (task con): bỏ qua, context đó tự hết hạn


def ngon_ngu_giao_dien() -> str:
    """Ngôn ngữ CHỮ TRÊN MÀN HÌNH. Dùng cho danh sách skill, nhãn nút, thông báo lỗi.

    Thiết bị đang gọi (cookie) -> `ui_lang` của cả máy -> mặc định."""
    return (_UI_YEU_CAU.get()
            or lang_registry.chuan_hoa(_cau_hinh().get("ui_lang") or "")
            or lang_registry.MAC_DINH)


def chu(vi: str, en: str, **bien) -> str:
    """Chữ hiện trên màn hình, đúng ngôn ngữ giao diện của người đang nhìn.

        return JSONResponse({"error": chu("Không tìm thấy file", "File not found")})
        chu("Đã lưu {n} mục", "Saved {n} items", n=3)

    Viết hai bản NGAY TẠI CHỖ thay vì một kho khoá như dashboard: chuỗi phía server rải ở hàng
    trăm chỗ, mỗi chỗ chỉ dùng một lần, và đọc code thấy luôn cả hai bản thì sửa một bản không
    quên bản kia. Thứ tiếng thứ ba rơi về tiếng Anh (`lang_registry.chon_ban_dich`).
    `bien` chỉ được thay khi có truyền, nên chữ chứa dấu ngoặc nhọn vẫn an toàn.
    """
    s = lang_registry.chon_ban_dich(ngon_ngu_giao_dien(), {"vi": vi, "en": en})
    if bien:
        try:
            return s.format(**bien)
        except (KeyError, IndexError, ValueError):
            return s
    return s


def ngon_ngu_tra_loi() -> str:
    """Ngôn ngữ Javis TRẢ LỜI, theo cấu hình - KHÔNG tính phần dò từ câu người dùng vừa gõ.

    `reply_lang` mặc định là "auto" (bám theo người viết), và "auto" không phải một ngôn ngữ,
    nên rơi tiếp xuống `ui_lang`. Bỏ nấc đó thì máy để giao diện tiếng Anh, `reply_lang` để
    auto, mà những chỗ chỉ có cấu hình chứ không có câu người dùng (mô tả tool, giọng đọc) lại
    quay về tiếng Việt.

    Chỗ nào có văn bản của lượt chat thì dùng `lang.resolve()` - nó chính xác hơn hàm này.
    """
    c = _cau_hinh()
    return (lang_registry.chuan_hoa(c.get("reply_lang") or "")
            or lang_registry.chuan_hoa(c.get("ui_lang") or "")
            or lang_registry.MAC_DINH)


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
