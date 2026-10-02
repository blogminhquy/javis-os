"""Chữ phía SERVER theo ngôn ngữ giao diện của THIẾT BỊ đang gọi (0.67.0).

    python tests/run.py chu_theo_thiet_bi

`ui_lang` trong settings là chung cả máy, còn ngôn ngữ giao diện là theo từng trình duyệt.
Nên dashboard đặt cookie `javis_lang`, middleware gán nó cho request, và `localefmt.chu()`
chọn bản chữ theo đó. Test này canh ba chỗ dễ hỏng:
  - thứ tiếng thứ ba rơi về tiếng Việt thay vì tiếng Anh;
  - request không có cookie (Telegram, script, test cũ) bị đổi sang tiếng Anh;
  - middleware bị gỡ hoặc đặt sai chỗ nên cookie không tới được endpoint.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-chu-"))
import lang_registry  # noqa: E402
import localefmt  # noqa: E402

_fails = []


def check(ten, ok, chi_tiet=""):
    print(f"{'ok  ' if ok else 'FAIL'} {ten}" + ("" if ok else f"  [{chi_tiet}]"))
    if not ok:
        _fails.append(ten)


BAN = {"vi": "Xin chào", "en": "Hello"}
check("chon_ban_dich: đúng ngôn ngữ", lang_registry.chon_ban_dich("vi", BAN) == "Xin chào")
check("chon_ban_dich: mã đủ (en-US) vẫn nhận", lang_registry.chon_ban_dich("en-US", BAN) == "Hello")
check("chon_ban_dich: thứ tiếng chưa có -> tiếng Anh", lang_registry.chon_ban_dich("ja", BAN) == "Hello")
check("chon_ban_dich: thiếu bản tiếng Anh -> bản còn lại, không rỗng",
      lang_registry.chon_ban_dich("ja", {"vi": "Chỉ có tiếng Việt"}) == "Chỉ có tiếng Việt")

# Không cookie: giữ đúng hành vi cũ (ui_lang của máy, mặc định tiếng Việt). Đây là điều giữ cho
# hàng trăm test cũ đang soi chữ tiếng Việt khỏi đỏ, và cho Telegram khỏi đổi ngôn ngữ.
check("không cookie -> mặc định của máy", localefmt.chu("Đã lưu", "Saved") == "Đã lưu")

tok = localefmt.dat_ngon_ngu_yeu_cau("en")
check("cookie en -> tiếng Anh", localefmt.chu("Đã lưu", "Saved") == "Saved")
check("biến được thay", localefmt.chu("Đã lưu {n} mục", "Saved {n} items", n=3) == "Saved 3 items")
check("chữ có ngoặc nhọn mà không truyền biến thì giữ nguyên",
      localefmt.chu("{a}", "{json}") == "{json}")
check("thiếu biến thì trả chữ thô, không ném lỗi", localefmt.chu("{n} mục", "{n} items") == "{n} items")
localefmt.bo_ngon_ngu_yeu_cau(tok)
check("gỡ cookie xong quay về mặc định", localefmt.chu("Đã lưu", "Saved") == "Đã lưu")

tok = localefmt.dat_ngon_ngu_yeu_cau("rác")
check("cookie rác -> coi như không có", localefmt.ngon_ngu_giao_dien() == lang_registry.MAC_DINH)
localefmt.bo_ngon_ngu_yeu_cau(tok)

# Đi qua app THẬT: cookie phải tới được endpoint qua cả chồng middleware.
try:
    from fastapi.testclient import TestClient
    import main
    hits = [r for r in main.app.routes if getattr(r, "path", "") == "/__test_chu"]
    if not hits:
        @main.app.get("/__test_chu")
        def _test_chu():
            return {"chu": localefmt.chu("Xin chào", "Hello")}
    c = TestClient(main.app, base_url="http://localhost")
    check("app: không cookie -> tiếng Việt", c.get("/__test_chu").json().get("chu") == "Xin chào")
    c.cookies.set("javis_lang", "en")
    check("app: cookie javis_lang=en -> tiếng Anh", c.get("/__test_chu").json().get("chu") == "Hello")
    c.cookies.set("javis_lang", "vi")
    check("app: cookie javis_lang=vi -> tiếng Việt", c.get("/__test_chu").json().get("chu") == "Xin chào")
except Exception as e:  # noqa: BLE001
    check("app: nạp được main để thử middleware", False, f"{type(e).__name__}: {e}")

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_chu_theo_thiet_bi: tất cả pass")
