"""Trang Tệp tin chỉ được soi "file .md hỏng bản cũ" MỘT LẦN cho mỗi brain.

    python tests/run.py vault_soi_md_mot_lan

Chủ repo báo 01/09/2026: *"tìm kiếm trên cây thư mục ở phần javis load rất lâu và chậm"*.

Thủ phạm không nằm ở ô tìm kiếm. Mỗi lần mở trang Tệp tin, dashboard gọi `/files/md-hong`, mà
vòng đó ĐỌC TOÀN BỘ file .md của brain rồi chạy regex trên từng file. Brain vài nghìn note là
vài chục MB đọc lại từ đầu, mỗi lần mở trang - tranh cả đĩa lẫn thread với chính cái tìm kiếm
người dùng vừa gõ.

Mà vòng đó là một cuộc DI TRÚ MỘT LẦN: nó đi tìm vết hỏng do bản <= 0.33.3 để lại, và bản đó
không còn tồn tại. Brain đã sạch một lần thì không thể tự bẩn lại, nên soi lại là công vô ích
vĩnh viễn.

Test khoá ba điều: soi sạch rồi thì thôi hẳn, còn bẩn thì vẫn soi lại (người dùng chưa chữa),
và `force=1` luôn soi lại (chép vault cũ từ máy khác vào).
"""
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-mdhong-"))

from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio  # noqa: E402
import pathlib  # noqa: E402
import sys  # noqa: E402

import main  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


brain = tempfile.mkdtemp(prefix="javis-brain-")
pathlib.Path(brain, "ghi-chu.md").write_text("# lành\n", encoding="utf-8")

_dem = {"n": 0}
_ket_qua = {"items": []}
_that = main._quet_md_hong


def _quet_dem(brain_arg, chi_path=None):
    _dem["n"] += 1
    return list(_ket_qua["items"])


main._quet_md_hong = _quet_dem
try:
    # --- Lần đầu: phải soi thật ---
    d1 = asyncio.run(main.files_md_hong(brain=brain))
    check("lần mở đầu tiên: có soi", _dem["n"] == 1, _dem["n"])
    check("brain sạch → không mời chữa gì", d1.get("items") == [], d1)

    # --- Lần sau: KHÔNG được đụng vào đĩa nữa ---
    d2 = asyncio.run(main.files_md_hong(brain=brain))
    check("lần mở thứ hai: KHÔNG soi lại (đây là cả cái sửa)", _dem["n"] == 1, _dem["n"])
    check("và nói rõ vì sao bỏ qua", d2.get("bo_qua") == "da-soi-sach", d2)
    for _ in range(5):
        asyncio.run(main.files_md_hong(brain=brain))
    check("mở thêm 5 lần nữa vẫn không soi lại", _dem["n"] == 1, _dem["n"])

    # --- force=1 vẫn soi lại được ---
    asyncio.run(main.files_md_hong(brain=brain, force="1"))
    check("force=1 thì soi lại", _dem["n"] == 2, _dem["n"])

    # --- Brain CÒN file hỏng: phải soi lại mỗi lần, vì người dùng chưa chữa ---
    brain2 = tempfile.mkdtemp(prefix="javis-brain-hong-")
    pathlib.Path(brain2, "hong.md").write_text("* * *\n", encoding="utf-8")
    _ket_qua["items"] = [{"path": "hong.md", "name": "hong.md", "van_de": ["fm"], "mo_ta": "x"}]
    truoc = _dem["n"]
    e1 = asyncio.run(main.files_md_hong(brain=brain2))
    e2 = asyncio.run(main.files_md_hong(brain=brain2))
    check("brain còn file hỏng thì VẪN soi lại lần sau", _dem["n"] == truoc + 2, _dem["n"])
    check("và vẫn mời chữa như cũ", len(e1.get("items") or []) == 1 and len(e2.get("items") or []) == 1)

    # --- Dấu ghi theo TỪNG brain, không lẫn sang nhau ---
    check("dấu 'đã soi sạch' ghi riêng cho brain sạch",
          main._md_hong_da_sach(str(pathlib.Path(brain).resolve())) is True)
    check("brain còn hỏng thì không mang dấu sạch",
          main._md_hong_da_sach(str(pathlib.Path(brain2).resolve())) is False)
finally:
    main._quet_md_hong = _that

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails[:4]))
    sys.exit(1)
print("Tất cả xanh.")
