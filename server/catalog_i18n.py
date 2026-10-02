"""Bản dịch chữ HIỂN THỊ của kho Kết nối, phủ lên lúc trả cho giao diện (0.67.0).

`system/mcp-catalog.json` viết bằng tiếng Việt và là nguồn gốc. Bản cho thứ tiếng khác nằm
trong `system/mcp-catalog.<mã>.json`, khoá theo id connector, chỉ chứa chữ hiển thị: tên, mô tả,
dòng nhóm, cảnh báo quyền, hướng dẫn, nhãn và placeholder của ô nhập, các bước wizard, nhãn link
cài đặt. Thêm một ngôn ngữ = thêm một file dữ liệu, không sửa mã.

Vì sao là lớp phủ chứ không đổi các trường trong catalog gốc thành map {"vi":…, "en":…}: những
trường đó còn được nhiều chỗ khác đọc dưới dạng chuỗi (mô tả đi vào prompt của model, `category`
làm khoá lọc). Phủ đúng ở MỘT chỗ, lúc dựng bản cho UI (`mcp_catalog.public_catalog`), thì không
chỗ nào khác phải biết là có bản dịch.

Bước và link cài đặt khớp với bản gốc theo VỊ TRÍ. Lệch số lượng (ai đó thêm bước vào bản gốc mà
quên bản dịch) thì bước đó giữ chữ gốc, không bao giờ lệch nghĩa sang bước khác; test
`test_catalog_ban_dich.py` canh chuyện số lượng.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import lang_registry
import localefmt

_THU_MUC = Path(__file__).resolve().parent.parent / "system"
_CACHE: dict = {}   # mã -> (mtime, dữ liệu)


def _doc_lop_phu(ma: str) -> dict:
    p = _THU_MUC / f"mcp-catalog.{ma}.json"
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {}
    cu = _CACHE.get(ma)
    if cu and cu[0] == mt:
        return cu[1]
    try:
        data = (json.loads(p.read_text(encoding="utf-8")) or {}).get("connectors") or {}
    except Exception:
        data = {}   # file dịch hỏng thì hiện chữ gốc, không làm sập trang Kết nối
    _CACHE[ma] = (mt, data)
    return data


def lop_phu(ma: str) -> dict:
    """Bản dịch cho ngôn ngữ `ma`. Ngôn ngữ gốc của catalog thì không cần gì. Thứ tiếng chưa có
    file riêng thì dùng của DU_PHONG_GIAO_DIEN, cùng luật suy biến với chữ trên dashboard."""
    ma = lang_registry.chuan_hoa(ma) or lang_registry.MAC_DINH
    if ma == lang_registry.MAC_DINH:
        return {}
    return _doc_lop_phu(ma) or (
        {} if lang_registry.DU_PHONG_GIAO_DIEN == lang_registry.MAC_DINH
        else _doc_lop_phu(lang_registry.DU_PHONG_GIAO_DIEN))


def _dat(dich: dict, goc: dict, khoa: str) -> None:
    v = dich.get(khoa)
    if isinstance(v, str) and v:
        goc[khoa] = v


def phu(muc: list, ma: str | None = None) -> list:
    """Phủ bản dịch lên danh sách connector đã dựng cho UI. Không đụng tới dữ liệu gốc."""
    ban = lop_phu(ma if ma is not None else localefmt.ngon_ngu_giao_dien())
    if not ban:
        return muc
    for c in muc:
        d = ban.get(c.get("id"))
        if not isinstance(d, dict):
            continue
        for k in ("name", "description", "group_line", "guide", "risk"):
            _dat(d, c, k)
        fd = d.get("fields") or {}
        for f in c.get("fields") or []:
            _dat(fd.get(f.get("key")) or {}, f, "label")
            _dat(fd.get(f.get("key")) or {}, f, "placeholder")
        for s, sd in zip(c.get("steps") or [], d.get("steps") or []):
            if isinstance(sd, dict):
                _dat(sd, s, "text")
                _dat(sd, s, "link_label")
        links_dich = ((d.get("setup") or {}).get("links")) or []
        if links_dich and isinstance(c.get("setup"), dict) and c["setup"].get("links"):
            # `setup` là tham chiếu thẳng vào catalog gốc đang cache: chép ra trước khi sửa,
            # nếu không bản tiếng Anh dính vào catalog và lần sau tiếng Việt cũng ra tiếng Anh.
            c["setup"] = copy.deepcopy(c["setup"])
            for l, ld in zip(c["setup"]["links"], links_dich):
                if isinstance(l, dict) and isinstance(ld, dict):
                    _dat(ld, l, "label")
    return muc
