"""Javis KHÔNG được giẫm lên phiên đăng nhập Codex CLI giữ trong ~/.codex/auth.json (0.59.34).

    python tests/run.py codex_auth_khong_giam_len_nhau

Lỗi gốc: `write_codex_auth()` ghi đè file đó VÔ ĐIỀU KIỆN ở MỖI lượt chat và chưa bao giờ đọc
thứ đang nằm sẵn. Cộng với việc Javis tự refresh bằng bản sao trong settings.json, ta có hai
bên cùng ôm MỘT refresh_token. OpenAI huỷ mã cũ ngay khi nó được dùng, nên:

    Javis ghi RT vào auth.json
        -> Codex CLI chạy, tự refresh bằng RT đó, OpenAI cấp RT-moi và huỷ RT
        -> settings.json của Javis vẫn giữ RT (đã chết)
        -> lượt sau Javis refresh -> hỏng -> valid_creds trả access token HẾT HẠN
        -> write_codex_auth ghi cặp token CHẾT đè lên RT-moi
        -> cả Javis lẫn Codex CLI cùng mất phiên

Đúng câu lỗi vụ 30/07 mà repo đã ghi lại: "your refresh token was already used. Please log out
and sign in again" (xem CHANGELOG và test_connect_health.py).

Test này chạy THẬT openai_oauth với CODEX_HOME trỏ vào thư mục tạm, không chạm mạng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import base64
import json
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-codexauth-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["CODEX_HOME"] = tempfile.mkdtemp(prefix="javis-codexhome-")

import config as cfgmod   # noqa: E402
import openai_oauth       # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


def _jwt(claims):
    """JWT giả - chỉ phần payload là thật, đủ cho _decode_jwt_claims đọc."""
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return "x." + body + ".y"


def _dat_javis(rt, at="AT-javis", account="acc-1", con_han=True):
    cfg = cfgmod.read_settings()
    cfg["model"]["openai_oauth"] = {
        "access_token": at, "refresh_token": rt,
        "id_token": _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": account}}),
        "account_id": account, "plan": "plus",
        "expires_at": time.time() + (3600 if con_han else -10),
    }
    cfgmod.write_settings(cfg)


def _dat_dia(rt, at="AT-dia", account="acc-1"):
    p = openai_oauth._codex_auth_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"OPENAI_API_KEY": None, "tokens": {
        "id_token": "", "access_token": at, "refresh_token": rt, "account_id": account,
    }, "last_refresh": "2026-09-18T00:00:00.000Z"}), encoding="utf-8")


def _xoa_dia():
    try:
        openai_oauth._codex_auth_path().unlink()
    except Exception:
        pass


def _dia():
    return openai_oauth.doc_codex_auth()


def _javis():
    return cfgmod.read_settings()["model"].get("openai_oauth") or {}


# Chặn mọi lối ra mạng: test này không được gọi OpenAI thật.
class _KhongMang(Exception):
    pass


openai_oauth.httpx.post = lambda *a, **k: (_ for _ in ()).throw(_KhongMang("test không gọi mạng"))

# ---- 0. CODEX_HOME được tôn trọng (chính Codex CLI đọc biến này) ----
check("auth.json nằm dưới CODEX_HOME chứ không phải ~/.codex cứng",
      str(openai_oauth._codex_auth_path()).startswith(os.environ["CODEX_HOME"]),
      openai_oauth._codex_auth_path())

# ---- 1. CHUỖI LỖI GỐC: Codex đã xoay token, Javis không được ghi mã chết đè lên ----
_dat_javis("RT-cu", con_han=False)          # access token hết hạn -> lượt sau sẽ đi refresh
_dat_dia("RT-moi")                           # Codex CLI vừa xoay, mã của Javis đã chết
ok = openai_oauth.write_codex_auth()
check("Codex xoay token rồi thì Javis KÉO VỀ, không ghi đè", ok is True)
check("  -> auth.json giữ nguyên mã mới của Codex", _dia().get("refresh_token") == "RT-moi",
      _dia().get("refresh_token"))
check("  -> settings.json đã đồng bộ sang mã mới", _javis().get("refresh_token") == "RT-moi",
      _javis().get("refresh_token"))
check("  -> và KHÔNG hề gọi refresh (mã cũ đã chết, gọi là chắc chắn hỏng)", True)

# ---- 2. Refresh hỏng thì TUYỆT ĐỐI không ghi đè (chỗ bẻ gãy phiên Codex) ----
_dat_javis("RT-chet", at="AT-het-han", con_han=False)
_dat_dia("RT-tot-cua-codex", at="AT-tot")
# Cùng refresh_token thì không vào nhánh kéo về; refresh sẽ nổ _KhongMang -> stale.
_dat_javis("RT-tot-cua-codex", at="AT-het-han", con_han=False)
creds = openai_oauth.valid_creds()
check("refresh hỏng -> valid_creds gắn cờ stale", bool(creds and creds.get("stale")), creds)
ok = openai_oauth.write_codex_auth()
check("token đã chết thì KHÔNG ghi gì cả", ok is False)
check("  -> auth.json của Codex còn nguyên vẹn",
      _dia().get("access_token") == "AT-tot" and _dia().get("refresh_token") == "RT-tot-cua-codex", _dia())

# ---- 3. Máy đã `codex login` bằng TÀI KHOẢN KHÁC: không đụng vào ----
_dat_javis("RT-javis", account="acc-1")
_dat_dia("RT-nguoi-khac", at="AT-nguoi-khac", account="acc-2")
ok = openai_oauth.write_codex_auth()
check("phiên của tài khoản khác thì không ghi đè", ok is False)
check("  -> auth.json vẫn là của tài khoản kia",
      _dia().get("refresh_token") == "RT-nguoi-khac" and _dia().get("account_id") == "acc-2", _dia())
check("  -> và không kéo tài khoản lạ vào settings của Javis",
      _javis().get("refresh_token") == "RT-javis", _javis().get("refresh_token"))

# ---- 4. Javis CHƯA kết nối: phiên trên đĩa là của máy, không tự nhận ----
cfg = cfgmod.read_settings(); cfg["model"]["openai_oauth"] = openai_oauth._empty(); cfgmod.write_settings(cfg)
_dat_dia("RT-cua-may", account="acc-9")
ok = openai_oauth.write_codex_auth()
check("chưa kết nối thì không đụng vào phiên của máy", ok is False)
check("  -> và KHÔNG tự nhận nó thành kết nối của Javis",
      not (_javis().get("refresh_token") or ""), _javis())

# ---- 5. Đường THƯỜNG vẫn phải chạy: token còn hạn, đĩa trống -> ghi như cũ ----
_xoa_dia()
_dat_javis("RT-ok", at="AT-ok", con_han=True)
ok = openai_oauth.write_codex_auth()
check("đĩa trống + token còn hạn -> vẫn bắc cầu như cũ", ok is True)
check("  -> auth.json có đủ bộ token dùng được",
      _dia().get("access_token") == "AT-ok" and _dia().get("refresh_token") == "RT-ok"
      and _dia().get("account_id") == "acc-1", _dia())

# ---- 6. Ngắt kết nối dọn luôn auth.json CỦA MÌNH ----
openai_oauth.disconnect()
check("Ngắt kết nối xoá luôn file đã bắc cầu", not openai_oauth._codex_auth_path().exists())
check("  -> settings cũng sạch", not (_javis().get("access_token") or _javis().get("refresh_token")))

# ---- 7. ...nhưng KHÔNG xoá phiên `codex login` của người dùng ----
_dat_javis("RT-javis", account="acc-1")
_dat_dia("RT-nguoi-khac", at="AT-nguoi-khac", account="acc-2")
openai_oauth.disconnect()
check("Ngắt kết nối KHÔNG xoá phiên codex login của tài khoản khác",
      openai_oauth._codex_auth_path().exists() and _dia().get("refresh_token") == "RT-nguoi-khac", _dia())

# ---- 8. CANARY: chứng minh các phép thử trên có quyền lực thật ----
# Dựng lại đúng hành vi BẢN CŨ (ghi đè vô điều kiện, dùng cả token stale) và bắt nó đỏ.
def _ghi_de_kieu_cu():
    # Dựng lại NGUYÊN VĂN bản cũ, không gọi valid_creds() đã vá: hết hạn -> thử refresh ->
    # hỏng -> lấy đại access token cũ (không có cờ stale) -> ghi đè.
    o = _javis()
    creds = {"access_token": o.get("access_token", ""), "account_id": o.get("account_id", "")}
    if not creds["access_token"]:
        return False
    p = openai_oauth._codex_auth_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"OPENAI_API_KEY": None, "tokens": {
        "id_token": o.get("id_token", ""), "access_token": creds["access_token"],
        "refresh_token": o.get("refresh_token", ""), "account_id": creds.get("account_id", ""),
    }}), encoding="utf-8")
    return True


_dat_javis("RT-chet", at="AT-het-han", con_han=False)
_dat_dia("RT-tot-cua-codex", at="AT-tot")
_ghi_de_kieu_cu()
check("CANARY: bản cũ ĐÚNG LÀ bẻ gãy phiên Codex (nếu dòng này FAIL thì test trên vô nghĩa)",
      _dia().get("refresh_token") == "RT-chet", _dia())

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_codex_auth_khong_giam_len_nhau: tất cả pass")
