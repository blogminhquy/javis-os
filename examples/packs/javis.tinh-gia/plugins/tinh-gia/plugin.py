"""Tool mẫu: tính giá bán từ giá vốn. Thuần stdlib, chỉ đọc, không chạm mạng.

Đây là bản tham chiếu nhỏ nhất của một plugin trong gói. Ba điều đáng chép lại khi viết
plugin của riêng bạn:

1. `register(ctx)` là toàn bộ hợp đồng. Handler nhận `(args: dict, ctx)` và trả về CHUỖI.
2. Sai đầu vào thì trả chuỗi bắt đầu bằng `ERROR:` chứ đừng ném exception. Model đọc được
   câu đó và tự sửa tham số ở lượt sau; một traceback thì nó chỉ biết là hỏng.
3. Tên tool nên mang tiền tố của gói bạn. Ở đây dùng `javis_` vì gói này là của chính
   Javis; gói của bên thứ ba nên dùng tên riêng để không đụng tool có sẵn.

Vì sao làm tròn giá ĐÃ CÓ VAT
-----------------------------
Số người mua nhìn thấy trên tem là số cuối cùng, nên nó mới là số đáng đẹp. Làm tròn giá
chưa VAT rồi mới cộng thuế sẽ ra những con số như 341.000, và cái tem đó không ai dán.
Làm tròn ở cuối thì biên lợi nhuận xê dịch một chút so với lúc đặt ra, nên tool trả về
BIÊN THỰC TẾ sau khi đã tròn, chứ không trả lại con số bạn vừa nhập vào.
"""
from __future__ import annotations

import json
import math


def _so(v, ten, mac_dinh=None):
    """Đọc một số từ args. Trả (giá_trị, lỗi) - lỗi là chuỗi hoặc None."""
    if v is None or v == "":
        return mac_dinh, None
    try:
        # Chấp cả "1.200.000" và "1200000": người dùng dán số từ bảng giá ra là có dấu chấm.
        if isinstance(v, str):
            v = v.replace(".", "").replace(",", ".").strip()
        return float(v), None
    except (TypeError, ValueError):
        return None, f"ERROR: '{ten}' phải là số."


def _tron_len(x, buoc):
    if buoc and buoc > 0:
        return math.ceil(x / buoc) * buoc
    return x


def _tinh(args, ctx):
    args = args or {}

    gia_von, loi = _so(args.get("gia_von"), "gia_von")
    if loi:
        return loi
    if gia_von is None:
        return "ERROR: thiếu 'gia_von' (giá vốn một đơn vị)."
    if gia_von <= 0:
        return "ERROR: 'gia_von' phải lớn hơn 0."

    bien, loi = _so(args.get("bien_loi_nhuan"), "bien_loi_nhuan", 30.0)
    if loi:
        return loi
    if bien >= 100:
        # Biên 100% nghĩa là giá vốn bằng 0 phần trăm của giá bán, tức giá bán vô hạn.
        # Đây gần như luôn là nhầm biên với markup, nên nói thẳng ra chỗ nhầm.
        return ("ERROR: 'bien_loi_nhuan' phải nhỏ hơn 100. Biên tính trên GIÁ BÁN. "
                "Nếu bạn đang nghĩ tới phần cộng thêm vào giá vốn thì đó là markup, "
                "hãy dùng 'ty_le_markup'.")

    markup, loi = _so(args.get("ty_le_markup"), "ty_le_markup")
    if loi:
        return loi

    vat, loi = _so(args.get("vat"), "vat", 0.0)
    if loi:
        return loi
    if vat < 0:
        return "ERROR: 'vat' không âm được."

    buoc, loi = _so(args.get("lam_tron"), "lam_tron", 1000.0)
    if loi:
        return loi
    if buoc < 0:
        return "ERROR: 'lam_tron' không âm được (0 = không làm tròn)."

    # Markup nếu có thì THẮNG, vì người nhập nó là người đang nghĩ theo lối "cộng bao nhiêu
    # phần trăm lên giá vốn" và không nên bị con số biên mặc định đè lên.
    if markup is not None:
        can_truoc_vat = gia_von * (1 + markup / 100.0)
        cach_dat = "markup"
    else:
        can_truoc_vat = gia_von / (1 - bien / 100.0)
        cach_dat = "bien_loi_nhuan"

    niem_yet = _tron_len(can_truoc_vat * (1 + vat / 100.0), buoc)
    thuc_truoc_vat = niem_yet / (1 + vat / 100.0)
    lai = thuc_truoc_vat - gia_von

    ra = {
        "gia_niem_yet": round(niem_yet, 2),
        "gia_truoc_vat": round(thuc_truoc_vat, 2),
        "gia_von": round(gia_von, 2),
        "lai_moi_don_vi": round(lai, 2),
        "bien_loi_nhuan_thuc": round(lai / thuc_truoc_vat * 100.0, 2) if thuc_truoc_vat else 0.0,
        "markup_tuong_duong": round(lai / gia_von * 100.0, 2),
        "vat": round(vat, 2),
        "lam_tron_theo": round(buoc, 2),
        "dat_theo": cach_dat,
    }
    ra["tom_tat"] = (
        f"Giá vốn {ra['gia_von']:,.0f} -> niêm yết {ra['gia_niem_yet']:,.0f}"
        + (f" (đã gồm VAT {ra['vat']:g}%)" if vat else "")
        + f", lãi {ra['lai_moi_don_vi']:,.0f} một đơn vị, "
        + f"biên thực {ra['bien_loi_nhuan_thuc']:g}%."
    )
    return json.dumps(ra, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(
        name="javis_tinh_gia_ban",
        description=(
            "Tính giá bán từ giá vốn. Tham số: gia_von (bắt buộc), bien_loi_nhuan (%, tính "
            "trên giá bán, mặc định 30), ty_le_markup (%, cộng lên giá vốn - nhập cái này thì "
            "nó thắng bien_loi_nhuan), vat (%, mặc định 0), lam_tron (bội số làm tròn lên, mặc "
            "định 1000, 0 là không tròn). Trả về giá niêm yết, lãi một đơn vị và BIÊN THỰC TẾ "
            "sau khi làm tròn."
        ),
        handler=_tinh,
        min_mode="readonly",
        emoji="🏷️",
        schema={
            "type": "object",
            "properties": {
                "gia_von": {"type": "number", "description": "Giá vốn một đơn vị"},
                "bien_loi_nhuan": {"type": "number",
                                   "description": "Biên lợi nhuận mong muốn, phần trăm trên GIÁ BÁN (mặc định 30)"},
                "ty_le_markup": {"type": "number",
                                 "description": "Phần trăm cộng thêm lên GIÁ VỐN. Nhập thì thắng bien_loi_nhuan"},
                "vat": {"type": "number", "description": "Thuế suất VAT phần trăm (mặc định 0)"},
                "lam_tron": {"type": "number",
                             "description": "Làm tròn LÊN theo bội số này (mặc định 1000, 0 = không làm tròn)"},
            },
            "required": ["gia_von"],
        },
    )
