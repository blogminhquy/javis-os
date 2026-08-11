"""install.sh phải đặt SẴN tài khoản quản trị, để không ai phải đi đọc MÃ THIẾT LẬP trong log.

    python tests/run.py install_admin      (KHÔNG mạng; cần bash + python3)

Bối cảnh: chạy Javis ra công khai mà chưa có admin thì server sinh một MÃ THIẾT LẬP ngẫu nhiên
và CHỈ in nó vào log lúc khởi động (`config.setup_token_required`, `main.py` mục auth bootstrap).
Người dùng phải SSH vào máy, đọc log, dán mã vào trình duyệt mới tạo được tài khoản.

Cái mã đó có lý do tồn tại và KHÔNG bị bỏ: nó chặn người lạ chỉ-có-URL chiếm quyền admin trước
chủ máy, mà thứ họ chiếm được là một máy có Bash, chạy full quyền, cắm sẵn vào POS/quảng cáo/
email của chủ. Nhưng nó không nên là đường CHÍNH. Người đang chạy `install.sh` vốn đã ngồi trên
máy chủ rồi, nên hỏi họ một câu là xoá sạch bước đọc-log mà không mở lỗ nào.

File này canh đúng hai thứ dễ hỏng khi sửa shell: khối tự sinh có chạy không, và `.env` ghi ra
có đọc lại được nguyên vẹn không (mật khẩu người ta gõ có thể chứa dấu nháy, gạch đứng, ký tự
thoát - mọi thứ làm vỡ một lệnh sed viết theo lối thường gặp).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


SRC = (ROOT / "install.sh").read_text(encoding="utf-8")

# ---- 1. Cú pháp + hợp đồng của khối ----
check("install.sh còn chạy được (bash -n)",
      subprocess.run(["bash", "-n", str(ROOT / "install.sh")]).returncode == 0)
check("có khối đặt sẵn tài khoản quản trị", "JAVIS_ADMIN_PASSWORD" in SRC)
check("KHÔNG dùng sed để ghi mật khẩu vào .env (mật khẩu chứa | & \\ \" ' là vỡ)",
      not re.search(r"sed .*JAVIS_ADMIN_PASSWORD", SRC))
check("chạy không có bàn phím vẫn tự sinh, không bỏ trống",
      "ADMIN_PW=\"$(_gen_pw)\"; ADMIN_PW_SINH=\"$ADMIN_PW\"" in SRC)
check("mật khẩu tự sinh chỉ in ra MỘT lần, ở cuối màn hình cài",
      SRC.count("$ADMIN_PW_SINH") == 1 and 'ADMIN_PW_SINH:-' in SRC)
check("tối thiểu 8 ký tự, khớp với rào của server", '-lt 8' in SRC)
check("đã có sẵn trong .env thì GIỮ NGUYÊN, không ghi đè",
      "_env_has JAVIS_ADMIN_PASSWORD" in SRC)
check(".env bị siết quyền sau khi ghi mật khẩu vào", "chmod 600 .env" in SRC)

# Cơ chế MÃ THIẾT LẬP vẫn phải còn: đây là lưới cho người deploy bằng cách khác. Bỏ nó là mở
# toang /auth/setup cho ai gõ trúng URL trước chủ máy.
_cfg = (SERVER / "config.py").read_text(encoding="utf-8")
check("CANARY: cơ chế MÃ THIẾT LẬP vẫn còn nguyên trong server",
      "def setup_token_required" in _cfg and "def check_setup_token" in _cfg)


# ---- 2. Chạy THẬT khối đó trong thư mục tạm ----
def _chay_khoi(env_ban_dau: str, lan: int = 1):
    """Trích khối 7b ra chạy độc lập (không tty → nhánh tự sinh). Trả (.env sau khi chạy, stdout)."""
    tmp = Path(tempfile.mkdtemp(prefix="javis-install-"))
    try:
        (tmp / ".env").write_text(env_ban_dau, encoding="utf-8")
        khoi = SRC[SRC.index("# --- 7b."):SRC.index("# --- 8.")]
        (tmp / "blok.sh").write_text(
            "log(){ echo \"-> $*\"; }\nok(){ echo \"OK $*\"; }\nwarn(){ echo \"!! $*\"; }\n"
            "set -euo pipefail\n" + khoi, encoding="utf-8")
        out = ""
        for _ in range(lan):
            r = subprocess.run(["bash", "blok.sh"], cwd=tmp, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
            out += r.stdout + r.stderr
        return (tmp / ".env").read_text(encoding="utf-8"), out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _doc(env_text: str, key: str):
    from dotenv import dotenv_values
    tmp = Path(tempfile.mkdtemp(prefix="javis-dotenv-"))
    try:
        p = tmp / ".env"
        p.write_text(env_text, encoding="utf-8")
        return dotenv_values(str(p)).get(key)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_mau = (ROOT / "env.example").read_text(encoding="utf-8")
_env1, _out1 = _chay_khoi(_mau)
_pw1 = _doc(_env1, "JAVIS_ADMIN_PASSWORD")
check("chạy không tty -> có sinh mật khẩu", bool(_pw1))
check("mật khẩu sinh ra đủ dài", len(_pw1 or "") >= 16)
check("mật khẩu sinh ra chỉ gồm chữ và số (an toàn cho .env của Docker Compose)",
      bool(_pw1) and _pw1.isalnum())
check("tên đăng nhập mặc định là admin", _doc(_env1, "JAVIS_ADMIN_USER") == "admin")
# env.example có sẵn hai dòng ĐÃ COMMENT cho hai biến này. Ghi đè nhầm vào dòng comment thì
# .env có biến nhưng vẫn nằm sau dấu #, tức server không thấy gì và người dùng lại về đọc log.
check("dòng mẫu đang comment trong env.example KHÔNG bị nhận nhầm là đã đặt",
      "# JAVIS_ADMIN_PASSWORD=doi-mat-khau-manh-o-day" in _env1)

# Chạy lại lần hai: cài lại / chạy lại script là chuyện thường, không được đổi mật khẩu đang dùng.
_env2, _out2 = _chay_khoi(_env1)
check("chạy lần hai KHÔNG đổi mật khẩu đang dùng",
      _doc(_env2, "JAVIS_ADMIN_PASSWORD") == _pw1)
check("và nói rõ là giữ nguyên", "giữ nguyên" in _out2)

# Không có .env sẵn (người dùng xoá đi) cũng phải chạy được.
_env3, _ = _chay_khoi("")
check("file .env rỗng vẫn đặt được tài khoản", bool(_doc(_env3, "JAVIS_ADMIN_PASSWORD")))


# ---- 3. Ghi .env an toàn với mật khẩu hiểm ----
# Đây là chỗ một lệnh sed sẽ chết: dấu nháy kép, gạch chéo ngược, gạch đứng, & và #.
_HIEM = 'a"b\\c|d&e$f\'g #h i'
_tmp = Path(tempfile.mkdtemp(prefix="javis-hiem-"))
try:
    (_tmp / ".env").write_text("X=1\n", encoding="utf-8")
    _fn = SRC[SRC.index("_env_set() {"):SRC.index("_env_has()")]
    (_tmp / "f.sh").write_text("set -euo pipefail\n" + _fn +
                               '\n_env_set JAVIS_ADMIN_PASSWORD "$1"\n', encoding="utf-8")
    subprocess.run(["bash", "f.sh", _HIEM], cwd=_tmp, check=True, capture_output=True)
    _sau = (_tmp / ".env").read_text(encoding="utf-8")
    check("mật khẩu hiểm ghi rồi đọc lại NGUYÊN VẸN",
          _doc(_sau, "JAVIS_ADMIN_PASSWORD") == _HIEM)
    check("và không nuốt mất dòng cũ trong .env", "X=1" in _sau)
finally:
    shutil.rmtree(_tmp, ignore_errors=True)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test install_admin đã qua.")
