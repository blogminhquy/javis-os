"""Xác thực 2 lớp (TOTP) ở cổng đăng nhập.

    python tests/run.py 2fa      (KHÔNG mạng)

Javis chạy full quyền và có Bash, nên cổng đăng nhập là thứ đáng canh nhất trong cả sản phẩm.
File này canh bốn thứ dễ làm sai khi tự viết TOTP, và cả bốn đều KHÔNG lộ ra lúc dùng thử:

1. **Dùng lại mã.** Một mã sống 30 giây, cộng cửa sổ lệch đồng hồ là tới 90. Không ghi lại bước
   đã dùng thì mã bị nhìn trộm qua vai còn xài được suốt quãng đó.
2. **Bật trước khi xác nhận.** Bật 2FA rồi mới bảo người ta quét QR là tự khoá chính chủ ra
   ngoài khi app của họ sinh mã khác (lệch giờ, quét hụt).
3. **Không có mã khôi phục.** Mất điện thoại = mất máy, và lối ra duy nhất là SSH vào sửa tay
   settings.json - đúng thứ người ta bật 2FA để khỏi phải làm.
4. **Ô mã thành máy dò.** Kiểm mã TRƯỚC mật khẩu là cho người chưa biết mật khẩu biết tài khoản
   nào đã bật 2FA.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-2fa-test-")
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


def dat_tai_khoan():
    cfg = c.read_settings()
    cfg["auth"] = {"username": "admin",
                   **dict(zip(("password_hash", "salt"), c.hash_password("matkhau123")))}
    c.write_settings(cfg)


# ============================================================
# 1. Phần toán thuần (totp.py) - chạy được không cần server
# ============================================================
S = totp.sinh_secret()
check("secret là base32 đủ dài", len(S) == 32 and S.isalnum() and S.isupper())
check("hai lần sinh ra hai secret khác nhau", totp.sinh_secret() != totp.sinh_secret())
B = totp.buoc_hien_tai()
check("mã là 6 chữ số", len(totp.ma_cua_buoc(S, B)) == 6 and totp.ma_cua_buoc(S, B).isdigit())
check("mã khớp -> trả về bước", totp.kiem(S, totp.ma_cua_buoc(S, B)) == B)
check("lệch 1 bước vẫn nhận (bù đồng hồ điện thoại)",
      totp.kiem(S, totp.ma_cua_buoc(S, B - 1)) == B - 1)
check("lệch 2 bước thì thôi", totp.kiem(S, totp.ma_cua_buoc(S, B - 2)) is None)
check("mã rỗng / sai định dạng -> None",
      totp.kiem(S, "") is None and totp.kiem(S, "12345") is None and totp.kiem(S, "abcdef") is None)
check("secret rỗng -> None, không nổ", totp.kiem("", totp.ma_cua_buoc(S, B)) is None)
check("CANARY: bước <= bước đã dùng thì TỪ CHỐI (chống dùng lại mã)",
      totp.kiem(S, totp.ma_cua_buoc(S, B), buoc_da_dung=B) is None)
check("nhưng bước SAU đó vẫn nhận",
      totp.kiem(S, totp.ma_cua_buoc(S, B + 1), buoc_da_dung=B) == B + 1)
# Nhãn otpauth: tên workspace tiếng Việt có dấu làm vài app hiện chuỗi hỏng, dấu ':' phá cú pháp.
_uri = totp.otpauth_uri(S, "admin", "Javis OS của Quý: bản 1")
check("otpauth bỏ dấu tiếng Việt và ký tự phá cú pháp",
      _uri.startswith("otpauth://totp/") and "ủ" not in _uri and _uri.count(":") == 1)
check("otpauth mang secret + chu kỳ + số chữ số", f"secret={S}" in _uri and "period=30" in _uri)
_ma = totp.sinh_ma_khoi_phuc()
check("sinh đúng 10 mã khôi phục", len(_ma) == 10 and len(set(_ma)) == 10)
check("mã khôi phục không có ký tự dễ nhầm (0 O 1 I L)",
      not any(ch in "01OIL" for m in _ma for ch in m))
check("chuẩn hoá bỏ qua cách gõ",
      totp.chuan_hoa_ma_khoi_phuc(_ma[0].lower().replace("-", " ")) == _ma[0])


# ============================================================
# 2. Lưu trữ (config.py)
# ============================================================
dat_tai_khoan()
check("chưa bật thì totp_enabled False", c.totp_enabled() is False)
c.totp_set(secret=S, enabled=False, recovery=_ma)
check("CANARY: có secret mà chưa enabled thì vẫn coi là CHƯA bật", c.totp_enabled() is False)
c.totp_set(secret=None, enabled=True)
check("bật rồi thì True", c.totp_enabled() is True)
check("đọc lại secret đúng", c.totp_secret() == S)
check("đếm đúng số mã khôi phục còn lại", c.totp_recovery_left() == 10)
check("mã khôi phục dùng được, gõ thường/không gạch cũng được",
      c.totp_dung_ma_khoi_phuc(_ma[0].lower().replace("-", "")) is True)
check("và bị TIÊU luôn, không dùng lại được",
      c.totp_dung_ma_khoi_phuc(_ma[0]) is False and c.totp_recovery_left() == 9)
check("mã bịa thì không qua", c.totp_dung_ma_khoi_phuc("ZZZZ-ZZZZ") is False)

_raw = (ROOT / "server" / "settings.json")
_raw = (os.path.join(os.environ["JAVIS_STATE_DIR"], "settings.json"))
_txt = open(_raw, encoding="utf-8").read()
check("CANARY: secret TOTP được mã hoá trên đĩa, không nằm nguyên văn", S not in _txt)
check("CANARY: mã khôi phục cũng không nằm nguyên văn",
      not any(m in _txt for m in _ma))
c.totp_tat()
check("tắt thì xoá sạch secret + mã khôi phục",
      c.totp_enabled() is False and c.totp_secret() == "" and c.totp_recovery_left() == 0)


# ============================================================
# 3. Chạy THẬT qua HTTP - đủ vòng đời
# ============================================================
dat_tai_khoan()
check("đăng nhập thường khi chưa bật 2FA",
      P("/auth/login", username="admin", password="matkhau123").json().get("ok") is True)

_d = P("/auth/2fa/start").json()
check("start trả secret + uri + QR",
      len(_d["secret"]) == 32 and _d["uri"].startswith("otpauth://") and len(_d["qr_svg"]) > 500)
SEC = _d["secret"]
check("chưa xác nhận thì CHƯA bật (secret mới nằm trong RAM, không ghi cấu hình)",
      c.totp_enabled() is False)
check("sai mã -> không bật được", P("/auth/2fa/enable", code="000000").status_code == 400)

BB = totp.buoc_hien_tai()
_r = P("/auth/2fa/enable", code=totp.ma_cua_buoc(SEC, BB)).json()
REC = _r["recovery"]
check("xác nhận đúng -> bật + trả 10 mã khôi phục", _r["ok"] and len(REC) == 10)
check("và /auth/status khai đã bật", cl.get("/auth/status").json()["totp_enabled"] is True)

cl.cookies.clear()
_r = P("/auth/login", username="admin", password="matkhau123")
check("thiếu mã -> 401 kèm needs_2fa để giao diện hiện ô mã",
      _r.status_code == 401 and _r.json().get("needs_2fa") is True)
check("CANARY: SAI MẬT KHẨU thì KHÔNG lộ needs_2fa (ô mã không thành máy dò)",
      P("/auth/login", username="admin", password="sai").json().get("needs_2fa") is None)
check("CANARY: mã vừa dùng để BẬT thì không đăng nhập lại được",
      P("/auth/login", username="admin", password="matkhau123",
        code=totp.ma_cua_buoc(SEC, BB)).status_code == 401)
check("mã mới -> vào được",
      P("/auth/login", username="admin", password="matkhau123",
        code=totp.ma_cua_buoc(SEC, BB + 1)).json().get("ok") is True)
cl.cookies.clear()
check("CANARY: dùng LẠI đúng mã vừa đăng nhập -> từ chối",
      P("/auth/login", username="admin", password="matkhau123",
        code=totp.ma_cua_buoc(SEC, BB + 1)).status_code == 401)

check("mã khôi phục đăng nhập được",
      P("/auth/login", username="admin", password="matkhau123",
        code=REC[0].lower()).json().get("ok") is True)
check("và bị tiêu", c.totp_recovery_left() == 9)
cl.cookies.clear()
check("mã khôi phục đã dùng thì hết tác dụng",
      P("/auth/login", username="admin", password="matkhau123", code=REC[0]).status_code == 401)

# Sinh lại bộ mã khôi phục
P("/auth/login", username="admin", password="matkhau123", code=REC[1])
check("sinh lại mã khôi phục phải có mật khẩu",
      P("/auth/2fa/recovery", password="sai").status_code == 401)
_r2 = P("/auth/2fa/recovery", password="matkhau123").json()
check("sinh lại -> bộ mới 10 mã", _r2["ok"] and len(_r2["recovery"]) == 10)
check("bộ CŨ hết hiệu lực ngay", c.totp_dung_ma_khoi_phuc(REC[2]) is False)
check("bộ MỚI dùng được", c.totp_dung_ma_khoi_phuc(_r2["recovery"][0]) is True)

# Tắt: đòi CẢ mật khẩu lẫn mã
check("tắt mà sai mật khẩu -> chặn",
      P("/auth/2fa/disable", password="sai", code=_r2["recovery"][1]).status_code == 401)
check("tắt mà sai mã -> chặn",
      P("/auth/2fa/disable", password="matkhau123", code="000000").status_code == 401)
check("vẫn đang bật sau hai lần thử hỏng", c.totp_enabled() is True)
check("tắt đúng -> ok",
      P("/auth/2fa/disable", password="matkhau123",
        code=_r2["recovery"][1]).json().get("ok") is True)
check("tắt rồi thì đăng nhập không cần mã nữa",
      c.totp_enabled() is False
      and P("/auth/login", username="admin", password="matkhau123").json().get("ok") is True)


# ============================================================
# 4. Endpoint 2FA không được nhận token API
# ============================================================
# Cùng lý do với /auth/tokens: cho token đổi được cách đăng nhập thì một token rò ra là kẻ cầm
# nó tự gắn 2FA của mình vào rồi khoá chính chủ ra ngoài.
_src = (SERVER / "main.py").read_text(encoding="utf-8")
_khoi = _src[_src.index("def _doi_phien_that("):_src.index("@app.post(\"/auth/2fa/recovery\")")]
check("CANARY: mọi endpoint 2FA đều đòi session trình duyệt",
      _khoi.count("_doi_phien_that(request)") == 3 and "valid_session" in _khoi)
check("CANARY: /auth/2fa/* KHÔNG nằm trong danh sách miễn đăng nhập",
      "2fa" not in _src[_src.index("_AUTH_PUBLIC_EXACT = "):_src.index("_AUTH_PUBLIC_EXACT = ") + 400])

# install.sh chỉ ghi Ý ĐỊNH, không được tự bật 2FA (bật trước khi quét QR = tự khoá mình).
_ins = (ROOT / "install.sh").read_text(encoding="utf-8")
check("install.sh có hỏi bật 2FA", "JAVIS_SETUP_2FA" in _ins)
check("CANARY: install.sh KHÔNG tự bật, chỉ ghi cờ gợi ý",
      "_env_set JAVIS_SETUP_2FA 1" in _ins and "totp" not in _ins.lower())

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test 2fa_totp đã qua.")
