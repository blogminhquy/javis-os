"""Test trần duyệt File Manager (v0.9.38). Chạy tay / CI:

    python tests/run.py files_root

KHÔNG mạng. Phủ: localhost mở tới ổ đĩa (out được ra root), public khoá brain,
JAVIS_FILES_ROOT override, _safe_path chặn vượt trần, điểm vào mặc định = brain,
parent=None khi ở trần (ẩn nút Lên).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-filestest-"))

import main            # noqa: E402
import config as cfgmod  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# Brain giả sâu vài cấp để có chỗ "Lên"
_TMP = Path(tempfile.mkdtemp(prefix="javis-brainroot-")).resolve()
BRAIN = _TMP / "brains" / "My Vault"
(BRAIN / "01 - Daily").mkdir(parents=True)
(BRAIN / "note.md").write_text("hi", encoding="utf-8")
(BRAIN / "Kế Hoạch Quý.md").write_text(
    "Mở đầu\nDoanh thu mục tiêu 500 triệu trong quý này.\nKết thúc",
    encoding="utf-8",
)
(_TMP / "ngoai-vault.txt").write_text("data ngoài brain", encoding="utf-8")  # data user cần đọc
_ANCHOR = Path(BRAIN.anchor)

_orig_brain_root = main._brain_root
_orig_brains_dir = main.BRAINS_DIR
main._brain_root = lambda brain: str(BRAIN)
main.BRAINS_DIR = str(_TMP / "brains")


def _set_env(host=None, files_root=None):
    for k, v in (("JAVIS_HOST", host), ("JAVIS_FILES_ROOT", files_root)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    os.environ.pop("JAVIS_REQUIRE_LOGIN", None)


try:
    # ---- 1. Localhost (mặc định): trần = ổ đĩa, out được ra root ----
    _set_env(host="127.0.0.1")
    check("localhost: require_login False", cfgmod.require_login() is False)
    check("localhost: trần = ổ đĩa chứa brain", main._files_ceiling("brain") == _ANCHOR)
    rel_ngoai = main._files_rel(_ANCHOR, _TMP / "ngoai-vault.txt")   # tương đối so với TRẦN (ổ đĩa)
    p = main._safe_path("brain", rel_ngoai)
    check("localhost: đọc được file NGOÀI brain (trong ổ đĩa)", p == _TMP / "ngoai-vault.txt")

    # ---- 2. Public bind: khoá trong brain (fail-closed) ----
    _set_env(host="0.0.0.0")
    check("public: require_login True", cfgmod.require_login() is True)
    check("public: trần = brain", main._files_ceiling("brain") == BRAIN)
    try:
        main._safe_path("brain", "../ngoai-vault.txt")
        check("public: chặn ../ ra ngoài brain", False)
    except ValueError:
        check("public: chặn ../ ra ngoài brain", True)

    # ---- 3. JAVIS_FILES_ROOT override ----
    _set_env(host="0.0.0.0", files_root="drive")   # public NHƯNG ép mở ổ đĩa
    check("env=drive: trần = ổ đĩa dù public", main._files_ceiling("brain") == _ANCHOR)
    _set_env(host="127.0.0.1", files_root="brain")  # localhost NHƯNG ép khoá brain
    check("env=brain: khoá brain dù localhost", main._files_ceiling("brain") == BRAIN)
    _set_env(host="127.0.0.1", files_root=str(_TMP))  # đường dẫn cụ thể chứa brain
    check("env=path cụ thể: trần = path đó", main._files_ceiling("brain") == _TMP)
    _set_env(host="127.0.0.1", files_root=str(_TMP / "khong-ton-tai"))  # path sai → fallback
    check("env=path sai: fallback về brain", main._files_ceiling("brain") == BRAIN)

    # ---- 4. files_list: điểm vào mặc định = brain, parent/home đúng ----
    _set_env(host="127.0.0.1")   # trần = ổ đĩa

    async def _list(path_arg):
        return await main.files_list(brain="brain", path=path_arg)

    d0 = asyncio.run(_list(None))   # None = mặc định
    check("list(None) = BRAIN (không phải ổ đĩa)", d0["path"] == main._files_rel(_ANCHOR, BRAIN)
          and any(i["name"] == "note.md" for i in d0["items"]))
    check("list: home trỏ brain", d0["home"] == main._files_rel(_ANCHOR, BRAIN))
    check("list: parent brain = thư mục cha (Lên được)", d0["parent"] == main._files_rel(_ANCHOR, BRAIN.parent))

    d_up = asyncio.run(_list(d0["parent"]))   # Lên 1 cấp
    check("list: lên 1 cấp thấy folder brain", any(i["name"] == "My Vault" for i in d_up["items"]))

    d_ceil = asyncio.run(_list(""))   # "" = trần (ổ đĩa)
    check("list(''): ở trần → parent=None (ẩn nút Lên)", d_ceil["parent"] is None)

    # ---- 5. Tìm file: tách rõ chế độ tên / nội dung, vẫn hỗ trợ tiếng Việt không dấu ----
    async def _search(q, mode):
        return await main.files_search(brain="brain", q=q, limit=50, mode=mode)

    by_name = asyncio.run(_search("ke hoach quy", "name"))
    check("search name: gõ không dấu vẫn tìm đúng tên có dấu",
          len(by_name["items"]) == 1 and by_name["items"][0]["name"] == "Kế Hoạch Quý.md"
          and by_name["items"][0]["match"] == "name")

    by_content = asyncio.run(_search("500 triệu", "content"))
    check("search content: tìm đúng nội dung + số dòng",
          len(by_content["items"]) == 1 and by_content["items"][0]["match"] == "content"
          and by_content["items"][0]["line"] == 2 and "500 triệu" in by_content["items"][0]["snippet"])

    content_does_not_match_name = asyncio.run(_search("ke hoach quy", "content"))
    check("search content: không lấy kết quả chỉ khớp tên", content_does_not_match_name["items"] == [])

    name_does_not_match_content = asyncio.run(_search("500 triệu", "name"))
    check("search name: không quét nội dung", name_does_not_match_content["items"] == [])

    # Hợp đồng UI: trang Tệp tin có cùng search box/chip như Vault Explorer và gửi đúng mode.
    console_js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
    check("UI Tệp tin có ô tìm + nút xoá + hai chế độ",
          'id="fmSearch"' in console_js and 'id="fmSearchClear"' in console_js
          and 'id="fmSearchName"' in console_js and 'id="fmSearchContent"' in console_js)
    check("UI gửi mode thật xuống /files/search",
          "/files/search?brain=${encodeURIComponent(fbrain())}" in console_js
          and "&mode=${searchMode}" in console_js)
    # Chữ trên nút đã vào từ điển i18n ở 0.55.14: console.js gọi khoá, câu tiếng Việt nằm
    # trong vi.json. Kiểm CẢ HAI vế (giao diện gọi đúng khoá + khoá mang đúng câu) để gỡ nút
    # khỏi giao diện hay đổi nội dung khoá đều làm test đỏ.
    VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
    check("UI Tệp tin có nút Tải về ở danh sách thường và kết quả tìm kiếm",
          console_js.count('data-act="dl"') >= 2
          and console_js.count('title="${window.t("cs.fm_dl_title")}"') >= 2
          and VI.get("cs.fm_dl_title") == "Tải file về máy")
    check("UI cây file Javis có nút tải cạnh file và trong editor",
          'data-a="dl"' in console_js and '"cs.fm_dl_title"' in console_js
          and 'mk("⤓ " + esc(window.t("cs.fm_dl")), window.t("cs.fm_dl_title")' in console_js
          and VI.get("cs.fm_dl") == "Tải" and VI.get("cs.fm_dl_title") == "Tải file về máy")
    check("UI có nút tải CẢ thư mục (nén .zip): danh sách, thanh công cụ, cây file",
          'data-act="zip"' in console_js and 'id="fmZipCur"' in console_js
          and console_js.count("_dlFolder(rel, it.name)") >= 2)
    check("UI tải bằng thẻ <a download> (không dính chặn popup)",
          "function _dlGo(" in console_js and "window.open(rawUrl(rel, 1)" not in console_js)

    # ---- 6. Tải CẢ thư mục về dạng .zip (/files/zip) ----
    import zipfile as _zipfile

    (BRAIN / "01 - Daily" / "2026-07-30.md").write_text("nhật ký hôm nay", encoding="utf-8")
    (BRAIN / "attachments").mkdir(exist_ok=True)
    (BRAIN / "attachments" / "anh.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    brain_rel = main._files_rel(_ANCHOR, BRAIN)

    probe = asyncio.run(main.files_zip(brain="brain", path=brain_rel, probe=1))
    check("zip probe: đếm đủ file (kể cả trong thư mục con)",
          isinstance(probe, dict) and probe.get("files") == 4 and probe.get("bytes", 0) > 0
          and probe.get("name") == "My Vault.zip")

    zip_resp = asyncio.run(main.files_zip(brain="brain", path=brain_rel, probe=0))
    check("zip: trả file .zip đặt theo tên thư mục", getattr(zip_resp, "filename", "") == "My Vault.zip")
    with _zipfile.ZipFile(zip_resp.path) as _z:
        names = _z.namelist()
        bad = _z.testzip()
    check("zip: gói MỌI loại file, không riêng .md",
          bad is None and "My Vault/note.md" in names
          and "My Vault/attachments/anh.png" in names
          and "My Vault/01 - Daily/2026-07-30.md" in names)
    check("zip: giữ nguyên cây thư mục", "My Vault/attachments/" in names)

    dl_dir = asyncio.run(main.files_download(brain="brain", path=brain_rel))
    check("download trỏ vào thư mục → tự nén .zip (không 404 nữa)",
          getattr(dl_dir, "filename", "") == "My Vault.zip")

    _old_max = main._ZIP_MAX_FILES
    main._ZIP_MAX_FILES = 1          # ép vượt trần để kiểm chứng đường dừng sớm
    try:
        too_big = asyncio.run(main.files_zip(brain="brain", path=brain_rel, probe=1))
        check("zip: vượt trần an toàn → 413 chứ không nén nửa vời",
              hasattr(too_big, "status_code") and too_big.status_code == 413)
    finally:
        main._ZIP_MAX_FILES = _old_max

    not_dir = asyncio.run(main.files_zip(brain="brain", path=brain_rel + "/note.md", probe=0))
    check("zip: trỏ vào file lẻ → 404 'Không phải thư mục'",
          hasattr(not_dir, "status_code") and not_dir.status_code == 404)

    # ---- 7. Link export cũ /brains/<tên>/<path> vẫn mở được ----
    (BRAIN / "exports").mkdir(exist_ok=True)
    (BRAIN / "exports" / "bao-cao.html").write_text("<h1>OK</h1>", encoding="utf-8")
    compat = asyncio.run(main.brain_file_compat(
        brain_name="My Vault", path="exports/bao-cao.html", dl=0))
    check("link export cũ /brains/<brain>/... ánh xạ đúng file",
          Path(getattr(compat, "path", "")).resolve() == BRAIN / "exports" / "bao-cao.html")
    missing_brain = asyncio.run(main.brain_file_compat(
        brain_name="Brain Không Có", path="exports/bao-cao.html", dl=0))
    check("link /brains không được rơi nhầm sang brain mặc định",
          hasattr(missing_brain, "status_code") and missing_brain.status_code == 404)

    for _tmp_resp in (zip_resp, dl_dir):
        try:
            os.unlink(_tmp_resp.path)
        except OSError:
            pass

    # ---- 8. Xoá: chặn xoá brain root lẫn trần ----
    async def _del(path_arg):
        return await main.files_delete(brain="brain", path=path_arg)

    r = asyncio.run(_del(main._files_rel(_ANCHOR, BRAIN)))
    check("không xoá được brain root", hasattr(r, "status_code") and r.status_code == 400)
finally:
    main._brain_root = _orig_brain_root
    main.BRAINS_DIR = _orig_brains_dir
    _set_env()

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_files_root: tất cả pass")
