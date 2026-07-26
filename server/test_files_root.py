"""Test trần duyệt File Manager (v0.9.38). Chạy tay / CI:

    cd server && python test_files_root.py

KHÔNG mạng. Phủ: localhost mở tới ổ đĩa (out được ra root), public khoá brain,
JAVIS_FILES_ROOT override, _safe_path chặn vượt trần, điểm vào mặc định = brain,
parent=None khi ở trần (ẩn nút Lên).
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-filestest-"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
main._brain_root = lambda brain: str(BRAIN)


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
    console_js = (Path(__file__).resolve().parents[1] / "dashboard" / "console.js").read_text(encoding="utf-8")
    check("UI Tệp tin có ô tìm + nút xoá + hai chế độ",
          'id="fmSearch"' in console_js and 'id="fmSearchClear"' in console_js
          and 'id="fmSearchName"' in console_js and 'id="fmSearchContent"' in console_js)
    check("UI gửi mode thật xuống /files/search",
          "/files/search?brain=${encodeURIComponent(fbrain())}" in console_js
          and "&mode=${searchMode}" in console_js)

    # ---- 6. Xoá: chặn xoá brain root lẫn trần ----
    async def _del(path_arg):
        return await main.files_delete(brain="brain", path=path_arg)

    r = asyncio.run(_del(main._files_rel(_ANCHOR, BRAIN)))
    check("không xoá được brain root", hasattr(r, "status_code") and r.status_code == 400)
finally:
    main._brain_root = _orig_brain_root
    _set_env()

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_files_root: tất cả pass")
