"""Desktop installers: JavisOS-Setup.exe (Windows) and JavisOS-macOS.dmg (macOS).

    python tests/run.py desktop_installer

The .exe and .dmg are only built on Windows and macOS runners (desktop-installers.yml, which
also does a real install on Windows). This Linux test guards the invariants whose breakage
installs fine and fails later, where nobody looks:
- the shortcut must open Javis WITHOUT restarting it (start-javis.vbs always kills first);
- the code must be a git clone in a folder the app and the uninstaller agree on, or the
  Update button stops working and the uninstaller loses track of the brain;
- Windows script files must stay ASCII (PowerShell 5.1 and wscript read them as ANSI), and the
  Inno script must keep its BOM (it holds Vietnamese text).
"""
from _paths import ROOT  # noqa: E402
import os
import plistlib
import re
import shutil
import subprocess
import sys

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


PK = ROOT / "packaging"
ISS = PK / "windows" / "javis-setup.iss"
BOOT_PS1 = PK / "windows" / "bootstrap.ps1"
OPEN_VBS = ROOT / "open-javis.vbs"
LAUNCHER = PK / "macos" / "launcher.sh"
BOOT_SH = PK / "macos" / "bootstrap.sh"
BUILD_DMG = PK / "macos" / "build-dmg.sh"
WF = ROOT / ".github" / "workflows" / "desktop-installers.yml"

for f in (ISS, BOOT_PS1, OPEN_VBS, LAUNCHER, BOOT_SH, BUILD_DMG, WF,
          PK / "assets" / "javis.ico", PK / "assets" / "javis.icns"):
    check(f"exists: {f.relative_to(ROOT)}", f.exists())

iss_raw = ISS.read_bytes()
iss = iss_raw.decode("utf-8-sig")
boot = BOOT_PS1.read_text(encoding="utf-8")
vbs = OPEN_VBS.read_text(encoding="utf-8")
launcher = LAUNCHER.read_text(encoding="utf-8")
boot_sh = BOOT_SH.read_text(encoding="utf-8")
wf = WF.read_text(encoding="utf-8")
install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
main_py = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

# ---- encodings ----
for f in (BOOT_PS1, OPEN_VBS, ROOT / "install.ps1"):
    check(f"{f.name} is pure ASCII (read as ANSI on Windows)", f.read_bytes().isascii())
check("javis-setup.iss starts with a UTF-8 BOM (Vietnamese messages)", iss_raw.startswith(b"\xef\xbb\xbf"))

# ---- open without restarting ----
server_up = vbs.split("Function ServerUp()", 1)[-1].split("End Function", 1)[0]
check("CANARY: open-javis.vbs only calls start-javis.vbs (which kills the running server) when /health fails",
      re.search(r'If ServerUp\(\) Then\s+OpenWindow\s+Else\s+sh\.Run "wscript\.exe //nologo """ & root & "\\start-javis\.vbs"" /open"',
                vbs) is not None and "/health" in server_up and "http.Status = 200" in server_up)
check("open-javis.vbs opens an app window (--app=) with a default-browser fallback",
      "--app=" in vbs and "sh.Run url, 1, False" in vbs)
check("open-javis.vbs honours JAVIS_PORT", "JAVIS_PORT" in vbs)
shortcut_lines = [ln for ln in iss.splitlines() if ln.startswith("Name: \"{auto") and "wscript.exe" in ln]
check("every wscript shortcut in the installer runs open-javis.vbs, never start-javis.vbs",
      len(shortcut_lines) == 2 and all("open-javis.vbs" in ln and "start-javis.vbs" not in ln for ln in shortcut_lines),
      shortcut_lines)
check("the 'open now' checkbox also uses open-javis.vbs and only after a good bootstrap",
      re.search(r'^Filename: "\{sys\}\\wscript\.exe";.*open-javis\.vbs.*postinstall.*Check: BootstrapOk', iss, re.M) is not None)
check("CANARY: macOS launcher hands an installed Javis to bin/javis-start.sh (opens, never restarts)",
      'exec "${JAVIS_HOME}/bin/javis-start.sh"' in launcher)

# ---- one folder, agreed on everywhere ----
check("installer CodeDir and bootstrap.ps1 default agree on %USERPROFILE%\\JavisOS",
      "ExpandConstant('{%USERPROFILE}') + '\\JavisOS'" in iss
      and '(Join-Path $env:USERPROFILE "JavisOS")' in boot)
check("macOS launcher and bootstrap.sh agree on ~/JavisOS",
      'JAVIS_HOME="${JAVIS_HOME:-$HOME/JavisOS}"' in launcher and 'JAVIS_HOME="${JAVIS_HOME:-$HOME/JavisOS}"' in boot_sh)
check("Windows wizard does not ask for a folder (the clone path is fixed)", "DisableDirPage=yes" in iss)
check("per-user install, no admin prompt from the wizard", "PrivilegesRequired=lowest" in iss)

