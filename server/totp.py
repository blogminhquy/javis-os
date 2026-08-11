"""Mã xác thực 2 lớp (TOTP - RFC 6238) cho cổng đăng nhập Javis.

Module này CỐ Ý thuần tuý: chỉ toán và chuỗi, không đọc/ghi cấu hình, không import `config`.
Nơi lưu secret và mã khôi phục là `config.py`; nơi ráp vào cổng đăng nhập là `main.py`. Tách
như vậy để test chạy offline được và để không đẻ thêm một vòng import quanh `config`.

Vì sao tự viết thay vì thêm thư viện: TOTP là HMAC-SHA1 trên một bộ đếm 30 giây, đúng 20 dòng
thật sự, và nó đã đứng yên từ RFC 6238 (2011). Thêm một dependency cho ngần đó code là đổi một
thứ mình đọc hết được lấy một thứ mình không kiểm soát, ngay tại cổng đăng nhập.

CHỐNG DÙNG LẠI MÃ: `kiem()` trả về bước thời gian đã khớp, và nơi gọi PHẢI lưu lại rồi từ chối
mọi bước <= bước đã dùng. Thiếu vế đó thì một mã bị nhìn trộm còn xài được suốt 90 giây - đó là
lỗ mà phần lớn bản TOTP tự viết mắc phải, vì nó không lộ ra trong lúc dùng thử.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import unicodedata
from urllib.parse import quote

CHU_KY = 30            # giây mỗi bước, mặc định của RFC và của mọi app Authenticator
SO_CHU_SO = 6
CUA_SO = 1             # chấp nhận lệch 1 bước hai phía → bù đồng hồ điện thoại lệch tối đa 30s

# Bảng chữ mã khôi phục: bỏ 0/O/1/I/L để người ta chép tay không nhầm. Mã khôi phục hay được
# in ra giấy rồi gõ lại lúc hoảng (mất điện thoại), nên dễ đọc quan trọng hơn ngắn.
_CHU_KHOI_PHUC = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SO_MA_KHOI_PHUC = 10


def sinh_secret(so_byte: int = 20) -> str:
    """Secret base32 cho app Authenticator. 20 byte = 160 bit, đúng khuyến nghị của RFC 4226."""
    return base64.b32encode(secrets.token_bytes(so_byte)).decode("ascii").rstrip("=")


def _giai_secret(secret: str) -> bytes:
    s = (secret or "").strip().replace(" ", "").upper()
    s += "=" * (-len(s) % 8)          # base32 đòi bội số của 8; secret hiển thị thường bỏ đệm
    return base64.b32decode(s, casefold=True)


def buoc_hien_tai(luc: float | None = None) -> int:
    return int((time.time() if luc is None else luc) // CHU_KY)


def ma_cua_buoc(secret: str, buoc: int) -> str:
    """Mã 6 chữ số của một bước thời gian. Đây là toàn bộ RFC 6238."""
    khoa = _giai_secret(secret)
    dam = hmac.new(khoa, struct.pack(">Q", max(0, int(buoc))), hashlib.sha1).digest()
    lech = dam[-1] & 0x0F                                   # truncation động
    so = struct.unpack(">I", dam[lech:lech + 4])[0] & 0x7FFFFFFF
    return str(so % (10 ** SO_CHU_SO)).zfill(SO_CHU_SO)


def kiem(secret: str, ma: str, *, buoc_da_dung: int = 0, luc: float | None = None,
         cua_so: int = CUA_SO) -> int | None:
    """Mã có đúng không. Trả BƯỚC đã khớp (để nơi gọi ghi lại), None nếu sai.

    `buoc_da_dung` là bước của lần đăng nhập thành công gần nhất: mọi bước <= nó bị từ chối,
    nên một mã đã dùng thì dùng lại không được nữa dù còn trong cửa sổ 30 giây.
    """
    ma = "".join(ch for ch in str(ma or "") if ch.isdigit())
    if len(ma) != SO_CHU_SO or not (secret or "").strip():
        return None
    hien_tai = buoc_hien_tai(luc)
    for d in range(-cua_so, cua_so + 1):
        b = hien_tai + d
        if b <= int(buoc_da_dung or 0) or b < 0:
            continue                                        # đã dùng rồi → không nhận lại
        if hmac.compare_digest(ma_cua_buoc(secret, b), ma):
            return b
    return None


def _sach(s: str) -> str:
    """Bỏ dấu + ký tự lạ cho nhãn otpauth. Tên workspace tiếng Việt có dấu làm vài app
    Authenticator hiện chuỗi hỏng, và ':' thì phá luôn cú pháp label của otpauth."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in s if ch.isalnum() or ch in " ._-").strip() or "Javis"


