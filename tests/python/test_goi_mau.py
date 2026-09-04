"""Một gói THẬT đi trọn vòng: soi -> cài -> gọi tool -> gỡ, kể cả khi người dùng đã sửa.

    python tests/run.py goi_mau

Không cần pytest, không chạm mạng, không đụng brain thật.

Vì sao tồn tại, tách khỏi `test_goi_chay_ma.py` (vốn cũng cài một gói): gói ở đây mang ĐỦ HAI
loại năng lực có vòng đời khác nhau, và chính chỗ khác nhau đó mới là thứ dễ sai:

  - Plugin nằm TRONG thư mục gói. Gỡ là `rmtree`, không ai mất gì.
  - Kỹ năng nằm trong BRAIN của người dùng, và brain là nơi họ SỬA. Gỡ mà xoá nhầm công của
    họ là loại lỗi tệ nhất một trình cài có thể gây ra: gói cài lại được trong ba giây, còn
    thứ họ viết thì không.

Gói dựng ngay trong test chứ không đọc từ đĩa. Trước 0.55.30 nó đọc `examples/packs/`, nhưng
gói thật đã dọn sang repo kho riêng (`blogminhquy/javis-store`) - và một test của Javis OS thì
không được phụ thuộc vào nội dung một repo khác, càng không phụ thuộc vào mạng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
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

PACK_ID = "javis.tinh-gia"
TOOL = "javis_tinh_gia_ban"

MANIFEST = """format: javis-pack
spec: 1
id: javis.tinh-gia
version: 1.0.0
name: {vi: "Tính giá bán"}
description: {vi: "Từ giá vốn ra giá niêm yết."}
compat: {app: ">=0.55.25"}
provides:
  plugins: [plugins/tinh-gia]
  skills: [skills/dat-gia-ban]
"""

PLUGIN_YAML = """name: Tính giá bán
slug: tinh-gia
version: 1.0.0
enabled: true
min_mode: readonly
tools:
  - javis_tinh_gia_ban
hooks: []
"""

# Giữ đúng phần lõi của gói thật trong kho: nhận giá vốn cộng biên, làm tròn LÊN giá cuối, rồi
# trả về BIÊN THỰC TẾ sau khi tròn. Con số kỳ vọng bên dưới tính từ đúng công thức này.
PLUGIN_PY = '''import json, math


def _tinh(args, ctx):
    args = args or {}
    try:
        von = float(args.get("gia_von"))
    except (TypeError, ValueError):
        return "ERROR: 'gia_von' phai la so."
    if von <= 0:
        return "ERROR: 'gia_von' phai lon hon 0."
    bien = float(args.get("bien_loi_nhuan", 30))
    if bien >= 100:
        return "ERROR: 'bien_loi_nhuan' phai nho hon 100."
    vat = float(args.get("vat", 0))
    buoc = float(args.get("lam_tron", 1000))
    can = von / (1 - bien / 100.0) * (1 + vat / 100.0)
    niem_yet = math.ceil(can / buoc) * buoc if buoc > 0 else can
    truoc_vat = niem_yet / (1 + vat / 100.0)
    lai = truoc_vat - von
    return json.dumps({"gia_niem_yet": round(niem_yet, 2),
                       "bien_loi_nhuan_thuc": round(lai / truoc_vat * 100.0, 2)},
                      ensure_ascii=False)


def register(ctx):
    ctx.register_tool(name="javis_tinh_gia_ban", description="Tinh gia ban tu gia von",
                      handler=_tinh, min_mode="readonly",
                      schema={"type": "object",
                              "properties": {"gia_von": {"type": "number"}},
                              "required": ["gia_von"]})
'''

SKILL_MD = """---
name: Đặt giá bán
description: Phân biệt biên lợi nhuận với markup khi đặt giá bán.
group: Bán hàng
---

# Đặt giá bán

