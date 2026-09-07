"""Mất .secret_key thì 2FA phải HỎNG CÓ TIẾNG, không được âm thầm thành fail-open.

    python tests/run.py 2fa_mat_khoa_khong_im_lang     (KHÔNG mạng)

Vụ thật (16/08): chủ bật 2FA, cập nhật Javis xong UI báo "Chưa bật" - tưởng bản cập
nhật đè mất. Truy ra: secret 2FA mã hoá Fernet bằng STATE_DIR/.secret_key; file key
mất/đổi thì decrypt trả "", mà totp_enabled = enabled AND secret nên thành False.
Hậu quả kép, cả hai đều tệ hơn triệu chứng:
  1. FAIL-OPEN: cổng đăng nhập thôi hỏi mã luôn - ai có mật khẩu là vào thẳng, đúng
     thứ 2FA phải chặn, và chủ không hề hay biết vì UI chỉ nói "Chưa bật".
  2. PHÁ DỮ LIỆU: lần write_settings kế tiếp ghi secret "" xuống file - blob mã hoá
     bay màu vĩnh viễn, khôi phục lại đúng key cũ cũng không cứu được nữa.

Test ghim 4 tầng vá: totp_hong phát hiện đúng trạng thái; write_settings không phá
blob; cổng đăng nhập fail-closed (mã khôi phục - vốn BĂM chứ không mã hoá - vẫn vào
được); UI + /auth/status nói thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_td = tempfile.TemporaryDirectory()
os.environ["JAVIS_STATE_DIR"] = _td.name

import config as cfgmod          # noqa: E402  - đọc JAVIS_STATE_DIR lúc import
import secrets_store             # noqa: E402

assert str(cfgmod.STATE_DIR) == _td.name, "STATE_DIR phải trỏ vào thư mục tạm của test"


def _mat_key():
    """Giả lập đúng sự cố: file .secret_key biến mất, server khởi động lại."""
    try:
        os.remove(cfgmod.STATE_DIR / ".secret_key")
    except FileNotFoundError:
        pass
    secrets_store._fernet = None
    cfgmod._SETTINGS_CACHE["sig"] = None


# ---- 0. Dựng hiện trường: có mật khẩu + 2FA bật hẳn hoi ----
_cfg0 = cfgmod.read_settings()
_h, _s = cfgmod.hash_password("mat-khau-manh")
_cfg0["auth"].update({"username": "chu-nha", "password_hash": _h, "salt": _s})
cfgmod.write_settings(_cfg0)
cfgmod.totp_set(secret="JBSWY3DPEHPK3PXP", enabled=True,
                recovery=["ABCD-EFGH", "JKMN-PQRS"], last_step=7)
check("tiền đề: 2FA đang bật, chưa hỏng",
      cfgmod.totp_enabled() and not cfgmod.totp_hong())
raw = json.loads(cfgmod.SETTINGS_PATH.read_text(encoding="utf-8"))
check("tiền đề: secret nằm dạng enc: trong file",
      str(raw["auth"]["totp"]["secret"]).startswith("enc:"))

# ---- 1. Mất key → phải HỎNG CÓ TIẾNG ----
_mat_key()
check("CANARY: totp_hong bắt được trạng thái khoá hỏng", cfgmod.totp_hong())
check("totp_enabled vẫn False (không giả vờ chạy được)", not cfgmod.totp_enabled())
check("secret_paths_hong liệt kê đúng auth.totp.secret",
      "auth.totp.secret" in cfgmod.secret_paths_hong())

# ---- 2. Vòng ghi không được PHÁ blob ----
blob_truoc = raw["auth"]["totp"]["secret"]
cfgmod.write_settings(cfgmod.read_settings())        # một lần lưu settings bất kỳ
raw2 = json.loads(cfgmod.SETTINGS_PATH.read_text(encoding="utf-8"))
check("CANARY: blob mã hoá SỐNG SÓT qua write_settings khi khoá đang lỗi",
      raw2["auth"]["totp"]["secret"] == blob_truoc)

# Khôi phục lại là đường quan trọng nhất của việc giữ blob: tìm lại được key cũ thì
# 2FA sống lại nguyên vẹn, không cần bật lại.
# (mô phỏng: không kiểm được vì key cũ đã sinh ngẫu nhiên - kiểm chiều ngược: blob còn
# thì totp_hong vẫn báo hỏng chứ không báo "chưa bật")
check("trạng thái sau ghi vẫn là HỎNG, không tụt về 'chưa bật'", cfgmod.totp_hong())

# ---- 3. Mã khôi phục (băm, không mã hoá) vẫn tiêu được - đường vào fail-closed ----
check("mã khôi phục vẫn dùng được khi khoá hỏng",
      cfgmod.totp_dung_ma_khoi_phuc("abcd efgh"))
check("mã khôi phục tiêu xong là hết (còn 1)", cfgmod.totp_recovery_left() == 1)

# ---- 4. Tắt 2FA thật vẫn xoá được (nhánh giữ-blob không cản đường tắt) ----
cfgmod.totp_tat()
raw3 = json.loads(cfgmod.SETTINGS_PATH.read_text(encoding="utf-8"))
check("totp_tat vẫn xoá sạch được secret", raw3["auth"]["totp"]["secret"] == ""
      and not raw3["auth"]["totp"]["enabled"])
check("tắt xong thì hết hỏng, về 'chưa bật' thật", not cfgmod.totp_hong())

# ---- 5. Đối chiếu dây nối: cổng đăng nhập + status + UI ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: cổng đăng nhập fail-closed (hỏi mã cả khi khoá hỏng)",
      "cfgmod.totp_enabled(cfg) or _tfa_hong" in src)
check("/auth/status lộ totp_broken cho UI", '"totp_broken"' in src)
check("khởi động hô to danh sách secret hỏng", "secret_paths_hong()" in src)

cjs = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
# Chữ đã dời vào từ điển i18n (0.55.14) nên không còn nằm thẳng trong console.js. Bằng chứng
# bây giờ phải đi HAI VẾ: console.js gọi đúng khoá, VÀ khoá đó mang đúng câu tiếng Việt. Chỉ
# kiểm một vế là hở: kiểm mỗi khoá thì đổi nội dung khoá thành "Chưa bật" vẫn xanh, còn kiểm
# mỗi từ điển thì gỡ hẳn lời cảnh báo khỏi giao diện cũng vẫn xanh.
_VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
check("thẻ Tài khoản có nhánh khoá hỏng (không hiện 'Chưa bật' nữa)",
      "a.totp_broken" in cjs
      and "cs.tfa_broken_a" in cjs and "khoá bị lỗi" in _VI.get("cs.tfa_broken_a", "")
      and "cs.tfa_row_broken" in cjs and "khoá bị lỗi" in _VI.get("cs.tfa_row_broken", ""))
check("có đường 'bật lại với khoá mới' ngay trên UI",
      "cs.tfa_reenable" in cjs and _VI.get("cs.tfa_reenable") == "Bật lại xác thực 2 lớp")

_td.cleanup()
if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_2fa_mat_khoa_khong_im_lang: tat ca pass")