def otpauth_uri(secret: str, ten_dang_nhap: str, ten_workspace: str = "Javis OS") -> str:
    """Chuỗi `otpauth://` để app Authenticator quét QR hoặc nhập tay."""
    issuer = _sach(ten_workspace)
    label = quote(f"{issuer}:{_sach(ten_dang_nhap) or 'admin'}", safe="")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
            f"&algorithm=SHA1&digits={SO_CHU_SO}&period={CHU_KY}")


def qr_svg(noi_dung: str) -> str:
    """QR dạng SVG (chuỗi) cho `noi_dung`. "" nếu máy không có segno.

    Vẽ QR ở SERVER chứ không ở trình duyệt: dựng QR phía client cần một thư viện JS nữa, mà
    thứ được mã hoá ở đây là secret 2FA - càng ít chỗ đi qua càng tốt. Không có segno thì trả
    rỗng và giao diện lui về cho người dùng nhập tay secret; mất tiện, không mất tính năng.
    """
    try:
        import segno
    except Exception:
        return ""
    try:
        import io
        # segno GHI RA BYTES kể cả với kind="svg" - đưa StringIO vào là TypeError. Bọc except
        # rồi trả "" nên lỗi này không hiện ra ở đâu cả: QR biến mất, giao diện lặng lẽ lui về
        # nhập tay, và không ai biết vì sao. Nên vừa dùng BytesIO cho đúng, vừa in lỗi ra log.
        buf = io.BytesIO()
        segno.make(noi_dung, error="m").save(buf, kind="svg", scale=5, border=2,
                                             dark="#111", light=None)
        return buf.getvalue().decode("utf-8")
    except Exception as e:  # noqa: BLE001 - thiếu QR không được làm hỏng cả màn bật 2FA
        import sys
        print(f"[totp qr] không vẽ được QR: {type(e).__name__}: {e}", file=sys.stderr)
        return ""


def sinh_ma_khoi_phuc(so_ma: int = SO_MA_KHOI_PHUC) -> list[str]:
    """Danh sách mã khôi phục dạng 'ABCD-EFGH'. Dùng khi mất điện thoại.

    KHÔNG có nó thì bật 2FA là tự đặt một cái bẫy: mất máy là mất luôn đường vào, và cách duy
    nhất còn lại là SSH vào server sửa tay settings.json - đúng thứ người dùng bật 2FA để khỏi
    phải làm.
    """
    def _khoi(n):
        return "".join(secrets.choice(_CHU_KHOI_PHUC) for _ in range(n))
    return [f"{_khoi(4)}-{_khoi(4)}" for _ in range(max(1, int(so_ma)))]


def chuan_hoa_ma_khoi_phuc(ma: str) -> str:
    """'abcd efgh' / 'ABCD-EFGH' / 'abcdefgh' → 'ABCD-EFGH'. So sánh phải bỏ qua cách gõ."""
    s = "".join(ch for ch in str(ma or "").upper() if ch in _CHU_KHOI_PHUC)
    return f"{s[:4]}-{s[4:8]}" if len(s) == 8 else s