Biên tính trên giá BÁN, markup tính trên giá VỐN. Hỏi lại trước khi tính.
"""

_fails = []


def check(ten, cond):
    print(("ok   " if cond else "FAIL ") + ten)
    if not cond:
        _fails.append(ten)


def dung_zip() -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("javis-pack.yaml", MANIFEST)
        z.writestr("plugins/tinh-gia/plugin.yaml", PLUGIN_YAML)
        z.writestr("plugins/tinh-gia/plugin.py", PLUGIN_PY)
        z.writestr("skills/dat-gia-ban/SKILL.md", SKILL_MD)
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
        du = dung_zip()

        # --------------- 1. Soi: nói đúng gói có gì, TRƯỚC khi cài gì ---------------
        r = pack_install.soi(du, "javis-tinh-gia.zip")
        check("gói đọc được bằng bản Javis hiện tại", r.get("ok") is True)
        check("id khớp tên khai trong manifest", r.get("id") == PACK_ID)
        check("xếp đúng bậc code vì có tệp .py", r.get("tier") == "code")
        check("liệt kê plugin trong gói", r.get("plugins") == ["tinh-gia"])
        check("liệt kê kỹ năng sẽ ghi vào brain",
              (r.get("vault") or {}).get("skills") == ["dat-gia-ban"])
        check("không phần nào của gói bị bỏ qua vì lỗi", not r.get("error"))
        check("tool chưa tồn tại khi mới chỉ soi", not route_co(TOOL))

        # --------------- 2. Cài: tool ra tới hub, kỹ năng vào brain ---------------
        c = pack_install.cai(r["staging_id"], r["sha256"], enable=True, brain_root=str(brain))
        check("cài xong", c.get("ok") is True)
        check("kỹ năng được thêm vào brain đang mở",
              [x["khoa"] for x in (c.get("vault") or {}).get("them") or []]
              == ["skills/dat-gia-ban"])
        sk = brain / "skills" / "dat-gia-ban" / "SKILL.md"
        check("và tệp có thật trên đĩa", sk.is_file())

        the = {x["slug"]: x for x in plugins_host.describe()}
        check("thẻ plugin ghi nguồn là 'pack'", the.get("tinh-gia", {}).get("source") == "pack")
        check("và đang nạp thật, không phải 'bật (chưa nạp)'",
              the.get("tinh-gia", {}).get("loaded") is True)
        check("tool ra tới hub cho mọi engine", route_co(TOOL))

        # --------------- 3. Gọi thật: số phải đúng, không chỉ có mặt ---------------
        _, route = plugins_host.plugin_tools("full", None)
        d = json.loads(asyncio.run(route[TOOL]["call"]({"gia_von": 120000, "vat": 8})))
        check("gọi tool ra giá niêm yết đã tròn và đã gồm VAT", d["gia_niem_yet"] == 186000.0)
        check("và trả BIÊN THỰC sau khi tròn, không trả lại con số vừa nhập",
              d["bien_loi_nhuan_thuc"] != 30.0 and 30.0 < d["bien_loi_nhuan_thuc"] < 31.0)
        loi = asyncio.run(route[TOOL]["call"]({"gia_von": 100, "bien_loi_nhuan": 120}))
        check("đầu vào sai trả câu ERROR đọc được chứ không ném exception",
              isinstance(loi, str) and loi.startswith("ERROR:"))

        # --------------- 4. Gỡ khi người dùng ĐÃ SỬA kỹ năng: phải giữ lại ---------------
        sk.write_bytes(sk.read_bytes() + "\n\nGhi chú riêng của tôi.\n".encode("utf-8"))
        ke = pack_install.ke_hoach_go(PACK_ID)
        check("hộp gỡ báo TRƯỚC là sẽ giữ mục đã sửa",
              [x["slug"] for x in (ke.get("vault") or {}).get("giu") or []] == ["dat-gia-ban"])

        g = asyncio.run(pack_install.go(PACK_ID))
        check("gỡ xong", g.get("ok") is True)
        check("tool biến khỏi mọi engine", not route_co(TOOL))
        check("thư mục gói không còn", not (packs.PACKS_DIR / PACK_ID).exists())
        check("kỹ năng đã sửa thì GIỮ LẠI", sk.is_file())

        # --------------- 5. Cài lại rồi gỡ khi CHƯA sửa: phải sạch bong ---------------
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
