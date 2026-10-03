"""Nhật ký cập nhật song ngữ: CHANGELOG.md (gốc, tiếng Việt) + CHANGELOG.en.md (0.68.0).

    python tests/run.py nhat_ky_song_ngu

Trang Cập nhật trong app đọc CHANGELOG.md; từ 0.68.0 thiết bị đọc tiếng Anh thấy bản dịch trong
CHANGELOG.en.md cho những phiên bản đã dịch. Hai file sống riêng, nên test này là CHỐT CHẶN:
từ 0.66.0 trở đi, phiên bản nào có trong CHANGELOG.md mà thiếu trong CHANGELOG.en.md là đỏ.
Không có chốt này thì sau vài tuần bản tiếng Anh dừng ở đúng phiên bản cuối cùng có người nhớ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-cl-"))
import localefmt  # noqa: E402
import main  # noqa: E402

_fails = []
DAU_VIET = re.compile("[ăđơưảãạằắẳẵặầấẩẫậẻẽẹềếểễệỉĩịỏõọồốổỗộờớởỡợủũụừứửữựỳỷỹỵ]", re.I)
MOC = (0, 66, 0)   # bản dịch tiếng Anh bắt đầu từ đây


def check(ten, ok, chi_tiet=""):
    print(f"{'ok  ' if ok else 'FAIL'} {ten}" + ("" if ok else f"  [{chi_tiet}]"))
    if not ok:
        _fails.append(ten)


vi_md = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
en_md = (ROOT / "CHANGELOG.en.md").read_text(encoding="utf-8")
vi = {r["version"]: r for r in main._parse_changelog(vi_md)}
en = {r["version"]: r for r in main._parse_changelog(en_md)}
ver = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731

check("CHANGELOG.en.md đọc ra được phiên bản", len(en) >= 3, len(en))
check("bản tiếng Anh không có phiên bản lạ (mọi bản đều có trong CHANGELOG.md)", set(en) <= set(vi), set(en) - set(vi))
thieu = sorted((v for v in vi if ver(v) >= MOC and v not in en), key=ver, reverse=True)
check("CHỐT: mọi phiên bản từ 0.66.0 trong CHANGELOG.md đều có bản tiếng Anh", not thieu,
      "thiếu: " + ", ".join(thieu[:5]) + " - viết thêm khối đó vào CHANGELOG.en.md")
lech = [v for v in en if len(en[v]["sections"]) != len(vi[v]["sections"])
        or not all(s["items"] for s in en[v]["sections"])]
check("mỗi phiên bản dịch có cùng số nhóm thay đổi và không nhóm nào rỗng", not lech, lech[:5])
# "Tiếng Việt" là tên NÚT chuyển ngôn ngữ trên giao diện, giữ nguyên trong bản tiếng Anh.
body_en = (en_md.split("## [", 1)[1] if "## [" in en_md else "").replace("Tiếng Việt", "")
check("phần nội dung tiếng Anh không lẫn chữ Việt", not DAU_VIET.search(body_en), DAU_VIET.findall(body_en)[:5])
check("không em dash / en dash", "—" not in en_md and "–" not in en_md)
check("hai file có dòng chuyển ngôn ngữ trỏ nhau", "(CHANGELOG.en.md)" in vi_md and "(CHANGELOG.md)" in en_md)


# Chạy thật lớp phủ, không đi mạng: bản trên GitHub coi như chưa tải được.
async def _khong_mang(ma, refresh=False):
    return {}
main._cl_dich_remote = _khong_mang
rels = [dict(vi[v]) for v in sorted(vi, key=ver, reverse=True)[:8]]
moi = next(v for v in (r["version"] for r in rels) if v in en)
cu = next((v for v in (r["version"] for r in rels) if v not in en), None)

out = asyncio.run(main._cl_theo_ngon_ngu(rels))
check("không cookie: giữ nguyên tiếng Việt", out == rels)
tok = localefmt.dat_ngon_ngu_yeu_cau("en")
out = {r["version"]: r for r in asyncio.run(main._cl_theo_ngon_ngu(rels))}
localefmt.bo_ngon_ngu_yeu_cau(tok)
check(f"cookie en: {moi} ra bản tiếng Anh", out[moi]["sections"] == en[moi]["sections"] and out[moi].get("lang") == "en")
if cu:
    check(f"cookie en: {cu} chưa dịch thì giữ bản tiếng Việt", out[cu]["sections"] == vi[cu]["sections"])
check("không làm bẩn danh sách gốc (cache) khi phủ bản dịch", rels[0]["sections"] == vi[rels[0]["version"]]["sections"])

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_nhat_ky_song_ngu: tất cả pass")
