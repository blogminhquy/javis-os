# ============================================================
# JAVIS OS - what JavisOS-Setup.exe runs after it copies its own few files.
#
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 [-Dir <folder>] [-LogFile <path>]
#
# Steps: make sure Git exists (winget, else the official Git for Windows installer), clone
# Javis into %USERPROFILE%\JavisOS (or reuse the clone already there), then hand over to
# install.ps1 -NoStart, which checks and installs Python, Node, the four CLI brains, the venv,
# .env and the login auto-start. The setup wizard opens the app itself on its last page.
#
# Why a GIT CLONE and not a copy of the files inside the .exe: the Update button in the app
# runs server/updater.py, which updates with git fetch + merge and rolls back with git reset.
# A plain copy would install fine and then never update. A clone also means the .exe never
# goes stale: whoever runs it gets the newest release.
#
# Why %USERPROFILE%\JavisOS and not Program Files: the brain (notes, memory, settings) lives
# inside that folder, so it has to be writable without admin rights, easy to find, and it must
# survive an uninstall.
#
# ASCII only: Windows PowerShell 5.1 reads a file without BOM in the ANSI codepage.
# ============================================================
param(
  [string]$Dir = (Join-Path $env:USERPROFILE "JavisOS"),
  [string]$Repo = "https://github.com/blogminhquy/javis-os.git",
  [string]$Branch = "main",
  [string]$LogFile = "",
  [switch]$SkipCli,   # passed on to install.ps1 (CI smoke test: no third-party CLI installers)
  [switch]$NoPause    # never wait for Enter (CI); the wizard run waits so errors stay readable
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $Host.UI.RawUI.WindowTitle = "JAVIS OS - cai dat" } catch { }
if ($LogFile) { try { Start-Transcript -Path $LogFile -Force | Out-Null } catch { } }

function Line($t) { Write-Host $t }
function Step($n, $t) { Write-Host "" ; Write-Host "[$n] $t" -ForegroundColor Cyan }
function Ok($t) { Write-Host "    OK  $t" -ForegroundColor Green }
function Warn($t) { Write-Host "    [!] $t" -ForegroundColor Yellow }
function Err($t) { Write-Host "    [LOI] $t" -ForegroundColor Red }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Refresh-Path {
  $m = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $u = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:PATH = (@($m, $u) | Where-Object { $_ }) -join ";"
  # Git for Windows installed per user lands here and is not always on PATH yet.
  foreach ($g in @((Join-Path $env:ProgramFiles "Git\cmd"), (Join-Path $env:LOCALAPPDATA "Programs\Git\cmd"))) {
    if ((Test-Path $g) -and ($env:PATH -notlike "*$g*")) { $env:PATH = "$env:PATH;$g" }
  }
}

function Finish($code) {
  if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
  if ($code -ne 0) {
    Line ""
    Err "Cai dat chua xong. Doc cac dong mau do o tren de biet thieu gi."
    if ($LogFile) { Line "    Nhat ky: $LogFile" }
    Line "    Sua xong thi chay lai JavisOS-Setup.exe, cac buoc da xong se duoc bo qua."
    if (-not $NoPause) { Read-Host "Nhan Enter de dong cua so nay" | Out-Null }
  } else {
    Line ""
    Ok "Xong. Lan sau mo Javis bang bieu tuong JAVIS OS tren Desktop hoac Start menu."
    if (-not $NoPause) { Start-Sleep -Seconds 3 }
  }
  exit $code
}

Line ""
Line " =========================================="
Line "  JAVIS OS - kiem tra va cai nhung gi may con thieu"
Line "  Thu muc cai: $Dir"
Line " =========================================="

# ---------------------------------------------------------------- [A] Git
Step "A" "Kiem tra Git (de nut Cap nhat trong app hoat dong)"
Refresh-Path
if (-not (Have "git")) {
  if (Have "winget") {
    Line "    Chua co Git, dang cai bang winget..."
    winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
  }
}
if (-not (Have "git")) {
  # No winget (older Windows 10 without App Installer): the newest official 64-bit installer,
  # silent and per user so it needs no admin rights.
  try {
    Line "    Dang tai Git for Windows..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/git-for-windows/git/releases/latest" -UseBasicParsing -TimeoutSec 60
    $asset = $rel.assets | Where-Object { $_.name -match "^Git-[0-9.]+-64-bit\.exe$" } | Select-Object -First 1
    if ($asset) {
      $out = Join-Path $env:TEMP $asset.name
      Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $out -UseBasicParsing
      Start-Process -FilePath $out -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP- /SUPPRESSMSGBOXES /CURRENTUSER" -Wait
      Refresh-Path
    }
  } catch {
    Warn "Khong tai duoc Git: $($_.Exception.Message)"
  }
}
if (-not (Have "git")) {
  Err "Chua co Git. Cai Git o https://git-scm.com/download/win roi chay lai JavisOS-Setup.exe."
  Finish 1
}
Ok ((git --version) 2>&1)

# ---------------------------------------------------------------- [B] ma nguon
Step "B" "Tai Javis ve may"
if (Test-Path (Join-Path $Dir ".git")) {
  # Re-running the setup (repair, or after a failed step) must not touch an existing clone:
  # it holds the user's brain, and updates go through the Update button.
  Ok "Da co ban Javis o $Dir, giu nguyen (cap nhat bang nut Cap nhat trong app)"
} else {
  if ((Test-Path $Dir) -and (Get-ChildItem -Force $Dir | Select-Object -First 1)) {
    Err "Thu muc $Dir da co file nhung khong phai ban Javis tai bang git."
    Line "    Doi ten hoac chuyen thu muc do di cho khac, roi chay lai JavisOS-Setup.exe."
    Finish 1
  }
  # blob:none = every commit, file contents fetched only when needed. The updater merges and
  # rolls back on this history, which a --depth clone can refuse to do.
  git clone --filter=blob:none --branch $Branch $Repo $Dir
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $Dir "install.ps1"))) {
    Err "Khong tai duoc Javis tu $Repo (kiem tra mang Internet)."
    Finish 1
  }
  Ok "Da tai ve $Dir"
}

# ---------------------------------------------------------------- [C] cai dat
Step "C" "Cai Python, Node, cac bo nao AI va thu vien (vai phut, lan dau lau hon)"
$inst = Join-Path $Dir "install.ps1"
$instArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $inst, "-NoStart")
if ($SkipCli) { $instArgs += "-SkipCli" }
& powershell @instArgs | Out-Host
if ($LASTEXITCODE -ne 0) {
  Err "Buoc cai dat bao loi (ma $LASTEXITCODE)."
  Finish 1
}

Finish 0
