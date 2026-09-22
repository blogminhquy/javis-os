"""`env.example` phải MÁY đọc được: chỉ TÊN=giá trị, không một dòng chú thích nào.

    python tests/run.py env_example

Lỗi thật, và đây là lần thứ HAI. Các nền tảng deploy (Docker Manager của Hostinger, bảng
Environment của những chỗ tương tự) tự quét file cấu hình trong repo rồi đổ nguyên nội dung
vào ô Environment. Chúng cắt MỌI dòng có dấu `=` tại dấu `=` đầu tiên và coi vế trái là tên
biến. Dòng chú thích cũng bị cắt như thường, nên:

    # ==========================================   ->  tên biến là "#"
    # JAVIS_HOST=127.0.0.1                         ->  tên biến là "# JAVIS_HOST"
    # Mặc định: bind KHÔNG phải loopback -> tự bật  ->  cắt ở dấu "=" giữa câu

Bản `env.example` trước có 25 dòng chú thích chứa dấu `=`; ba dòng `# ===` trùng tên nên gộp
lại còn một, ra đúng **23 biến đỏ "Tên biến không hợp lệ"** mà chủ repo gặp mỗi lần dựng máy
mới (22/09). Không hỏng gì về chức năng, nhưng nền tảng CHẶN deploy cho tới khi xoá tay hết.

Lần chữa thứ nhất (0.5x, xem CHANGELOG) là ĐỔI TÊN file `.env.example` thành `env.example` để
trình quét bỏ qua. Nó không đủ: vẫn còn đường người dùng tự mở file rồi dán vào ô Environment,
và một trình quét khác có thể bắt cả tên không có dấu chấm đầu. Chữa lần này đi vào nội dung:
**file không còn gì để hiểu sai.**

Phần giải thích từng biến KHÔNG mất đi, nó nằm ở `docs/16-cau-hinh-env.md` (bản tiếng Anh:
`docs/en/16-env-configuration.md`) - một tài liệu 241 dòng có bảng, đầy đủ hơn hẳn khối chú
thích cũ, và là nơi người ta thật sự tra cứu.

Vì sao là phép thử chứ không phải một dòng nhắc trong tài liệu: khối chú thích đó mọc lại rất
tự nhiên. Ai thêm một biến mới đều muốn giải thích nó ngay tại chỗ, và không ai nhớ tới cái ô
Environment của một nền tảng deploy mình không dùng.
"""
from _paths import ROOT  # noqa: E402,F401
import re
import sys

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


_DONG_HOP_LE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

_path = ROOT / "env.example"
check("có file env.example", _path.is_file())
_raw = _path.read_text(encoding="utf-8")
_dong = _raw.splitlines()


# ============================================================
# 1) Luật chính: mọi dòng đều là TÊN=giá trị, hoặc trống
# ============================================================

_xau = [(i + 1, d) for i, d in enumerate(_dong) if d.strip() and not _DONG_HOP_LE.match(d)]
check(f"mọi dòng đều dạng TÊN=giá trị (sai: {_xau[:3]})", not _xau)

_co_thich = [(i + 1, d) for i, d in enumerate(_dong) if d.lstrip().startswith("#")]
check(f"KHÔNG còn dòng chú thích nào (còn: {_co_thich[:3]})", not _co_thich)

check("không có dòng nào bắt đầu bằng khoảng trắng (trình quét cắt sai vế trái)",
      not [d for d in _dong if d != d.lstrip()])


# ============================================================
# 2) Mô phỏng ĐÚNG cách trình quét ngây thơ đọc file
# ============================================================
#
# Đây là phần soi thật: dựng lại thuật toán đã sinh ra 23 biến đỏ, rồi khẳng định nó không
# còn sinh ra tên nào sai. Mô phỏng chứ không chỉ kiểm cú pháp, vì luật ở mục 1 có thể đúng
# mà vẫn ra tên xấu nếu file lỡ có ký tự lạ.

def _quet_ngay_tho(text):
    """Cắt MỌI dòng có dấu `=` tại dấu `=` đầu tiên, trả về danh sách tên biến."""
    ten = []
    for d in text.splitlines():
        if "=" in d:
            ten.append(d.split("=", 1)[0])
    return ten


_TEN_HOP_LE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ten = _quet_ngay_tho(_raw)
_ten_xau = [t for t in _ten if not _TEN_HOP_LE.match(t)]
check(f"trình quét ngây thơ KHÔNG sinh tên biến sai nào (sai: {_ten_xau[:5]})", not _ten_xau)
check("và nó vẫn đọc ra đủ các biến thật", len(_ten) == len([d for d in _dong if d.strip()]))

