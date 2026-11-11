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
      '-File `"$inst`" -NoStart"' in boot and "if ($instCode -ne 0)" in boot.split("install.ps1")[-1])
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

check("CANARY: install.ps1 runs the agy/grok vendor scripts in a child PowerShell (an `exit` in them "
      "must not end install.ps1 before deps, .env and autostart)",
      not any("Invoke-Expression" in ln and not ln.lstrip().startswith("#") for ln in install_ps1.splitlines())
      and "-EncodedCommand $enc" in install_ps1 and "-EncodedCommand $enc\" -Minutes 10" in install_ps1)
check("install.ps1 still installs all four brains (claude, codex, agy, grok)",
      all(x in install_ps1 for x in ('"@anthropic-ai/claude-code"', '"@openai/codex"',
                                     "antigravity.google/cli/install.ps1", "x.ai/cli/install.ps1")))
check("install.sh still installs all four brains (claude, codex, agy, grok)",
      all(x in install_sh for x in ("@anthropic-ai/claude-code", "@openai/codex", "antigravity.google/cli/install.sh",
                                    "x.ai/cli/install.sh")))
cb = (PK / "check_brains.py").read_text(encoding="utf-8")
check("check_brains.py uses the server's own finders for all four brains",
      all(f in cb for f in ("find_claude_cli", "find_codex_cli", "find_antigravity_cli", "find_grok_cli")))
win_job = wf.split("\n  windows:", 1)[1].split("\n  macos:", 1)[0]
mac_job = wf.split("\n  macos:", 1)[1].split("\n  publish:", 1)[0]
check("CI installs the CLIs on Windows (no -SkipCli) and checks all four brains",
      "-SkipCli" not in win_job and "check_brains.py" in win_job)
check("CI runs the macOS first-run path and checks all four brains",
      "packaging/macos/bootstrap.sh" in mac_job and "check_brains.py" in mac_job)
check("macOS launcher has a fallback when Terminal automation is denied",
      "if ! osascript" in launcher and "pbcopy" in launcher and "printf 'JAVIS_HOME=%q bash %q" in launcher)

# ---- no black window, nothing that can wait forever (2026-11-11) ----
# The owner's screenshot: wizard at 100%, nothing moving, the console that held the answer
# hidden behind it. The bootstrap now runs hidden and the wizard shows its lines.
code = iss.split("[Code]", 1)[1]
boot_exec = code.split("procedure CurStepChanged", 1)[1].split("procedure CurPageChanged", 1)[0]
check("CANARY: the wizard runs bootstrap.ps1 hidden and reads its output (no separate console)",
      "ExecAndLogOutput(PowerShellExe, args" in boot_exec and "@BootLine" in boot_exec)
check("CANARY: the hidden bootstrap gets -NoPause (nobody can press Enter in it)",
      "-NoPause'" in boot_exec and "Read-Host" in boot and "if (-not $NoPause) { Read-Host" in boot)
check("the wizard shows the lines in a box on the Installing page",
      "BootMemo.Parent := WizardForm.InstallingPage" in code and "BootMemo.Lines.Add(" in code)
check("the bar keeps moving while the bootstrap runs (it used to sit at 100%)",
      "ProgressGauge.Style := npbstMarquee" in boot_exec and "ProgressGauge.Style := npbstNormal" in boot_exec)
check("the wizard keeps the log on disk and names it when the bootstrap fails",
      "SaveStringsToUTF8File(BootLogFile" in code and "[why, BootLogFile]" in boot_exec)
check("no wizard text still sends people to a black window",
      "black window" not in iss.split("[CustomMessages]")[1].split("[Tasks]")[0]
      and "cửa sổ đen" not in iss.split("[CustomMessages]")[1].split("[Tasks]")[0])
step_keys = ("StepGit", "StepClone", "StepPython", "StepLibs", "StepBrains", "StepFinish", "Bootstrapping",
             "BootstrapFailed", "BootstrapNoDetail", "NotFinishedTitle", "NotFinishedText")
check("every wizard step line exists in English and Vietnamese",
      all(f"en.{k}=" in iss and f"vi.{k}=" in iss for k in step_keys))
check("the step markers the wizard reads are the ones the scripts print",
      all(f"Pos('[{m}]', U) = 1" in code for m in "AB12345")
      and 'Step "A"' in boot and 'Step "B"' in boot
      and all(f"Step {n} " in install_ps1 for n in (1, 2, 3, 4, 5)))
for name, src in (("bootstrap.ps1", boot), ("install.ps1", install_ps1)):
    live = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    check(f"{name} turns off the PS 5.1 progress bar (10x slower downloads)",
          '$ProgressPreference = "SilentlyContinue"' in src)
    check(f"{name} has Invoke-Capped: waits for one process, with a time cap, and stops its helpers",
          "function Invoke-Capped" in src and "$p.WaitForExit($Minutes * 60000)" in src
          and "taskkill.exe /PID $p.Id /T /F" in src and "$null = $p.Handle" in src)
    check(f"CANARY: {name} never waits with Start-Process -Wait (it also waits for leftover helpers)",
          not any("Start-Process" in ln and re.search(r"-Wait\b", ln) for ln in live),
          [ln for ln in live if "Start-Process" in ln and "-Wait" in ln])
    check(f"CANARY: {name} never pipes winget, npm or the next script into Out-Null / Out-Host "
          "(a pipe waits for every helper process that keeps it open)",
          not any(re.search(r"^\s*(&\s+)?(winget|cmd|powershell)\b.*\|\s*Out-(Null|Host)", ln) for ln in live),
          [ln for ln in live if re.search(r"^\s*(&\s+)?(winget|cmd|powershell)\b.*\|\s*Out-(Null|Host)", ln)])
