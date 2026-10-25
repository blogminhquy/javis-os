"""Cài trên Windows hoặc macOS là Javis tự chạy cùng máy và tự mở trình duyệt (0.306.0).

    python tests/run.py tu_mo_cung_may

Chủ repo 24/10/2026: "Mặc định cài javis trên win hoặc trên mac os thì em cài khởi động cùng trình duyệt giúp anh".
Trước bản này tự khởi động phải bật tay (javis-autostart.bat install, ./bin/javis-autostart.sh install, hoặc nút
trong dashboard) và khi bật thì chỉ chạy NỀN, mở máy lên không thấy Javis đâu. Checks:
  1. Windows: start-javis.vbs có chế độ /open (chờ /health có giới hạn, mở cửa sổ app, không có Edge/Chrome thì
     trình duyệt mặc định); không /open thì vẫn chạy ngầm như cũ (nút Cập nhật gọi kiểu đó, không được bật tab).
  2. Windows: lệnh của dashboard và của javis-autostart.ps1 là MỘT chuỗi, lệnh cũ không /open không bị báo
     "đường dẫn cũ"; install.ps1 và setup.bat bật tự khởi động mặc định, có cách tắt.
  3. macOS: javis-autostart.sh viết thêm agent mở trình duyệt (chạy một lần, không KeepAlive); install.sh trên
     Darwin dùng nó thay cho nohup. Chạy thật script với launchctl giả, đọc plist bằng plistlib.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tumo-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def doc(p):
    return (ROOT / p).read_bytes().decode("utf-8").replace("\r\n", "\n")


# ---- 1. start-javis.vbs /open ----
vbs = doc("start-javis.vbs")
i_run = vbs.find("server\\main.py")
i_open = vbs.find('If LCase(WScript.Arguments(0)) = "/open" Then MoDashboard')
check("vbs: /open chỉ chạy SAU khi đã bật server", 0 < i_run < i_open, (i_run, i_open))
check("vbs: chờ /health có giới hạn (60 lần, mỗi lần 1 giây)", "For i = 1 To 60" in vbs and '"/health"' in vbs)
check("vbs: tôn trọng JAVIS_PORT", "%JAVIS_PORT%" in vbs)
check("vbs: mở dạng cửa sổ app như JAVIS OS.bat", "--app=" in vbs and "msedge.exe" in vbs and "chrome.exe" in vbs)
check("vbs: không có Edge/Chrome thì mở trình duyệt mặc định", "sh.Run url, 1, False" in vbs)
check("vbs: phần mới chỉ dùng ASCII (wscript đọc file theo ANSI)",
      all(ord(c) < 128 for c in vbs[vbs.find("' 0.306.0"):]))
up = (ROOT / "server" / "updater.py").read_text(encoding="utf-8")
check("nút Cập nhật vẫn gọi vbs KHÔNG /open (cập nhật không được bật thêm cửa sổ)",
      'str(ROOT / "start-javis.vbs")]' in up and "/open" not in up)

# ---- 2. Windows: một chuỗi lệnh, cài là bật ----
import main  # noqa: E402

cmd = main._autostart_command()
check("dashboard: lệnh có /open", cmd.endswith('start-javis.vbs" /open') and cmd.startswith("wscript.exe //nologo "), cmd)
check("dashboard: lệnh cũ là đúng lệnh trước 0.306.0", main._autostart_legacy_command() + " /open" == cmd)
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("lệnh cũ không bị báo đường dẫn cũ (vẫn chạy được, chỉ chưa mở trình duyệt)",
      "val.strip() not in (expected, _autostart_legacy_command())" in src)
ps1 = doc("javis-autostart.ps1")
check("javis-autostart.ps1 ghi đúng chuỗi của dashboard",
      '$cmd = "wscript.exe //nologo `"$vbs`" /open"' in ps1 and '$Name = "JavisOS"' in ps1)
check("javis-autostart.ps1 gỡ cờ chặn của Task Manager như nút trong dashboard", "StartupApproved" in ps1 and "-band 1" in ps1)
check("javis-autostart.ps1 dọn shortcut kiểu cũ (tránh hai bản giành cổng)", "Remove-Item $Lnk" in ps1)
check("javis-autostart.ps1 chỉ dùng ASCII", all(ord(c) < 128 for c in ps1))
inst = doc("install.ps1")
check("install.ps1: bật tự khởi động mặc định, tắt bằng -NoAutostart",
      "[switch]$NoAutostart" in inst and "if (-not $NoAutostart)" in inst and "javis-autostart.ps1" in inst)
check("install.ps1: cài xong mở luôn dashboard (/open)", '"//nologo `"$vbs`" /open"' in inst)
check("install.ps1 vẫn ASCII", all(ord(c) < 128 for c in inst))
bat = doc("setup.bat")
check("setup.bat: bật tự khởi động, JAVIS_NO_AUTOSTART=1 để bỏ",
      'if not "%JAVIS_NO_AUTOSTART%"=="1"' in bat and "javis-autostart.ps1\" install" in bat)
check("setup.bat bật trước khi chạy server ở cửa sổ", bat.find("javis-autostart.ps1") < bat.find("python main.py"))

# ---- 3. macOS ----
SH = shutil.which("bash")
if SH:
    t = Path(tempfile.mkdtemp(prefix="tumo-mac-"))
    app = t / "app"
    (app / "bin").mkdir(parents=True)
    (app / ".venv" / "bin").mkdir(parents=True)
    (t / "fake").mkdir()
    shutil.copy(ROOT / "bin" / "javis-autostart.sh", app / "bin" / "javis-autostart.sh")
    (app / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
    (app / ".venv" / "bin" / "python").chmod(0o755)
    (t / "fake" / "launchctl").write_text(f'#!/bin/sh\necho "$@" >> {t}/lc.log\n')
    (t / "fake" / "launchctl").chmod(0o755)

    def chay(action, **env):
        e = dict(os.environ, HOME=str(t), PATH=f"{t}/fake:" + os.environ.get("PATH", ""), **env)
        return subprocess.run([SH, str(app / "bin" / "javis-autostart.sh"), action], env=e, capture_output=True, text=True,
                              timeout=30)

    r = chay("install", JAVIS_PORT="7790")
    la = t / "Library" / "LaunchAgents"
    srv = plistlib.loads((la / "com.javis.os.plist").read_bytes())
    op = plistlib.loads((la / "com.javis.os.open.plist").read_bytes())
    check("mac: agent server giữ nhãn com.javis.os (updater/watchdog nhận diện)", srv["Label"] == "com.javis.os" and srv["KeepAlive"] is True)
    check("mac: agent mở trình duyệt chạy một lần mỗi lần đăng nhập, KHÔNG KeepAlive",
          op["Label"] == "com.javis.os.open" and op.get("RunAtLoad") is True and "KeepAlive" not in op)
    body = op["ProgramArguments"][2]
    check("mac: chờ /health có giới hạn rồi mở đúng cổng",
          "seq 1 60" in body and "http://127.0.0.1:7790/health && break" in body and body.endswith("open http://127.0.0.1:7790"), body)
    sh_ok = subprocess.run(["sh", "-n", "-c", body]).returncode == 0
    check("mac: lệnh trong plist là shell hợp lệ", sh_ok)
    lc = (t / "lc.log").read_text()
    check("mac: nạp cả hai agent (nạp agent mở là trình duyệt mở luôn sau khi cài)",
          f"load {la}/com.javis.os.plist" in lc and f"load {la}/com.javis.os.open.plist" in lc, lc)
    chay("install", JAVIS_AUTOSTART_OPEN="0")
    check("mac: JAVIS_AUTOSTART_OPEN=0 chỉ chạy nền", (la / "com.javis.os.plist").exists() and not (la / "com.javis.os.open.plist").exists())
    chay("install")
    chay("uninstall")
    check("mac: uninstall gỡ cả hai", not list(la.glob("*.plist")))
else:
    print("skip mac script run (no bash)")

ish = doc("install.sh")
i_mac = ish.find('if [ "$(uname -s)" = "Darwin" ]')
i_sysd = ish.find("command -v systemctl")
check("install.sh: macOS đi LaunchAgent trước nhánh systemd/nohup", 0 < i_mac < i_sysd)
check("install.sh: có cách bỏ (JAVIS_NO_AUTOSTART=1), bản thứ hai (JAVIS_NAME) không đè nhãn",
      '"${JAVIS_NO_AUTOSTART:-0}" != "1"' in ish and '[ -z "${JAVIS_NAME:-}" ]' in ish)

for f in ("start-javis.vbs", "javis-autostart.ps1", "install.ps1", "setup.bat", "bin/javis-autostart.sh", "install.sh",
          "tests/python/test_tu_mo_cung_may.py"):
    s = doc(f)
    check("no em or en dash in " + f, chr(0x2014) not in s and chr(0x2013) not in s)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
