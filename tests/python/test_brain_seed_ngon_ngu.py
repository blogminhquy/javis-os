"""File hạt giống của brain theo ngôn ngữ người dùng (0.67.0).

    python tests/run.py brain_seed_ngon_ngu

Brain mặc định được tạo lúc server khởi động, trước khi biết người dùng đọc tiếng gì, nên nó
ra tiếng Việt; khi người dùng chốt ngôn ngữ giao diện, các file hạt giống CÒN NGUYÊN được viết
lại sang ngôn ngữ đó. Cách nhận "còn nguyên" là so từng ký tự với bản hạt giống, nên chỗ dễ hỏng
nhất là bản tiếng Việt trong brain_seed_i18n.py lệch khỏi hằng số gốc ở main.py / meta_tools.py:
lệch một ký tự là không file nào được nhận ra nữa, và chuyện đó xảy ra trong im lặng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-seed-"))
import brain_seed_i18n as bs  # noqa: E402
import localefmt  # noqa: E402
import meta_tools  # noqa: E402

_fails = []
DAU_VIET = re.compile("[ăđơưảãạằắẳẵặầấẩẫậẻẽẹềếểễệỉĩịỏõọồốổỗộờớởỡợủũụừứửữựỳỷỹỵ]", re.I)


def check(ten, ok, chi_tiet=""):
    print(f"{'ok  ' if ok else 'FAIL'} {ten}" + ("" if ok else f"  [{chi_tiet}]"))
    if not ok:
        _fails.append(ten)


# Đọc hằng số gốc thẳng từ mã nguồn main.py (nạp cả main chỉ để lấy ba chuỗi là quá nặng).
_src = (SERVER / "main.py").read_text(encoding="utf-8")


def _hang_so(ten):
    m = re.search(rf"^{ten} = \(\n(.*?)\n\)", _src, re.S | re.M)
    return eval("(" + m.group(1) + ")") if m else None  # noqa: S307 - chuỗi ghép từ mã của chính repo


for ten, goc in (("dashboard", _hang_so("DASHBOARD_SEED")), ("memory", _hang_so("MEMORY_SEED")),
                 ("javis_readme", _hang_so("JAVIS_README")),
                 ("wiki_index", meta_tools._WIKI_INDEX), ("wiki_log", meta_tools._WIKI_LOG),
                 ("open_questions", meta_tools._OPEN_QUESTIONS), ("session_handoff", meta_tools._SESSION_HANDOFF)):
    check(f"bản tiếng Việt của '{ten}' giống từng ký tự hằng số gốc", bs.HAT_GIONG[ten]["vi"] == goc)
for ten, b in bs.HAT_GIONG.items():
    check(f"'{ten}': bản tiếng Anh không lẫn chữ Việt", not DAU_VIET.search(b["en"]))
    check(f"'{ten}': không em dash / en dash", "—" not in b["en"] + b["vi"] and "–" not in b["en"] + b["vi"])

check("giữ chỗ bộ nhớ: nhận bản tiếng Việt", bs.GIU_CHO_BO_NHO.search(bs.HAT_GIONG["memory"]["vi"]))
check("giữ chỗ bộ nhớ: nhận bản tiếng Anh", bs.GIU_CHO_BO_NHO.search(bs.HAT_GIONG["memory"]["en"]))

# chon(): theo ngôn ngữ của thiết bị đang gọi.
goc = bs.HAT_GIONG["dashboard"]["vi"]
check("chon(): không cookie -> tiếng Việt như cũ", bs.chon(goc) == goc)
tok = localefmt.dat_ngon_ngu_yeu_cau("en")
check("chon(): cookie en -> tiếng Anh", bs.chon(goc) == bs.HAT_GIONG["dashboard"]["en"])
check("chon(): chuỗi lạ trả nguyên văn", bs.chon("# Ghi chú riêng\n") == "# Ghi chú riêng\n")
localefmt.bo_ngon_ngu_yeu_cau(tok)

# doi_ngon_ngu(): chỉ đổi file còn nguyên.
root = Path(tempfile.mkdtemp(prefix="brain-"))
vt = bs._vi_tri(root)
for ten, p in vt.items():
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(bs.HAT_GIONG[ten]["vi"], encoding="utf-8")
vt["wiki_log"].write_text(bs.HAT_GIONG["wiki_log"]["vi"] + "## [2026-10-02] ingest | Sổ tay\n", encoding="utf-8")
doi = bs.doi_ngon_ngu(root, "en")
check("đổi sang en: mọi file còn nguyên được viết lại", set(doi) == set(bs.HAT_GIONG) - {"wiki_log"}, doi)
check("đổi sang en: Dashboard ra tiếng Anh", vt["dashboard"].read_text(encoding="utf-8") == bs.HAT_GIONG["dashboard"]["en"])
check("file người dùng đã sửa thì KHÔNG đụng", "Sổ tay" in vt["wiki_log"].read_text(encoding="utf-8"))
check("đổi lại sang vi được (người dùng đổi ý)", "dashboard" in bs.doi_ngon_ngu(root, "vi")
      and vt["dashboard"].read_text(encoding="utf-8") == bs.HAT_GIONG["dashboard"]["vi"])
check("đã đúng ngôn ngữ thì không ghi gì", bs.doi_ngon_ngu(root, "vi") == [])
check("mã rác thì không làm gì", bs.doi_ngon_ngu(root, "") == [] and bs.doi_ngon_ngu(root, "xx") == [])

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_brain_seed_ngon_ngu: tất cả pass")
