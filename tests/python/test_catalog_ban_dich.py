"""Kho Kết nối nói tiếng Anh: lớp phủ system/mcp-catalog.en.json (0.67.0).

    python tests/run.py catalog_ban_dich

Catalog gốc viết tiếng Việt; bản tiếng Anh là file lớp phủ, phủ lên lúc dựng bản cho giao diện
(server/catalog_i18n.py). Hai file sống riêng nên lệch nhau là lệch IM LẶNG: thêm một connector,
một ô nhập hay một bước wizard vào bản gốc mà quên bản dịch thì người đọc tiếng Anh thấy chữ Việt
lọt vào giữa trang. Test này bắt đúng những chỗ đó, cộng một lượt chạy thật qua public_catalog.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-cat-"))
import catalog_i18n  # noqa: E402
import localefmt  # noqa: E402
import mcp_catalog  # noqa: E402

_fails = []
DAU_VIET = re.compile("[ăđơưảãạằắẳẵặầấẩẫậẻẽẹềếểễệỉĩịỏõọồốổỗộờớởỡợủũụừứửữựỳỷỹỵ]", re.I)


def check(ten, ok, chi_tiet=""):
    print(f"{'ok  ' if ok else 'FAIL'} {ten}" + ("" if ok else f"  [{chi_tiet}]"))
    if not ok:
        _fails.append(ten)


goc = {c["id"]: c for c in json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))["connectors"]}
raw_en = (ROOT / "system" / "mcp-catalog.en.json").read_text(encoding="utf-8")
en = json.loads(raw_en)["connectors"]

check("bản dịch không nhắc connector không có trong catalog", set(en) <= set(goc), set(en) - set(goc))
thieu, lech, chu_viet = [], [], []
for cid, c in goc.items():
    a = c.get("auth") or {}
    d = en.get(cid) or {}
    # Trường nào bản gốc có chữ Việt thì bản dịch phải có.
    for k, v in (("name", c.get("name")), ("description", c.get("description")),
                 ("group_line", c.get("group_line")), ("risk", c.get("risk")), ("guide", a.get("guide"))):
        if v and DAU_VIET.search(v) and not d.get(k):
            thieu.append(f"{cid}.{k}")
    for f in a.get("fields") or []:
        fd = (d.get("fields") or {}).get(f.get("key")) or {}
        for k in ("label", "placeholder"):
            if f.get(k) and DAU_VIET.search(f[k]) and not fd.get(k):
                thieu.append(f"{cid}.fields.{f.get('key')}.{k}")
    st_goc, st_en = a.get("steps") or [], d.get("steps") or []
    if any(DAU_VIET.search(s.get("text", "")) for s in st_goc) and len(st_goc) != len(st_en):
        lech.append(f"{cid}.steps {len(st_goc)}!={len(st_en)}")
    l_goc = ((a.get("setup") or {}).get("links")) or []
    l_en = ((d.get("setup") or {}).get("links")) or []
    if any(DAU_VIET.search(x.get("label", "")) for x in l_goc) and len(l_goc) != len(l_en):
        lech.append(f"{cid}.setup.links {len(l_goc)}!={len(l_en)}")
check("mọi chữ hiển thị tiếng Việt của catalog đều có bản tiếng Anh", not thieu, ", ".join(thieu[:6]))
check("số bước wizard và link cài đặt khớp bản gốc (khớp theo vị trí)", not lech, ", ".join(lech[:6]))
check("bản tiếng Anh không lẫn chữ Việt", not DAU_VIET.search(raw_en), DAU_VIET.findall(raw_en)[:5])
check("bản tiếng Anh không dùng em dash / en dash", "—" not in raw_en and "–" not in raw_en)

# Chạy thật: đúng chỗ dashboard gọi.
pub_vi = {c["id"]: c for c in mcp_catalog.public_catalog()}
tok = localefmt.dat_ngon_ngu_yeu_cau("en")
pub_en = {c["id"]: c for c in mcp_catalog.public_catalog()}
localefmt.bo_ngon_ngu_yeu_cau(tok)
pub_vi2 = {c["id"]: c for c in mcp_catalog.public_catalog()}

if "botcake" in pub_en:
    check("tiếng Anh: mô tả Botcake ra bản tiếng Anh", pub_en["botcake"]["description"].startswith("Customers, tags"))
    check("tiếng Anh: nhãn ô nhập cũng dịch",
          any(f["label"] == "The page's API key" for f in pub_en["botcake"]["fields"]))
    check("tiếng Việt: vẫn là bản gốc", pub_vi["botcake"]["description"] == goc["botcake"]["description"])
if "gmail" in pub_en:
    check("tiếng Anh: nhãn link cài đặt dịch", pub_en["gmail"]["setup"]["links"][0]["label"] == "Enrol in Developer Preview")
    check("phủ bản dịch KHÔNG làm bẩn catalog gốc đang cache (gọi lại tiếng Việt vẫn ra tiếng Việt)",
          pub_vi2["gmail"]["setup"]["links"][0]["label"] == goc["gmail"]["auth"]["setup"]["links"][0]["label"])
check("tiếng Anh: không còn chữ Việt trong chữ hiển thị của connector có bản dịch",
      not [cid for cid, c in pub_en.items() if cid in en
           and DAU_VIET.search(json.dumps({k: c.get(k) for k in ("name", "description", "group_line", "guide", "risk", "fields", "steps", "setup")}, ensure_ascii=False))])
# Thứ tiếng ĐÃ đăng ký nhưng chưa có mcp-catalog.<mã>.json: phải dùng bản tiếng Anh, không rơi
# về tiếng Việt. Giả lập bằng cách cho sổ đăng ký nhận "ja" trong lúc thử.
import lang_registry  # noqa: E402
_goc_ch = lang_registry.chuan_hoa
lang_registry.chuan_hoa = lambda m: "ja" if str(m).startswith("ja") else _goc_ch(m)
try:
    check("thứ tiếng chưa có file catalog riêng dùng bản tiếng Anh",
          catalog_i18n.lop_phu("ja") is catalog_i18n._doc_lop_phu("en") and bool(catalog_i18n.lop_phu("ja")))
finally:
    lang_registry.chuan_hoa = _goc_ch
# File của thứ tiếng thứ ba dịch dở: connector nào chưa có trong đó phải lấy bản tiếng Anh,
# không rơi thẳng về tiếng Việt (lỗi người dịch sổ tay tìm ra, 0.68.0).
_goc_doc = catalog_i18n._doc_lop_phu
_goc_ch2 = lang_registry.chuan_hoa
catalog_i18n._doc_lop_phu = lambda m: ({"botcake": {"description": "JA"}} if m == "ja" else _goc_doc(m))
lang_registry.chuan_hoa = lambda m: "ja" if str(m).startswith("ja") else _goc_ch2(m)
try:
    _ja = catalog_i18n.lop_phu("ja")
    check("thứ tiếng thứ ba dịch dở: mục đã dịch dùng bản của nó", _ja["botcake"]["description"] == "JA")
    check("thứ tiếng thứ ba dịch dở: mục chưa dịch dùng bản tiếng Anh", _ja.get("gmail") == en.get("gmail"))
finally:
    catalog_i18n._doc_lop_phu = _goc_doc
    lang_registry.chuan_hoa = _goc_ch2
check("ngôn ngữ gốc của catalog thì không phủ gì", catalog_i18n.lop_phu(lang_registry.MAC_DINH) == {})

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_catalog_ban_dich: tất cả pass")
