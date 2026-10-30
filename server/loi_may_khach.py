"""Hộp đen lỗi giao diện (0.416.0): lỗi JS xảy ra trên trình duyệt của người dùng, gom về máy chủ.

Vì sao: ngày 30/10/2026 một khách báo "dùng đơ" kèm ảnh chụp, và phải dựng lại từ ảnh mới biết trang đã nhận về trang
lỗi HTML thay vì JSON. Lỗi giao diện chỉ sống trong trình duyệt của người gặp nó; không ai thấy nếu họ không chụp màn
hình gửi đi. dashboard/loi-may-khach.js bắt `error` và `unhandledrejection`, gửi về đây; trang Sức khoẻ (health-panel.js)
liệt kê theo nhóm.

Giới hạn để hộp đen không thành chỗ phình: gom theo (thông điệp, file, dòng), giữ tối đa 100 nhóm (bỏ nhóm cũ nhất),
mỗi lượt gửi tối đa 20 lỗi, cắt độ dài từng trường. Chỉ chứa lỗi kỹ thuật (thông điệp, file, dòng, ngăn xếp gọi hàm,
trình duyệt), không chứa nội dung chat.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import config as cfgmod

TOI_DA_NHOM = 100
TOI_DA_MOI_LUOT = 20
_KHOA = threading.Lock()


def _tep() -> Path:
    return Path(cfgmod.STATE_DIR) / "client_errors.json"


def _doc() -> list:
    try:
        d = json.loads(_tep().read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _ghi(ds: list) -> None:
    p = _tep()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(ds, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _cat(v, n: int) -> str:
    return str(v if v is not None else "")[:n]


def _so(v) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def ghi(payload: dict, ua: str = "") -> int:
    """Nhận một lượt gửi {version, errors: [...]}. Trả số lỗi đã ghi."""
    if not isinstance(payload, dict):
        return 0
    loi = payload.get("errors")
    if not isinstance(loi, list):
        return 0
    phien_ban = _cat(payload.get("version"), 40)
    ua = _cat(ua or payload.get("ua"), 200)
    bay = int(time.time())
    so = 0
    with _KHOA:
        ds = _doc()
        theo_khoa = {g.get("key"): g for g in ds if isinstance(g, dict)}
        # Thứ tự "mới nhất" theo số tăng dần, không theo giây: hai lỗi trong cùng một giây vẫn xếp đúng.
        stt = max([int(g.get("seq") or 0) for g in ds if isinstance(g, dict)] or [0])
        for e in loi[:TOI_DA_MOI_LUOT]:
            if not isinstance(e, dict):
                continue
            msg = _cat(e.get("msg"), 500).strip()
            if not msg:
                continue
            src = _cat(e.get("src"), 200)
            dong = _so(e.get("dong"))
            khoa = hashlib.sha1(f"{msg}|{src}|{dong}".encode("utf-8")).hexdigest()[:16]
            g = theo_khoa.get(khoa)
            if g is None:
                g = {"key": khoa, "msg": msg, "src": src, "dong": dong, "cot": _so(e.get("cot")),
                     "loai": _cat(e.get("loai"), 20), "stack": _cat(e.get("stack"), 2000),
                     "count": 0, "first_at": bay}
                theo_khoa[khoa] = g
                ds.append(g)
            g["count"] = int(g.get("count") or 0) + 1
            g["last_at"] = bay
            stt += 1
            g["seq"] = stt
            g["version"] = phien_ban
            g["ua"] = ua
            g["trang"] = _cat(e.get("trang"), 60)
            so += 1
        if so:
            ds.sort(key=lambda x: x.get("seq") or 0)
            ds = ds[-TOI_DA_NHOM:]
            _ghi(ds)
    return so


def danh_sach() -> list:
    """Các nhóm lỗi, mới nhất trước."""
    with _KHOA:
        ds = _doc()
    return sorted(ds, key=lambda x: x.get("seq") or 0, reverse=True)


def xoa_het() -> None:
    with _KHOA:
        try:
            _tep().unlink()
        except OSError:
            pass
