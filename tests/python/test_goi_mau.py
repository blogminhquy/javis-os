"""Gói mẫu `examples/packs/javis.tinh-gia` chạy được thật, đủ vòng cài -> dùng -> gỡ.

    python tests/run.py goi_mau

Không cần pytest, không chạm mạng, không đụng brain thật.

Vì sao một ví dụ cần test riêng: một ví dụ HỎNG tệ hơn không có ví dụ nào. Người viết gói đầu
tiên sẽ chép thư mục này làm khuôn, nên nếu hợp đồng plugin đổi, hay `spec` lên 2, hay tên
trường trong manifest đổi, thì ví dụ phải đỏ ở đây chứ không phải im lặng rồi hỏng trên máy
người lạ vào sáu tháng sau.

Test này cũng là bản mô tả sống của toàn bộ luồng: đọc từ trên xuống là thấy đúng thứ tự mà
trang Kho cài đặt làm việc - soi trước, hỏi sau, cài, rồi gỡ và kiểm xem còn sót gì.
"""
from _paths import ROOT  # noqa: E402,F401
import asyncio
import io
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import pack_install
import pack_vault
import packs
import plugins_host

NGUON = ROOT / "examples" / "packs" / "javis.tinh-gia"
PACK_ID = "javis.tinh-gia"
TOOL = "javis_tinh_gia_ban"

_fails = []


def check(ten, cond):
    print(("ok   " if cond else "FAIL ") + ten)
    if not cond:
        _fails.append(ten)


