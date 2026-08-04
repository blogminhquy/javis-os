"""Hồ sơ kết nối của CLI: đọc/ghi ~/.javis/config.json, và biến môi trường đè lên file.

Vì sao có biến môi trường đè: CI, Docker và script chạy nền không có chỗ nào để mount một
file cấu hình cho tử tế. `JAVIS_URL` + `JAVIS_TOKEN` là đường vào không cần trạng thái.
"""
import json
import os
from pathlib import Path

DUONG_DAN = Path(os.path.expanduser("~")) / ".javis" / "config.json"


def _doc() -> dict:
    try:
        if DUONG_DAN.is_file():
            d = json.loads(DUONG_DAN.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except Exception:
        pass
    return {}


def _ghi(d: dict):
    DUONG_DAN.parent.mkdir(parents=True, exist_ok=True)
    DUONG_DAN.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        # File này chứa token có quyền ngang phiên đăng nhập. 600 hay không là khác biệt giữa
        # "chỉ mình đọc được" và "mọi tài khoản trên máy đọc được".
        os.chmod(DUONG_DAN, 0o600)
    except Exception:
        pass


def ho_so(ten: str = "") -> dict:
    """Hồ sơ đang dùng: {url, token, brain, ten}. Biến môi trường THẮNG file."""
    d = _doc()
    ten = ten or os.getenv("JAVIS_PROFILE") or d.get("default") or ""
    p = dict((d.get("profiles") or {}).get(ten) or {})
    if os.getenv("JAVIS_URL"):
        p["url"] = os.environ["JAVIS_URL"]
    if os.getenv("JAVIS_TOKEN"):
        p["token"] = os.environ["JAVIS_TOKEN"]
    if os.getenv("JAVIS_BRAIN"):
        p["brain"] = os.environ["JAVIS_BRAIN"]
    p["ten"] = ten
    p["url"] = (p.get("url") or "").rstrip("/")
    return p


def luu(ten: str, url: str, token: str, brain: str = "", dat_mac_dinh: bool = True):
    d = _doc()
    d.setdefault("profiles", {})[ten] = {
        "url": (url or "").rstrip("/"), "token": token or "", "brain": brain or ""}
    if dat_mac_dinh or not d.get("default"):
        d["default"] = ten
    _ghi(d)


def danh_sach() -> dict:
    d = _doc()
    return {"default": d.get("default") or "", "profiles": d.get("profiles") or {}}
