"""Cài mới trên Windows: dò CLI không được phụ thuộc mình PATH. Chạy tay / CI:

    python tests/run.py cai_windows

Ba triệu chứng chủ dự án gặp khi nhờ Claude cài Javis trên máy Windows mới (16/09), cả ba đều
cùng một gốc:

  1. Cài xong, mở localhost:7777, đăng nhập thì báo "thiếu CLI".
  2. Nhờ Claude sửa thì chat được, nhưng cài thêm Antigravity CLI xong là Claude Code lại bị
     báo "chưa cài" và bắt cài lại từ đầu.
  3. Có lúc còn báo thiếu claude-agent-sdk.

Gốc bệnh:
  - Javis dò binary bằng PATH cộng một danh sách thư mục mà TOÀN BỘ là đường Unix/mac
    (/opt/homebrew, ~/.npm-global...). Trên Windows danh sách đó vô dụng.
  - PATH trên Windows nằm trong registry và bị mọi installer ghi vào. `setx` CẮT PATH ở 1024
    ký tự, nên một installer khác (đúng như Antigravity) có thể xoá sạch `%APPDATA%\\npm` khỏi
    PATH, làm một CLI vẫn nằm nguyên trên ổ đĩa trở thành "chưa cài".
  - Tiến trình server giữ PATH của LÚC NÓ BẬT, nên cài CLI sau đó thì nó không thấy.
  - setup.bat không kiểm mã lỗi của `pip install`, nên pip hỏng mà vẫn chạy tiếp và người dùng
    chỉ gặp lỗi "thiếu SDK" ở tận màn đăng nhập.

Phủ: dò binary (nhớ lại chỗ đã thấy, thư mục Windows, env override), câu báo thiếu CLI nói đủ
việc cần làm, và ba file cài (install.ps1, setup.bat, install.sh) cài đủ BỐN CLI.

KHÔNG chạm mạng.
KHÔNG dùng ký tự em dash.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import stat
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-caiwin-")

import claude_cli as cc  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _binary_gia(thu_muc: Path, ten: str) -> Path:
    thu_muc.mkdir(parents=True, exist_ok=True)
    f = thu_muc / ten
    f.write_text("#!/bin/sh\necho gia\n", encoding="utf-8")
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return f


# ============================================================
# 1. NHỚ chỗ đã thấy: PATH bị cắt cụt vẫn tìm ra binary còn trên ổ đĩa
# ============================================================
_bin_dir = Path(tempfile.mkdtemp(prefix="javis-fakebin-"))
_fake = _binary_gia(_bin_dir, "javisfakecli")
_path_that = os.environ.get("PATH", "")
os.environ["PATH"] = str(_bin_dir)
check("tìm được binary trên PATH", cc.tim_binary("javisfakecli") == str(_fake))

# Đây là ca Antigravity: PATH bị một installer khác ghi đè/cắt cụt, binary KHÔNG mất.
os.environ["PATH"] = str(Path(tempfile.mkdtemp(prefix="javis-empty-")))
cc._BIN_NHO["data"] = None          # tiến trình mới: đọc lại bản nhớ từ file
check("PATH bị cắt cụt vẫn dùng lại được chỗ đã nhớ",
      cc.tim_binary("javisfakecli") == str(_fake))
check("bản nhớ ghi xuống file trong STATE_DIR",
      (Path(os.environ["JAVIS_STATE_DIR"]) / "bin_paths.json").exists())

# Gỡ THẬT thì phải báo là chưa cài - bản nhớ không được biến thành lời nói dối.
_fake.unlink()
cc._BIN_NHO["data"] = None
check("gỡ CLI thật thì trả None, không giữ đường dẫn chết",
      cc.tim_binary("javisfakecli") is None)
os.environ["PATH"] = _path_that

# ============================================================
# 2. Thư mục cài của Windows
# ============================================================
check("danh sách thư mục Windows có npm global, nvm, volta, scoop",
      any("npm" in m for m in cc._THU_MUC_BIN_WINDOWS)
      and any("NVM" in m for m in cc._THU_MUC_BIN_WINDOWS)
      and any("Volta" in m for m in cc._THU_MUC_BIN_WINDOWS)
      and any("scoop" in m for m in cc._THU_MUC_BIN_WINDOWS))
check("có cả %LOCALAPPDATA%\\npm, không chỉ %APPDATA%\\npm",
      any("LOCALAPPDATA" in m and "npm" in m for m in cc._THU_MUC_BIN_WINDOWS))
# Bung biến môi trường: biến không tồn tại thì BỎ, không được trả về chuỗi còn dấu %.
_tmp_appdata = tempfile.mkdtemp(prefix="javis-appdata-")
os.environ["APPDATA"] = _tmp_appdata
Path(_tmp_appdata, "npm").mkdir(exist_ok=True)
os.environ.pop("NVM_SYMLINK", None)
_dirs = cc._thu_muc_bin_windows()
check("bung được %APPDATA%\\npm khi thư mục tồn tại",
      any(d.endswith("npm") and _tmp_appdata in d for d in _dirs))
check("biến môi trường không có thì bỏ, không trả chuỗi còn dấu %",
      not any("%" in d for d in _dirs))

# ============================================================
# 3. Env override cho cả bốn CLI (trước đây `claude` là cái duy nhất thiếu)
# ============================================================
_claude_gia = _binary_gia(Path(tempfile.mkdtemp(prefix="javis-cl-")), "claude-gia")
os.environ["JAVIS_CLAUDE_BIN"] = str(_claude_gia)
check("JAVIS_CLAUDE_BIN chỉ thẳng được đường dẫn lạ",
      cc.find_claude_cli() == str(_claude_gia))
os.environ.pop("JAVIS_CLAUDE_BIN", None)
src_cc = (SERVER / "claude_cli.py").read_text(encoding="utf-8")
src_agy = (SERVER / "antigravity_cli.py").read_text(encoding="utf-8")
src_grok = (SERVER / "grok_cli.py").read_text(encoding="utf-8")
check("cả bốn CLI đều có cửa thoát bằng biến môi trường",
      "JAVIS_CLAUDE_BIN" in src_cc and "JAVIS_CODEX_BIN" in src_cc
      and "JAVIS_AGY_BIN" in src_agy and "JAVIS_GROK_BIN" in src_grok)

# ============================================================
# 4. Câu báo thiếu CLI phải nói ĐỦ ba việc
# ============================================================
_cau = cc.cau_thieu_cli("claude", "Claude")
check("câu báo có lệnh cài cụ thể", "npm install -g @anthropic-ai/claude-code" in _cau)
check("câu báo nhắc KHỞI ĐỘNG LẠI JAVIS (tiến trình giữ PATH cũ)",
      "KHỞI ĐỘNG LẠI JAVIS" in _cau)
check("câu báo giữ nguyên cụm cũ để người quen vẫn nhận ra", _cau.startswith("Claude CLI chưa cài"))
for _t, _l in (("codex", "npm install -g @openai/codex"),
               ("agy", "antigravity.google/cli/install"),
               ("grok", "x.ai/cli/install")):
    check(f"câu báo của {_t} có lệnh cài", _l in cc.cau_thieu_cli(_t))
check("không còn chỗ nào trả câu trần 'Claude CLI chưa cài'",
      '"Claude CLI chưa cài"' not in src_cc
      and '"Claude CLI chưa cài"' not in (SERVER / "main.py").read_text(encoding="utf-8"))

# ============================================================
# 5. Ba file cài phải cài đủ BỐN CLI trong một lượt
# ============================================================
ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
bat = (ROOT / "setup.bat").read_text(encoding="utf-8")
sh = (ROOT / "install.sh").read_text(encoding="utf-8")

check("có install.ps1 (đường một lệnh cho Windows)", bool(ps1.strip()))
for goi in ("@anthropic-ai/claude-code", "@openai/codex",
            "antigravity.google/cli/install.ps1", "x.ai/cli/install.ps1"):
    check(f"install.ps1 cài {goi}", goi in ps1)
check("install.ps1 KIỂM mã lỗi của pip (gốc lỗi 'thiếu claude-agent-sdk')",
      "pip install -r requirements.txt" in ps1 and "$LASTEXITCODE -ne 0" in ps1)
check("install.ps1 đọc lại PATH từ registry sau khi cài (kẻo tổng kết báo sai)",
      "Refresh-Path" in ps1 and "GetEnvironmentVariable" in ps1)
check("install.ps1 không hỏi gì giữa đường (agent chạy được không cần người bấm)",
      "pause" not in ps1.lower() and "Read-Host" not in ps1)
check("install.ps1 viết bằng ASCII (PowerShell đọc file không BOM bằng ANSI codepage)",
      ps1.isascii())

check("setup.bat kiểm mã lỗi pip rồi dừng hẳn", "pip install -r requirements.txt -q" in bat
      and "thieu claude-agent-sdk" in bat)
check("setup.bat cài thêm agy và grok", ":cai_script" in bat
      and "antigravity.google/cli/install.ps1" in bat and "x.ai/cli/install.ps1" in bat)
check("setup.bat trỏ sang install.ps1 cho đường một lệnh", "install.ps1" in bat)
check("setup.bat vẫn chỉ dùng ASCII", bat.isascii())

check("install.sh cài agy và grok", "antigravity.google/cli/install.sh" in sh
      and "x.ai/cli/install.sh" in sh and "cai_cli_script" in sh)

# STATE_DIR mặc định CHÍNH LÀ thư mục server/, nên bản nhớ phải được .gitignore che: không che
# thì mỗi lần chạy app là cây git bẩn thêm một file và `git add -A` commit đường dẫn máy người
# khác (test_ignore_files.py canh đúng loại rác này).
import subprocess  # noqa: E402
_che = subprocess.run(["git", "check-ignore", "server/bin_paths.json"], cwd=ROOT,
                      capture_output=True, text=True)
check("bản nhớ bị .gitignore che (STATE_DIR mặc định là server/)", _che.returncode == 0)

readme = (ROOT / "README.md").read_text(encoding="utf-8")
check("README nói một lệnh cài hết cho Windows", "install.ps1" in readme)
check("README nhắc phải khởi động lại Javis khi cài thêm CLI",
      "khởi động lại javis" in readme.lower())
check("README không còn mời Gemini CLI (đã gỡ ở 0.50.0)", "Gemini CLI" not in readme)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_cai_windows: tat ca pass")
