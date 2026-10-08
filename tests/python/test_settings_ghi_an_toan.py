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

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
