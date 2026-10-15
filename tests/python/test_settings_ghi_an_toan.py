"""settings.json không bao giờ mất tên miền, đăng nhập, khoá API vì một lần ghi một phần (0.86.2).

    python tests/run.py settings_ghi_an_toan      (KHÔNG mạng, thư mục state tạm)

Báo lỗi của khách 08/10/2026 (chạy Docker trên VPS): sau một lần dựng lại Caddy, HTTPS chết vì
`domain.custom` trong settings.json đã rỗng. Họ rà mã và chỉ ra đúng chỗ: `write_settings()` THAY
CẢ FILE bằng thứ được đưa vào, mà từ 0.71.0 có ba chỗ đưa vào một MẢNH:

  - GET /whatsapp/status (tab WhatsApp ở trang Kênh Admin): lần đầu sinh verify_token rồi ghi
    `{"whatsapp": {"verify_token": ...}}`, tức chỉ MỞ TRANG là mất sạch cấu hình;
  - cho phép một chat Zalo: `{"zalo_bot": {"chat_id": ...}}`;
  - cho phép một người dùng Slack/WhatsApp/Discord/Lark: `{"<kênh>": {"allow": ...}}`.

Thêm ba rủi ro họ nêu, cũng có thật: đọc file hỏng thì trả mặc định rồi lần ghi sau đè mặc định
lên; ghi không nguyên tử; không khoá đọc-sửa-ghi.

Điều được ghim:
  1. Ba đường ghi một phần kia giữ nguyên mọi trường khác (gọi endpoint thật).
  2. `update_settings` gộp đệ quy, giữ trường anh em.
  3. Lưới an toàn: `write_settings` nhận một mảnh (thiếu khoá gốc) thì gộp chứ không ghi đè.
  4. Ghi cả cấu hình đầy đủ vẫn XOÁ được có chủ đích (không biến mọi lần ghi thành gộp).
  5. File hỏng: giữ bản hỏng `.bad-*`, đọc bản dự phòng `.bak`, lần ghi sau không làm mất tên miền.
  6. Ghi nguyên tử: lỗi giữa chừng để nguyên file cũ, không sót file tạm.
  7. Nhiều luồng cùng cập nhật: không thay đổi nào bị đè mất.
  8. Đọc hỏng thoáng qua (file bị khoá) không thành "máy mới cài", và cấu hình trống không bao
     giờ ghi đè được máy đã cài đặt (0.166.4, lỗi lưu kênh Lark).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import threading

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-settings-safe-")
import config as cfgmod  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


def seed():
    """Một máy đang chạy thật: có tên miền, khoá API, Telegram, một kênh Slack đã đấu."""
    for p in cfgmod.SETTINGS_PATH.parent.glob(cfgmod.SETTINGS_PATH.name + "*"):
        p.unlink()
    c = cfgmod.read_settings()
    c["domain"]["custom"] = "javis.example.com"
    c["workspace_name"] = "Cửa hàng A"
    c.setdefault("model", {})["openrouter_api_key"] = "sk-or-test-1234"
    c["telegram"]["chat_id"] = "111"
    c["slack"]["allow"] = "U1"
    cfgmod.write_settings(c)


def con_nguyen(c, tru=()):
    hong = []
    if c["domain"].get("custom") != "javis.example.com":
        hong.append("domain.custom")
    if c.get("workspace_name") != "Cửa hàng A":
        hong.append("workspace_name")
    if (c.get("model") or {}).get("openrouter_api_key") != "sk-or-test-1234":
        hong.append("model.openrouter_api_key")
    if "telegram" not in tru and c["telegram"].get("chat_id") != "111":
        hong.append("telegram.chat_id")
    return hong


# ---- 1. Ba đường ghi một phần, gọi qua endpoint thật ----
import main  # noqa: E402
import owner_channels  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://localhost")

seed()
r = client.get("/whatsapp/status")
c = cfgmod.read_settings()
check("GET /whatsapp/status sinh verify_token mà giữ nguyên mọi trường khác",
      r.status_code == 200 and not con_nguyen(c) and bool(c["whatsapp"].get("verify_token")), con_nguyen(c))

seed()
r = client.post("/zalo-bot/allow", data={"chat_id": "zalo-99", "on": "1"})
c = cfgmod.read_settings()
check("cho phép chat Zalo giữ nguyên mọi trường khác",
      not con_nguyen(c) and "zalo-99" in str(c["zalo_bot"].get("chat_id")), (r.status_code, con_nguyen(c)))

seed()
owner_channels.SLACK.allow("U2", True)
c = cfgmod.read_settings()
check("cho phép người dùng Slack giữ nguyên mọi trường khác (cả danh sách cũ)",
      not con_nguyen(c) and c["slack"].get("allow") == "U1, U2", (con_nguyen(c), c["slack"].get("allow")))

# ---- 2. update_settings gộp đệ quy ----
seed()
cfgmod.update_settings({"domain": {"email": "a@b.c"}})
c = cfgmod.read_settings()
check("update_settings giữ trường anh em", not con_nguyen(c) and c["domain"].get("email") == "a@b.c")

# ---- 3. Lưới an toàn: mảnh đưa nhầm vào write_settings ----
seed()
cfgmod.write_settings({"whatsapp": {"verify_token": "x"}})
c = cfgmod.read_settings()
check("write_settings nhận một mảnh thì gộp, không xoá sạch file",
      not con_nguyen(c) and c["whatsapp"].get("verify_token") == "x", con_nguyen(c))

# ---- 4. Xoá có chủ đích bằng cấu hình đầy đủ vẫn được ----
seed()
c = cfgmod.read_settings()
c["domain"]["custom"] = ""
c["telegram"]["chat_id"] = ""
cfgmod.write_settings(c)
c = cfgmod.read_settings()
check("ghi cấu hình đầy đủ vẫn xoá được trường có chủ đích",
      c["domain"].get("custom") == "" and c["telegram"].get("chat_id") == "")

seed()
c = cfgmod.read_settings()
c.pop("telegram")
cfgmod.write_settings(c)
c = cfgmod.read_settings()
check("bỏ hẳn một mục gốc có chủ đích (như đặt lại tài khoản) vẫn được",
      c["telegram"].get("chat_id") != "111" and not con_nguyen(c, tru=("telegram",)), c["telegram"].get("chat_id"))

# ---- 5. File hỏng: không rơi về mặc định rồi đè lên ----
seed()
cfgmod.update_settings({"workspace_name": "Cửa hàng A"})   # tạo .bak là bản tốt
raw_tot = cfgmod.SETTINGS_PATH.read_text(encoding="utf-8")
cfgmod.SETTINGS_PATH.write_text(raw_tot[: len(raw_tot) // 2], encoding="utf-8")   # JSON cụt
c = cfgmod.read_settings()
check("file hỏng: đọc bản dự phòng .bak, tên miền còn", not con_nguyen(c), con_nguyen(c))
bad = list(cfgmod.SETTINGS_PATH.parent.glob(cfgmod.SETTINGS_PATH.name + ".bad-*"))
check("file hỏng: giữ lại bản hỏng để cứu tay", len(bad) == 1)
cfgmod.update_settings({"locale": {"ui_lang": "vi"}})
c = cfgmod.read_settings()
check("file hỏng: lần ghi sau không làm mất tên miền", not con_nguyen(c), con_nguyen(c))

# ---- 6. Ghi nguyên tử ----
seed()
truoc = cfgmod.SETTINGS_PATH.read_bytes()
goc = os.replace


def _hong(*a, **k):
    raise OSError("giả lập mất điện giữa lúc thay file")


os.replace = _hong
try:
    try:
        cfgmod.update_settings({"domain": {"custom": "khac.example.com"}})
    except OSError:
        pass
finally:
    os.replace = goc
check("ghi lỗi giữa chừng: file cũ còn nguyên vẹn", cfgmod.SETTINGS_PATH.read_bytes() == truoc)
check("ghi lỗi giữa chừng: không sót file tạm",
      not list(cfgmod.SETTINGS_PATH.parent.glob(".settings.json.*.tmp")))

# ---- 7. Nhiều luồng cùng cập nhật ----
seed()
N = 16


def _them(i):
    cfgmod.update_settings({"dashboard": {f"k{i}": i}})


ts = [threading.Thread(target=_them, args=(i,)) for i in range(N)]
for t in ts:
    t.start()
for t in ts:
    t.join()
c = cfgmod.read_settings()
check("nhiều luồng cùng cập nhật: không thay đổi nào bị đè mất",
      all(c["dashboard"].get(f"k{i}") == i for i in range(N)) and not con_nguyen(c),
      [i for i in range(N) if c["dashboard"].get(f"k{i}") != i])


# ---- 8. Đọc hỏng THOÁNG QUA không được biến thành "máy mới cài" (0.166.4) ----
# Chủ repo 15/10/2026: lưu kênh Lark ở trang Kênh admin xong thì mất sạch tài khoản, model, kênh admin
# và trình cài đặt hiện lại. Đường dẫn tới đó: settings.json bị khoá trong tích tắc (diệt virus,
# os.replace trên Windows) -> đọc lỗi -> .bak cũng lỗi -> trả {} = mặc định = máy mới cài, bộ nhớ đệm
# giữ luôn bản trống đó, và lần lưu kế tiếp ghi nó xuống đĩa.
from pathlib import Path  # noqa: E402

seed()
c = cfgmod.read_settings()
c["setup_done"] = True
c["auth"] = {"username": "admin", "password_hash": "h", "salt": "s"}
cfgmod.write_settings(c)
cfgmod.write_settings(cfgmod.read_settings())      # có .bak tốt
_goc_read_text = Path.read_text
_khoa = {"n": 0}


def _read_text_bi_khoa(self, *a, **k):
    if self.name.startswith(cfgmod.SETTINGS_PATH.name) and _khoa["n"] > 0:
        _khoa["n"] -= 1
        raise PermissionError(13, "file đang bị khoá")
    return _goc_read_text(self, *a, **k)


Path.read_text = _read_text_bi_khoa
try:
    cfgmod._SETTINGS_CACHE["sig"] = None
    _khoa["n"] = 3                                # khoá vài chục mili giây rồi nhả
    c = cfgmod.read_settings()
    check("khoá thoáng qua: đọc lại được bản thật, không ra máy mới",
          c.get("setup_done") is True and c["auth"].get("password_hash") == "h" and not con_nguyen(c))

    cfgmod._SETTINGS_CACHE["sig"] = None
    _khoa["n"] = 10 ** 6                          # khoá mãi, cả .bak
    try:
        cfgmod.read_settings()
        ra = "không ném"
    except cfgmod.SettingsUnreadable:
        ra = "ném"
    check("khoá mãi cả file lẫn .bak: ném SettingsUnreadable, KHÔNG trả cấu hình mặc định", ra == "ném", ra)
    _khoa["n"] = 0
    c = cfgmod.read_settings()
    check("nhả khoá xong đọc lại bản thật (không giữ bản lỗi trong bộ nhớ đệm)",
          c.get("setup_done") is True and not con_nguyen(c))
finally:
    Path.read_text = _goc_read_text

# Lưới cuối: dù cấu hình trống đến từ đâu, không ghi nó đè lên máy đã cài đặt.
trong = json.loads(json.dumps(cfgmod._DEFAULT))
trong["lark"] = {"enabled": True, "app_id": "cli_x", "app_secret": "s", "domain": "lark", "allow": ""}
try:
    cfgmod.write_settings(trong)
    ra = "đã ghi"
except cfgmod.SettingsUnreadable:
    ra = "chặn"
c = cfgmod.read_settings()
check("CANARY: cấu hình 'máy mới cài' KHÔNG ghi đè được máy đã cài đặt", ra == "chặn", ra)
check("chặn xong tài khoản, model, kênh vẫn nguyên",
      c.get("setup_done") is True and c["auth"].get("password_hash") == "h" and not con_nguyen(c))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