# ---- git clone, so the Update button works ----
for name, src in (("bootstrap.ps1", boot), ("bootstrap.sh", boot_sh)):
    check(f"{name} clones with --filter=blob:none (full history for updater merge/rollback)",
          "git clone --filter=blob:none" in src)
    check(f"{name} does not shallow-clone (--depth breaks the updater merge)",
          not any("git clone" in ln and "--depth" in ln for ln in src.splitlines()))
    check(f"{name} leaves an existing clone alone (it holds the brain)", ".git" in src and "giu nguyen" in src)
    check(f"{name} refuses to clone over a non-empty folder", "khong phai ban Javis" in src)
check("bootstrap.ps1 hands over to install.ps1 -NoStart and checks its exit code",
      '"-NoStart"' in boot and "$LASTEXITCODE -ne 0" in boot.split("install.ps1")[-1])
check("bootstrap.sh runs install.sh", "bash ./install.sh" in boot_sh)

# ---- uninstall ----
m = re.search(r'_AUTOSTART_NAME = "([^"]+)"', main_py)
check("uninstaller removes the same Run entry the app writes",
      m is not None and f"CurrentVersion\\Run', '{m.group(1)}'" in iss, m and m.group(1))
check("uninstaller stops Javis first", "stop-javis.ps1" in iss and "usUninstall" in iss)
check("uninstaller keeps the brain folder and says where it is", "DataKept" in iss and "[UninstallDelete]" in iss
      and "JavisOS" not in iss.split("[UninstallDelete]")[1].split("[Code]")[0])

# ---- install.ps1 / install.sh fixes the installers rely on ----
check("install.ps1 no longer trusts a bare `python` (Microsoft Store stub)", '(Have "python")' not in install_ps1
      and "Find-Python" in install_ps1)
check("install.ps1 creates the venv with the probed interpreter", "& $script:PyExe @script:PyArgs -m venv .venv" in install_ps1)
check("install.ps1 has a no-winget fallback for Python and Node",
      "python.org/ftp/python" in install_ps1 and "SHASUMS256.txt" in install_ps1)
check("install.sh node tarball fallback picks darwin on a Mac", '-${nos}-${na}' in install_sh and "nos=darwin" in install_sh)

# ---- the .app bundle actually assembles ----
dist = ROOT / "dist" / "dmg-stage"
if shutil.which("bash") and os.name != "nt":
    r = subprocess.run(["bash", str(BUILD_DMG)], env={**os.environ, "NO_DMG": "1"}, capture_output=True, text=True)
    check("build-dmg.sh NO_DMG=1 assembles the app", r.returncode == 0, r.stderr[-400:])
    app = dist / "JAVIS OS.app" / "Contents"
    if r.returncode == 0:
        info = plistlib.loads((app / "Info.plist").read_bytes())
        ver = (ROOT / "VERSION").read_text().strip()
        check("Info.plist version follows VERSION", info.get("CFBundleShortVersionString") == ver, info)
        check("Info.plist executable and icon exist",
              (app / "MacOS" / info["CFBundleExecutable"]).exists()
              and (app / "Resources" / (info["CFBundleIconFile"] + ".icns")).exists())
        check("app executable is executable", os.access(app / "MacOS" / "javis", os.X_OK))
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
for f in (LAUNCHER, BOOT_SH, BUILD_DMG, ROOT / "install.sh", ROOT / "bin" / "javis-start.sh"):
    r = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
    check(f"bash -n {f.relative_to(ROOT)}", r.returncode == 0, r.stderr)
check("in-repo JAVIS OS.app now has the icon its Info.plist names",
      (ROOT / "JAVIS OS.app" / "Contents" / "Resources" / "javis.icns").exists())

# ---- publishing and docs agree on the download links ----
base = "https://github.com/blogminhquy/javis-os/releases/download/desktop/"
check("workflow publishes both files on the fixed 'desktop' release",
      "gh release upload desktop out/JavisOS-Setup.exe out/JavisOS-macOS.dmg --clobber" in wf)
check("workflow publishes only from main", "github.ref == 'refs/heads/main'" in wf)
check("the desktop release never becomes 'latest'", "--latest=false" in wf)
for doc in ("QUICKSTART.md", "QUICKSTART.en.md"):
    s = (ROOT / doc).read_text(encoding="utf-8")
    check(f"{doc} links the Windows installer", base + "JavisOS-Setup.exe" in s)
    check(f"{doc} links the macOS installer", base + "JavisOS-macOS.dmg" in s)

# ---- repo rule: no long dashes ----
for f in (ISS, BOOT_PS1, OPEN_VBS, LAUNCHER, BOOT_SH, BUILD_DMG, WF, PK / "make_icons.py"):
    s = f.read_text(encoding="utf-8-sig")
    check(f"{f.name} has no em/en dash", "—" not in s and "–" not in s)

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All desktop_installer tests passed.")
