"""Đổi mật khẩu / tên đăng nhập của tài khoản quản trị.

    python tests/run.py doi_mat_khau      (KHÔNG mạng)

Lỗi thật (báo 2026-08-12): điền tên đăng nhập + mật khẩu mới ở trang Tài khoản, bấm Lưu, và
không có gì xảy ra. Nguyên nhân: dashboard gọi `/auth/setup` để ĐỔI mật khẩu, mà endpoint đó là
đường CÔNG KHAI cho lần đầu tạo admin nên nó buộc phải trả 400 "Đã có tài khoản" - đúng như
thiết kế của nó. Không có endpoint nào cho việc đổi cả.

File này canh cái đường mới (`/auth/password`) và bốn thứ dễ làm sai quanh nó:

1. **Nuốt mất 2FA.** `cfg["auth"]` chứa cả cấu hình TOTP. Gán đè nguyên cục khi đổi mật khẩu là
   lặng lẽ tắt xác thực 2 lớp đúng lúc người ta tưởng mình vừa siết bảo mật.
2. **Phiên cũ sống tiếp.** Đổi mật khẩu mà không hạ phiên cũ thì cái phiên người ta muốn đuổi
   (máy công ty, trình duyệt người khác) vẫn vào được thêm 30 ngày.
3. **Tự khoá mình.** Hạ hết phiên mà quên cấp lại cho chính máy đang thao tác thì vừa bấm Lưu
   xong là văng ra màn đăng nhập.
4. **Cửa sau qua /settings.** Nhánh `section=password` cũ không đòi mật khẩu hiện tại và nhận
   cả token API scope `full` - một token rò ra là đổi được mật khẩu chủ máy.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pwtest-")
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"

from fastapi.testclient import TestClient   # noqa: E402
import config as c   # noqa: E402
import main          # noqa: E402
import totp          # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


cl = TestClient(main.app)


def P(path, **d):
    return cl.post(path, data=d)


def dat_tai_khoan(user="admin", pw="matkhau123"):
    cfg = c.read_settings()
    cfg["auth"] = {"username": user,
                   **dict(zip(("password_hash", "salt"), c.hash_password(pw)))}
    c.write_settings(cfg)
    c.clear_sessions()
    cl.cookies.clear()
    P("/auth/login", username=user, password=pw)


# ============================================================
# 1. Chính cái lỗi được báo: đổi mật khẩu phải ĂN
# ============================================================
dat_tai_khoan()
_r = P("/auth/password", current_password="matkhau123", username="quanly", password="matkhaumoi456")
check("đổi mật khẩu + tên đăng nhập -> ok", _r.status_code == 200 and _r.json().get("ok") is True)
check("mật khẩu MỚI vào được", c.verify_password("matkhaumoi456") is True)
check("mật khẩu CŨ hết tác dụng", c.verify_password("matkhau123") is False)
check("tên đăng nhập đã đổi", c.read_settings()["auth"]["username"] == "quanly")

# CANARY của chính lỗi cũ: /auth/setup là đường LẦN ĐẦU, nó PHẢI từ chối khi đã có tài khoản.
# Đó không phải bug của nó - bug là dashboard gọi nhầm sang đó để đổi.
check("CANARY: /auth/setup vẫn từ chối khi đã có tài khoản (đường lần-đầu, không phải đường đổi)",
      P("/auth/setup", username="ke_la", password="chiemquyen123").status_code == 400)
check("và không đổi được gì qua đường đó", c.verify_password("chiemquyen123") is False)

# ============================================================
# 2. Đòi mật khẩu hiện tại
# ============================================================
dat_tai_khoan()
check("sai mật khẩu hiện tại -> 401",
      P("/auth/password", current_password="sai", password="matkhaumoi456").status_code == 401)
check("và mật khẩu KHÔNG đổi", c.verify_password("matkhau123") is True)
check("thiếu mật khẩu hiện tại -> 401",
      P("/auth/password", password="matkhaumoi456").status_code == 401)
check("mật khẩu mới quá ngắn -> 400 (cùng rào 8 ký tự với /auth/setup)",
      P("/auth/password", current_password="matkhau123", password="ngan12").status_code == 400)
check("không gửi gì để đổi -> 400",
      P("/auth/password", current_password="matkhau123").status_code == 400)
check("sau mấy lần hỏng, mật khẩu vẫn nguyên", c.verify_password("matkhau123") is True)

# Đổi MỖI tên đăng nhập (để trống mật khẩu mới) - vẫn phải có mật khẩu hiện tại.
_r = P("/auth/password", current_password="matkhau123", username="  sepca  ")
check("đổi mỗi tên đăng nhập -> ok", _r.json().get("ok") is True)
check("tên được cắt khoảng trắng", c.read_settings()["auth"]["username"] == "sepca")
check("mật khẩu giữ nguyên khi chỉ đổi tên", c.verify_password("matkhau123") is True)

# ============================================================
# 3. KHÔNG được nuốt 2FA khi đổi mật khẩu
# ============================================================
dat_tai_khoan()
_ma = totp.sinh_ma_khoi_phuc()
c.totp_set(secret=totp.sinh_secret(), enabled=True, recovery=_ma)
check("dựng sẵn 2FA đang bật", c.totp_enabled() is True)
_sec_cu = c.totp_secret()
P("/auth/password", current_password="matkhau123", password="matkhaumoi456")
check("CANARY: đổi mật khẩu KHÔNG tắt xác thực 2 lớp", c.totp_enabled() is True)
check("secret TOTP còn nguyên (app Authenticator không phải quét lại)", c.totp_secret() == _sec_cu)
check("mã khôi phục còn nguyên", c.totp_recovery_left() == 10)
c.totp_tat()

# ============================================================
# 4. Phiên: hạ phiên cũ, giữ phiên đang thao tác
# ============================================================
dat_tai_khoan()
_phien_may_khac = c.new_session()
check("dựng sẵn một phiên của máy khác", c.valid_session(_phien_may_khac) is True)
_r = P("/auth/password", current_password="matkhau123", password="matkhaumoi456")
check("CANARY: phiên của máy KHÁC bị hạ (nếu không, đổi mật khẩu chẳng đuổi được ai)",
      c.valid_session(_phien_may_khac) is False)
check("máy đang thao tác được cấp phiên MỚI ngay (không tự khoá mình)",
      "javis_session" in _r.cookies)
check("và dùng được luôn, không văng ra màn đăng nhập",
      cl.get("/auth/status").json().get("authed") is True)

# Đổi mỗi tên đăng nhập thì KHÔNG cần hạ phiên - credential vào máy chưa đổi.
_phien = c.new_session()
P("/auth/password", current_password="matkhaumoi456", username="admin")
check("đổi mỗi tên đăng nhập thì không hạ phiên của máy khác", c.valid_session(_phien) is True)

# ============================================================
# 5. Không có cửa sau: /settings section=password
# ============================================================
dat_tai_khoan()
_r = cl.post("/settings", data={"section": "password",
                                "data": json.dumps({"new_password": "cuasau123456"})})
check("CANARY: /settings section=password KHÔNG đổi được mật khẩu nữa", _r.status_code == 400)
check("mật khẩu vẫn là cái cũ", c.verify_password("matkhau123") is True
      and c.verify_password("cuasau123456") is False)

_src = (SERVER / "main.py").read_text(encoding="utf-8")
_khoi_settings = _src[_src.index('elif section == "password":'):_src.index('    else:\n        return JSONResponse({"ok": False, "error": "section không hợp lệ"}')]
check("CANARY: nhánh đó không còn băm mật khẩu nào cả", "hash_password" not in _khoi_settings)

# Endpoint đổi mật khẩu phải đòi SESSION trình duyệt, không nhận token API - cùng lý do với
# /auth/tokens và /auth/2fa/*: token rò ra không được phép biến thành chiếm tài khoản.
_khoi_pw = _src[_src.index('@app.post("/auth/password")'):_src.index('@app.get("/auth/tokens")')]
check("CANARY: /auth/password đòi session trình duyệt", "_doi_phien_that(request)" in _khoi_pw)
check("CANARY: /auth/password KHÔNG nằm trong danh sách miễn đăng nhập",
      "/auth/password" not in _src[_src.index("_AUTH_PUBLIC_EXACT = "):
                                   _src.index("_AUTH_PUBLIC_EXACT = ") + 400])

# ============================================================
# 6. Dashboard đã nối đúng đường (cả HAI bề mặt tài khoản)
# ============================================================
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
_app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
_html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

check("trang Tài khoản gọi /auth/password", '"/auth/password"' in _console)
check("và có ô nhập mật khẩu hiện tại", 'id="acCur"' in _console)
check("khối tài khoản trong trang Cài đặt cũng gọi /auth/password", '"/auth/password"' in _app)
check("index.html có ô mật khẩu hiện tại cho khối đó", 'id="setAuthCur"' in _html)

# Khối #quickSet được NHÚNG sang trang Cài đặt của console mà không đi qua openSettings(), nên
# _settingsCache rỗng ở đó. Đọc trạng thái từ cache là đi nhầm nhánh "đặt lần đầu" -> 400 câm.
check("CANARY: nút Lưu đọc trạng thái TƯƠI, không tin _settingsCache",
      "_settingsCache && _settingsCache.auth" not in _app)
check("console.js gọi hàm đổ trạng thái tài khoản khi mở trang Cài đặt",
      "__javisRefreshAuthRow" in _console and "__javisRefreshAuthRow" in _app)

# Rào tối thiểu 8 ký tự phải giống nhau ở giao diện và server, nếu không người dùng gõ 5 ký tự
# rồi ăn lỗi từ server mà chẳng hiểu vì sao.
check("CANARY: giao diện không còn nói 'tối thiểu 4 ký tự'",
      "tối thiểu 4 ký tự" not in _console)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test doi_mat_khau đã qua.")
