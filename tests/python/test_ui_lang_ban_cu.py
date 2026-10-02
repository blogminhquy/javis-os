"""Ngôn ngữ giao diện khi lên 0.66.0: máy mới theo trình duyệt, máy cũ giữ tiếng Việt.

    python tests/run.py ui_lang_ban_cu

Từ 0.66.0 `locale.ui_lang` mặc định là "" (chưa chọn), để dashboard đoán theo trình duyệt rồi
ghi lại. Cái giá phải canh: máy cài TRƯỚC khi có khối locale có settings.json không chứa khoá
này. Đọc ra "" là người dùng Việt có trình duyệt để tiếng Anh bị đổi giao diện trong im lặng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="javis-uilang-"))
os.environ["JAVIS_STATE_DIR"] = str(_tmp)
import config as cfgmod  # noqa: E402

cfgmod.SETTINGS_PATH = _tmp / "settings.json"
_fails = []


def check(ten, ok):
    print(f"{'ok  ' if ok else 'FAIL'} {ten}")
    if not ok:
        _fails.append(ten)


def doc(noi_dung):
    p = cfgmod.SETTINGS_PATH
    if noi_dung is None:
        p.unlink(missing_ok=True)
    else:
        p.write_text(json.dumps(noi_dung), encoding="utf-8")
    cfgmod._SETTINGS_CACHE["sig"] = None
    return (cfgmod.read_settings().get("locale") or {}).get("ui_lang")


check("máy mới tinh (chưa có settings.json) -> rỗng, để dashboard đoán", doc(None) == "")
check("máy cũ có settings.json nhưng chưa từng có khối locale -> vi",
      doc({"workspace_name": "Shop", "setup_done": True}) == "vi")
check("máy cũ có locale mà thiếu ui_lang -> vi", doc({"locale": {"tz": "Asia/Ho_Chi_Minh"}}) == "vi")
check("máy đã lưu en -> giữ en", doc({"locale": {"ui_lang": "en"}}) == "en")
check("máy cài từ 0.66.0 (đã ghi ui_lang rỗng) -> vẫn rỗng, chưa ai chọn",
      doc({"setup_done": True, "locale": {"ui_lang": ""}}) == "")
# Ghi lại qua write_settings không được biến "vi" suy ra thành thứ khác, và máy mới ghi lần
# đầu thì phải giữ được trạng thái "chưa chọn".
doc(None)
cfgmod.write_settings(cfgmod.read_settings())
cfgmod._SETTINGS_CACHE["sig"] = None
check("máy mới ghi settings lần đầu -> ui_lang vẫn rỗng",
      (cfgmod.read_settings().get("locale") or {}).get("ui_lang") == "")

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_ui_lang_ban_cu: tất cả pass")
