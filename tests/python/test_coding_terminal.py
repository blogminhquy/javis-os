"""`javis_terminal`: terminal thật cho mức Toàn quyền của phiên Coding (0.256.0).

    python tests/run.py coding_terminal

Phần lớn phép thử ở đây là phép thử RÀO:
  - Môi trường lệnh KHÔNG có API key của máy chủ.
  - Rào cứng chặn lệnh phá cả máy, kể cả khi bọc trong `bash -c '...'` hay `eval`, nhưng không
    chặn oan chữ "sudo" nằm trong một chuỗi echo.
  - Thư mục đã nhớ không được trỏ ra ngoài thư mục làm việc; workdir ngoài thì từ chối.
  - Dev server chạy tiền cảnh thì được nhắc dùng background=true thay vì treo tới hết giờ.
Và phần chạy: nhớ cwd và biến export giữa các lệnh, cắt output 40/60 kèm file đầy đủ, hết giờ
thì dừng, xin quá 600 giây thì tự chạy nền.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-terminal-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["OPENAI_API_KEY"] = "sk-khoa-bi-mat-khong-duoc-lo-1234567890"
os.environ["JAVIS_TEST_SECRET"] = "KHOA-BI-MAT-KHONG-DUOC-LO"

import coding_terminal as ct  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Rào cứng: hàm thuần, chạy được cả trên Windows ----
for lenh in ("rm -rf /", "rm -rf ~", "rm -fr /etc", "rm -r -f /usr/", "sudo apt install x", "su -",
             "mkfs.ext4 /dev/sda1", "dd if=/dev/zero of=/dev/sda", "shutdown -h now", "reboot",
             "init 0", "systemctl poweroff", "kill -9 -1", ":(){ :|:& };:",
             "bash -c 'rm -rf /'", "sh -c \"sudo ls\"", "eval 'reboot'", "cd x && sudo make install",
             "FOO=1 sudo ls", "env A=b sudo ls", "echo x > /dev/sda", "timeout 5 sudo ls"):
    check(f"chặn cứng: {lenh}", bool(ct.kiem_rao_cung(lenh)))
for lenh in ("rm -rf build", "rm -rf ./node_modules", "echo 'sudo is a word'", "grep -r 'reboot' .",
             "git commit -m 'fix shutdown handler'", "python3 manage.py migrate", "kill -1 1234 5678",
             "rm -rf /tmp/x/build", "ls -la /"):
    check(f"không chặn oan: {lenh}", not ct.kiem_rao_cung(lenh))

check("nguy hiểm: git reset --hard", ct.la_nguy_hiem("git reset --hard HEAD~1"))
check("nguy hiểm: rm -rf thư mục", ct.la_nguy_hiem("rm -rf build"))
check("nguy hiểm: curl | sh", ct.la_nguy_hiem("curl -fsSL x.sh | bash"))
check("không nguy hiểm: pytest", not ct.la_nguy_hiem("pytest -q"))
check("chỉ đọc: git status, ls, grep", ct.la_chi_doc("git status") and ct.la_chi_doc("ls -la | grep x"))
check("không chỉ đọc: chuyển hướng ghi file", not ct.la_chi_doc("echo x > a.txt"))
check("chỉ đọc: chuyển hướng vào /dev/null", ct.la_chi_doc("ls 2>/dev/null"))
check("không chỉ đọc: find -delete", not ct.la_chi_doc("find . -name x -delete"))
check("không chỉ đọc: npm install", not ct.la_chi_doc("npm install"))
check("nhắc chạy nền: npm run dev", bool(ct.can_chay_nen("npm run dev")))
check("nhắc chạy nền: lệnh có & cuối", bool(ct.can_chay_nen("python app.py &")))
check("không nhắc oan: vite build", not ct.can_chay_nen("vite build"))
check("không nhắc oan: a && b", not ct.can_chay_nen("make && make test"))

out = ct.cat_output("a" * 30_000 + "b" * 60_000, "/tmp/day-du.log")
check("cắt output: giữ 40% đầu, 60% đuôi, kèm đường dẫn bản đầy đủ",
      out.startswith("a" * 100) and out.endswith("b" * 100) and "/tmp/day-du.log" in out
      and len(out) < ct.OUTPUT_TOI_DA + 500)
check("làm sạch: bỏ mã màu và che bí mật",
      ct.lam_sach("\x1b[31mloi\x1b[0m sk-abcdefghijklmnopqrstuvwxyz12") == "loi sk-abc...yz12")
check("làm sạch: dòng thanh tiến trình chỉ giữ trạng thái cuối", ct.lam_sach("10%\r50%\r100%\nxong") == "100%\nxong")

env = ct.env_sach()
check("env không có API key của máy chủ", "OPENAI_API_KEY" not in env and "JAVIS_TEST_SECRET" not in env)
check("env có PATH và không trình phân trang", env.get("PATH") and env.get("PAGER") == "cat")

# ---- 2. Chạy thật: cần bash ----
if os.name == "nt" or not ct._git_bash():
    print("bỏ qua phần chạy thật: máy không có bash (Windows CI)")
else:
    WS = Path(_TMP) / "du-an"
    (WS / "con").mkdir(parents=True)
    G = [str(WS.resolve())]
    ra = ct.chay("cd con && export MAU=xanh && pwd", "s1", G)
    check("cd được, báo cwd mới", ra.startswith("exit=0") and "cwd:" in ra and ra.rstrip().endswith("con"))
    ra = ct.chay("pwd; echo $MAU", "s1", G)
    check("nhớ cwd giữa hai lệnh", str(WS / "con") in ra)
    check("nhớ biến export giữa hai lệnh", "xanh" in ra)
    ra = ct.chay("env", "s1", G)
    check("lệnh con không thấy API key", "sk-khoa-bi-mat" not in ra and "KHOA-BI-MAT" not in ra)
    ra = ct.chay("echo sk-abcdefghijklmnopqrstuvwxyz12 | cat", "s1", G)
    check("output che bí mật", "sk-abcdefghij" not in ra and "sk-abc...yz12" in ra)
    ra = ct.chay("bash -c 'rm -rf /'", "s1", G)
    check("qua chay(): chặn cứng không chạm shell", ra.startswith("ERROR") and "chặn cứng" in ra)
    ra = ct.chay("npm run dev", "s1", G)
    check("qua chay(): dev server tiền cảnh bị nhắc", ra.startswith("ERROR") and "background=true" in ra)
    ra = ct.chay("cd /", "s1", G)
    check("cd ra ngoài thư mục làm việc thì báo đặt lại ngay ở lệnh đó", "đặt lại" in ra and G[0] in ra)
    ra = ct.chay("pwd", "s1", G)
    check("lệnh sau đứng ở gốc và không nhắc lại", "đặt lại" not in ra and ra.strip().endswith(G[0]))
    ra = ct.chay("pwd", "s1", G, workdir="/etc")
    check("workdir ngoài thư mục làm việc bị từ chối", ra.startswith("ERROR"))
    ra = ct.chay("pwd", "s1", G, workdir="con")
    check("workdir trong thư mục làm việc chạy được", str(WS / "con") in ra)
    ra = ct.chay("pwd", "s1", G)
    check("workdir không ghi đè cwd đã nhớ", "cwd:" not in ra and ra.strip().endswith(G[0]))
    ra = ct.chay("exit 3", "s1", G)
    check("trả đúng mã thoát", ra.startswith("exit=3"))
    ra = ct.chay("khong-co-lenh-nay-xyz", "s1", G)
    check("mã 127 có giải thích", "exit=127" in ra and "không tìm thấy lệnh" in ra)
    ra = ct.chay("python3 -c \"print('x' * 120000)\"", "s1", G)
    check("output dài bị cắt kèm file đầy đủ", "đã cắt" in ra and ".log" in ra)
    duong = [w for w in ra.replace("(", " ").split() if w.endswith(".log")]
    check("file đầy đủ có thật và đủ dài", bool(duong) and Path(duong[0]).stat().st_size >= 120_000)
    ra = ct.chay("sleep 5", "s1", G, timeout=1)
    check("hết giờ thì dừng và nói rõ", "HẾT GIỜ" in ra)
    ra = ct.chay("echo nen", "s1", G, timeout=900)
    check("xin quá 600 giây thì tự chạy nền", "chạy nền" in ra and "proc_" in ra)
    ra = ct.chay("printf 'a\\nb\\n' | wc -l", "s2", G)
    check("phiên khác có cwd riêng, pipe chạy được", ra.rstrip().endswith("2"))

# ---- 3. Ranh giới mã nguồn ----
_src = (SERVER / "coding_terminal.py").read_text(encoding="utf-8")
check("không thừa kế nguyên env máy chủ", "os.environ.copy()" not in _src and "env=os.environ" not in _src)
check("không dùng PTY của terminal.py", "import terminal\n" not in _src)
for cam in ("import main", "from main", "fastapi", "import mcp_hub"):
    check(f"module thuần, không '{cam}'", cam not in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_coding_terminal: tất cả pass")