check("winget installs skip the Microsoft Store source and run quietly under a cap",
      "--id $id --source winget" in install_ps1 and "function Winget-Install" in install_ps1
      and "--source winget" in boot and "-Quiet" in boot)
check("vendor installers answer in plain text, not CLIXML", "-OutputFormat Text -EncodedCommand $enc" in install_ps1)
check("CI runs the real Setup.exe and checks the lines the wizard captured",
      "dist\\JavisOS-Setup.exe -ArgumentList \"/VERYSILENT" in wf and "the wizard wrote no install.log" in wf
      and 'Join-Path $env:USERPROFILE "JavisOS"' in wf)
check("get-javis.ps1 says the rest happens in the Setup window",
      "JAVIS OS Setup" in (PK / "windows" / "get-javis.ps1").read_text(encoding="utf-8"))

# ---- Javis logo in the installers, optional signing (0.439.1) ----
import struct  # noqa: E402


def bmp_info(path):
    """(width, height, bits per pixel) from the BMP header; no Pillow on CI."""
    b = path.read_bytes()[:30]
    if b[:2] != b"BM":
        return None
    w, h = struct.unpack("<ii", b[18:26])
    return w, abs(h), struct.unpack("<H", b[28:30])[0]


for pct in (100, 125, 150, 175, 200, 225, 250):
    for name, base in ((f"wizard-{pct}.bmp", (164, 314)), (f"wizard-small-{pct}.bmp", (55, 55))):
        f = PK / "assets" / name
        want = tuple(round(v * pct / 100) for v in base)
        info = bmp_info(f) if f.exists() else None
        check(f"wizard picture {name} is a 24-bit BMP at {want} (what Inno Setup 6 reads)",
              info == (*want, 24), info)
        check(f"installer lists {name}", f"..\\assets\\{name}" in iss)
check("installer shows the pictures unstretched", "WizardImageStretch=no" in iss)
check("signing is opt-in: SignTool only under #ifdef Sign", "#ifdef Sign\r\nSignTool=javis" in iss_raw.decode("utf-8-sig")
      or "#ifdef Sign\nSignTool=javis" in iss)
check("the uninstaller is signed together with the setup", "SignedUninstaller=yes" in iss)
check("CI signs only with the certificate secrets and checks the signature",
      "secrets.WINDOWS_CERT_PFX_BASE64" in wf and "/DSign" in wf and "Get-AuthenticodeSignature" in wf
      and 'if ($sig.Status -ne "Valid")' in wf)
check("CI never prints the certificate to the log (written to a file, removed after)",
      "WriteAllBytes($pfx" in wf and "Remove-Item $pfx" in wf)
build_dmg = BUILD_DMG.read_text(encoding="utf-8")
check(".dmg mounts with the Javis icon (.VolumeIcon.icns + custom-icon flag)",
      ".VolumeIcon.icns" in build_dmg and "-a C" in build_dmg and "UDRW" in build_dmg)

# ---- one-line installs, no SmartScreen / Gatekeeper block (0.439.1) ----
REL = "https://github.com/blogminhquy/javis-os/releases/download/desktop/"
GET_PS1 = PK / "windows" / "get-javis.ps1"
GET_SH = PK / "macos" / "get-javis.sh"
gps = GET_PS1.read_text(encoding="utf-8")
gsh = GET_SH.read_text(encoding="utf-8")
check("get-javis.ps1 is pure ASCII (piped into Windows PowerShell 5.1)", GET_PS1.read_bytes().isascii())
check("get-javis.ps1 runs inside & { } so `irm | iex` leaves no settings in the person's session",
      gps.split("# ===", 2)[-1].lstrip().split("\n", 1)[-1].lstrip().startswith("& {"))
check("get-javis.ps1 downloads the published setup and opens it",
      REL + "JavisOS-Setup.exe" in gps and "Start-Process -FilePath $out" in gps)
check("get-javis.sh downloads the published .dmg", REL + "JavisOS-macOS.dmg" in gsh)
check("get-javis.sh gives the installer the keyboard back (stdin is the curl pipe)", "< /dev/tty" in gsh)
check("get-javis.sh only replaces the app bundle, never ~/JavisOS (the brain)",
      'rm -rf "${DEST}/JAVIS OS.app"' in gsh and not any("rm -rf" in ln and "JavisOS" in ln and ".app" not in ln
                                                         for ln in gsh.splitlines()))
check("get-javis.sh is executable", os.access(GET_SH, os.X_OK))
raw = "https://raw.githubusercontent.com/blogminhquy/javis-os/main/"
for doc in ("QUICKSTART.md", "QUICKSTART.en.md"):
    d = (ROOT / doc).read_text(encoding="utf-8")
    check(f"{doc} gives the Windows one-liner", f"irm {raw}packaging/windows/get-javis.ps1 | iex" in d)
    check(f"{doc} gives the macOS one-liner", f"curl -fsSL {raw}packaging/macos/get-javis.sh | bash" in d)

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
for f in (LAUNCHER, BOOT_SH, BUILD_DMG, PK / "macos" / "get-javis.sh", ROOT / "install.sh", ROOT / "bin" / "javis-start.sh"):
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
for f in (ISS, BOOT_PS1, OPEN_VBS, LAUNCHER, BOOT_SH, BUILD_DMG, WF, PK / "make_icons.py", PK / "check_brains.py"):
    s = f.read_text(encoding="utf-8-sig")
    check(f"{f.name} has no em/en dash", "—" not in s and "–" not in s)

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All desktop_installer tests passed.")