def _dong_goi_mod():
    """Nạp chính `examples/packs/dong-goi.py` để test dùng ĐÚNG thuật toán đóng gói thật.

    Không chép lại logic sang đây: hai bản sao sẽ lệch, và lúc lệch thì test báo đỏ vì lý do
    sai (thuật toán test cũ) chứ không phải vì gói hỏng. Tên tệp có dấu gạch nên phải nạp
    bằng đường dẫn."""
    import importlib.util
    p = ROOT / "examples" / "packs" / "dong-goi.py"
    spec = importlib.util.spec_from_file_location("dong_goi", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dong_zip(src: Path) -> bytes:
    """Đóng gói y như `examples/packs/dong-goi.py`, nhưng vào bộ nhớ."""
    dg = _dong_goi_mod()
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if not p.is_file() or any(x in p.parts for x in dg.BO_QUA):
                continue
            it = zipfile.ZipInfo(str(p.relative_to(src)).replace("\\", "/"), dg.NGAY_GHIM)
            it.compress_type = zipfile.ZIP_DEFLATED
            it.external_attr = 0o644 << 16
            z.writestr(it, p.read_bytes())
    return b.getvalue()


def route_co(ten):
    plugins_host.invalidate()
    _, route = plugins_host.plugin_tools("full", None)
    return ten in route


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    goc = (packs.PACKS_DIR, packs.LEDGER, pack_install.LEDGER, pack_install.STAGING,
           plugins_host._STATE_PATH, pack_vault.HIEU_UNG_DIR)
    packs.PACKS_DIR = tmp / "packs"
    packs.LEDGER = pack_install.LEDGER = tmp / "packs.json"
    pack_install.STAGING = tmp / "packs-staging"
    plugins_host._STATE_PATH = tmp / "plugins.json"
    pack_vault.HIEU_UNG_DIR = tmp / "packs-state"
    packs.PACKS_DIR.mkdir()
    brain = tmp / "brain"
    (brain / "skills").mkdir(parents=True)
    try:
        packs.invalidate()
        plugins_host.invalidate()
        plugins_host._STATE_CACHE.update(sig=None, data=None)
        du = dong_zip(NGUON)

        # ─────────────── 0. Tệp đã phát hành khớp ĐÚNG mã nguồn ───────────────
        # Đóng gói tái lập được nên hai thứ này phải bằng nhau từng byte. Lệch nghĩa là ai đó
        # sửa nguồn mà quên đóng lại, và kho đang phát một bản khác thứ repo công bố - loại
        # sai lệch mà không ai phát hiện ra bằng mắt.
        _ship = ROOT / "system" / "packs" / "javis-tinh-gia-1.0.0.zip"
        check("tệp phát hành trong kho khớp từng byte với mã nguồn",
              _ship.is_file() and _ship.read_bytes() == du)

        # ─────────────── 1. Soi: nói đúng gói có gì, TRƯỚC khi cài gì ───────────────
        r = pack_install.soi(du, "javis-tinh-gia.zip")
        check("gói mẫu còn đọc được bằng bản Javis hiện tại", r.get("ok") is True)
        check("id khớp tên thư mục", r.get("id") == PACK_ID)
        check("xếp đúng bậc code vì có tệp .py", r.get("tier") == "code")
        check("liệt kê plugin trong gói", r.get("plugins") == ["tinh-gia"])
        check("liệt kê kỹ năng sẽ ghi vào brain",
              (r.get("vault") or {}).get("skills") == ["dat-gia-ban"])
        check("gói mẫu cố ý KHÔNG mang connector", not r.get("connectors"))
        check("không phần nào của gói bị bỏ qua vì lỗi", not r.get("error"))
        check("tool chưa tồn tại khi mới chỉ soi", not route_co(TOOL))

        # ─────────────── 2. Cài: tool ra tới hub, kỹ năng vào brain ───────────────
        c = pack_install.cai(r["staging_id"], r["sha256"], enable=True, brain_root=str(brain))
        check("cài xong", c.get("ok") is True)
        check("kỹ năng được thêm vào brain đang mở",
              [x["khoa"] for x in (c.get("vault") or {}).get("them") or []]
              == ["skills/dat-gia-ban"])
        check("và tệp có thật trên đĩa",
              (brain / "skills" / "dat-gia-ban" / "SKILL.md").is_file())

        the = {x["slug"]: x for x in plugins_host.describe()}
        check("thẻ plugin ghi nguồn là 'pack'", the.get("tinh-gia", {}).get("source") == "pack")
        check("và đang nạp thật, không phải 'bật (chưa nạp)'",
              the.get("tinh-gia", {}).get("loaded") is True)
        check("tool ra tới hub cho mọi engine", route_co(TOOL))

        # ─────────────── 3. Gọi thật: số phải đúng, không chỉ có mặt ───────────────
        _, route = plugins_host.plugin_tools("full", None)
        d = json.loads(asyncio.run(route[TOOL]["call"]({"gia_von": 120000, "vat": 8})))
        check("gọi tool ra giá niêm yết đã tròn và đã gồm VAT", d["gia_niem_yet"] == 186000.0)
        check("và trả BIÊN THỰC sau khi tròn, không trả lại con số vừa nhập",
              d["bien_loi_nhuan_thuc"] != 30.0 and 30.0 < d["bien_loi_nhuan_thuc"] < 31.0)
        d2 = json.loads(asyncio.run(route[TOOL]["call"]({"gia_von": 120000, "ty_le_markup": 30,
                                                        "lam_tron": 0})))
        check("markup 30% ra khác biên 30% (đây là chỗ người dùng hay nhầm)",
              d2["gia_niem_yet"] == 156000.0)
        loi = asyncio.run(route[TOOL]["call"]({"gia_von": 100, "bien_loi_nhuan": 120}))
        check("đầu vào sai trả câu ERROR đọc được chứ không ném exception",
              isinstance(loi, str) and loi.startswith("ERROR:"))

        # ─────────────── 4. Gỡ khi người dùng ĐÃ SỬA kỹ năng: phải giữ lại ───────────────
        sk = brain / "skills" / "dat-gia-ban" / "SKILL.md"
        sk.write_bytes(sk.read_bytes() + "\n\nGhi chú riêng của tôi.\n".encode("utf-8"))
        ke = pack_install.ke_hoach_go(PACK_ID)
        check("hộp gỡ báo TRƯỚC là sẽ giữ mục đã sửa",
              [x["slug"] for x in (ke.get("vault") or {}).get("giu") or []] == ["dat-gia-ban"])

        g = asyncio.run(pack_install.go(PACK_ID))
        check("gỡ xong", g.get("ok") is True)
        check("tool biến khỏi mọi engine", not route_co(TOOL))
        check("thư mục gói không còn", not (packs.PACKS_DIR / PACK_ID).exists())
        check("kỹ năng đã sửa thì GIỮ LẠI", sk.is_file())

        # ─────────────── 5. Cài lại rồi gỡ khi CHƯA sửa: phải sạch bong ───────────────
        shutil.rmtree(brain / "skills" / "dat-gia-ban")
        r2 = pack_install.soi(du, "javis-tinh-gia.zip")
        pack_install.cai(r2["staging_id"], r2["sha256"], enable=True, brain_root=str(brain))
        check("cài lại lần hai được", sk.is_file())
        asyncio.run(pack_install.go(PACK_ID))
        check("chưa sửa gì thì gỡ xoá sạch kỹ năng",
              not (brain / "skills" / "dat-gia-ban").exists())
        check("sổ hiệu ứng dọn theo, không để lại vết",
              not (pack_vault.HIEU_UNG_DIR / f"{PACK_ID}.json").exists())
    finally:
        (packs.PACKS_DIR, packs.LEDGER, pack_install.LEDGER, pack_install.STAGING,
         plugins_host._STATE_PATH, pack_vault.HIEU_UNG_DIR) = goc

print()
if _fails:
    print(f"{len(_fails)} kiểm tra ĐỎ: " + "; ".join(_fails))
    sys.exit(1)
print("Gói mẫu: tất cả xanh.")
