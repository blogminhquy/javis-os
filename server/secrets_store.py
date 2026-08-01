"""
Mã hoá secret (API key / token MCP) at rest bằng Fernet (AES128-CBC + HMAC).
- Key máy: STATE_DIR/.secret_key - sinh 1 lần, không commit (STATE_DIR gitignored).
- Giá trị đã mã hoá có prefix "enc:". Thiếu lib cryptography → fallback "plain:" + cảnh báo
  (không chặn người dùng; cài `pip install cryptography` để bật mã hoá).
- Mất file key → decrypt trả "" (user nhập lại key cho connection) - chấp nhận được, an toàn hơn lộ key.
"""
import os
import sys

from config import STATE_DIR

_KEY_PATH = STATE_DIR / ".secret_key"
_fernet = None          # None = chưa init; False = thiếu lib/lỗi; object = sẵn sàng


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet or None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("[secrets] thiếu lib cryptography - secret lưu 'plain:' (chạy: pip install cryptography)",
              file=sys.stderr)
        _fernet = False
        return None
    try:
        if _KEY_PATH.exists():
            key = _KEY_PATH.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            _KEY_PATH.write_bytes(key)
            try:
                os.chmod(_KEY_PATH, 0o600)
            except Exception:
                pass
        _fernet = Fernet(key)
    except Exception as e:
        print(f"[secrets] không init được key: {e}", file=sys.stderr)
        _fernet = False
        return None
    return _fernet


def encrypt(value):
    """Mã hoá 1 chuỗi. Idempotent: giá trị đã 'enc:'/'plain:' hoặc rỗng → giữ nguyên."""
    if not isinstance(value, str) or not value or value.startswith(("enc:", "plain:")):
        return value
    f = _get_fernet()
    if not f:
        return "plain:" + value
    return "enc:" + f.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value):
    """Giải mã. Giá trị legacy không prefix (registry cũ chưa mã hoá) → trả nguyên văn."""
    if not isinstance(value, str) or not value:
        return value or ""
    if value.startswith("plain:"):
        return value[len("plain:"):]
    if value.startswith("enc:"):
        f = _get_fernet()
        if not f:
            print("[secrets] gặp giá trị enc: nhưng thiếu cryptography/key - trả rỗng", file=sys.stderr)
            return ""
        try:
            return f.decrypt(value[len("enc:"):].encode("ascii")).decode("utf-8")
        except Exception:
            print("[secrets] giải mã thất bại (file key đổi?) - cần nhập lại secret", file=sys.stderr)
            return ""
    return value


def encryption_available() -> bool:
    """Evidence/tool artifact dùng fail-closed; không chấp nhận fallback ``plain:``."""
    return _get_fernet() is not None


def encrypt_required(value: str) -> str:
    """Mã hoá bắt buộc, raise nếu máy chưa có Fernet/key hợp lệ."""
    if not isinstance(value, str):
        raise TypeError("value_must_be_text")
    f = _get_fernet()
    if f is None:
        raise RuntimeError("encryption_unavailable")
    return "enc:" + f.encrypt(value.encode("utf-8")).decode("ascii")


def encrypt_map(d):
    return {k: encrypt(v) for k, v in (d or {}).items()}


def decrypt_map(d):
    return {k: decrypt(v) for k, v in (d or {}).items()}