# Bản CŨ phải làm phép thử này đỏ, nếu không thì phép thử không chứng minh được gì.
_ban_cu = "# ==========================\n# JAVIS_HOST=127.0.0.1\nWORKSPACE_NAME=Javis OS\n"
check("CANARY: mô phỏng bắt được đúng kiểu hỏng của bản cũ",
      [t for t in _quet_ngay_tho(_ban_cu) if not _TEN_HOP_LE.match(t)] == ["# ", "# JAVIS_HOST"])


# ============================================================
# 3) Nội dung: chỉ những biến ĐẶT TƯỜNG MINH cũng vô hại
# ============================================================
#
# Vì sao không liệt kê lại mọi biến trong file mẫu: `install.sh` chép nguyên file này thành
# `.env`, và Docker Compose đọc `.env` để thay ${...}. Một biến nằm trong đó là nó ĐƯỢC ĐẶT
# THẬT, ghi đè giá trị mà Docker tự chọn. Đặt sẵn `JAVIS_HOST=127.0.0.1` là container nghe
# loopback rồi không ai vào được - đúng cảnh mà dòng mẫu đã-comment sinh ra để tránh, và là
# lý do cả khối cũ phải comment. Bỏ chú thích đi thì cách duy nhất còn đúng là KHÔNG liệt kê
# chúng nữa, chỉ giữ những biến mà đặt tường minh cũng ra đúng mặc định.

_bien = dict(d.split("=", 1) for d in _dong if d.strip())
_CAM = ("JAVIS_HOST", "JAVIS_PORT", "JAVIS_STATE_DIR", "BRAINS_DIR", "BRAIN_PATH",
        "OBSIDIAN_VAULT_PATH", "CLAUDE_CWD", "JAVIS_REQUIRE_LOGIN", "JAVIS_SECURE_COOKIE")
for _c in _CAM:
    check(f"KHÔNG đặt sẵn {_c} (đặt tường minh là ghi đè thứ Docker tự chọn)",
          _c not in _bien)

check("không đặt sẵn mật khẩu quản trị nào (install.sh tự sinh rồi ghi vào .env)",
      "JAVIS_ADMIN_PASSWORD" not in _bien)
check("vẫn còn các biến hiển thị cơ bản",
      "WORKSPACE_NAME" in _bien and "USER_NAME" in _bien)
check("vẫn còn cấu hình giọng đọc", "TTS_VOICE" in _bien and "TTS_RATE" in _bien)


# ============================================================
# 4) Phần giải thích phải còn chỗ khác, không được mất
# ============================================================

_doc_vi = ROOT / "docs" / "16-cau-hinh-env.md"
_doc_en = ROOT / "docs" / "en" / "16-env-configuration.md"
check("tài liệu tra cứu biến môi trường (VI) vẫn còn", _doc_vi.is_file())
check("tài liệu tra cứu biến môi trường (EN) vẫn còn", _doc_en.is_file())

_vi = _doc_vi.read_text(encoding="utf-8") if _doc_vi.is_file() else ""
# Mỗi biến từng được giải thích trong khối chú thích cũ phải tìm được ở tài liệu, kẻo lần dọn
# này là xoá mất kiến thức chứ không phải chuyển chỗ.
for _b in ("JAVIS_HOST", "JAVIS_PORT", "JAVIS_REQUIRE_LOGIN", "JAVIS_ADMIN_USER",
           "JAVIS_ADMIN_PASSWORD", "JAVIS_SETUP_2FA", "JAVIS_SECURE_COOKIE",
           "JAVIS_ALLOWED_HOSTS", "WATCHTOWER_TOKEN", "JAVIS_AUTO_UPDATE",
           "JAVIS_AUTO_UPDATE_INTERVAL", "CLAUDE_CWD", "BRAINS_DIR", "OBSIDIAN_VAULT_PATH",
           "BRAIN_PATH", "JAVIS_STATE_DIR", "JAVIS_ENABLE_USER_PLUGINS"):
    check(f"{_b} vẫn được giải thích trong docs/16-cau-hinh-env.md", _b in _vi)

check("README chỉ đúng chỗ tra cứu đầy đủ",
      "16-cau-hinh-env" in (ROOT / "README.md").read_text(encoding="utf-8"))

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_env_example_may_doc_duoc: tất cả pass")
