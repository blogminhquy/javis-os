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
# NO WINDOW OF ITS OWN: the wizard runs this file hidden and shows every line it prints inside
# the Setup window (javis-setup.iss, ExecAndLogOutput). So nothing here may wait on the
# keyboard (the wizard passes -NoPause and standard input is empty), and every outside program
# goes through Invoke-Capped, which waits for that one process and gives up after a time cap.
# Before this, an error waited for Enter in a black window hidden behind the wizard, and the
# wizard looked frozen for good.
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
# The Windows PowerShell 5.1 progress bar makes Invoke-WebRequest about 10x slower, which
# turned the Git download (65 MB) into a wait that looked like a hang.
$ProgressPreference = "SilentlyContinue"
# UTF-8 without BOM: the wizard reads these lines as UTF-8, and a BOM would show up as a stray
# character at the start of its log.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }
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

# Runs one outside program and waits for THAT process only, at most $Minutes.
#   - `tool | Out-Null` and `-Wait` also wait for every helper process the tool leaves behind
#     (they hold the output pipe), so one leftover background helper froze the whole setup.
#   - Without a cap, an installer stuck on a question nobody can see never returns.
# -Quiet sends the output to a temp file: winget redraws its progress bar thousands of times.
# Returns the exit code, -1 when the program could not start, -2 when it ran out of time.
function Invoke-Capped {
  param([string]$File, [string]$Arguments, [int]$Minutes = 20, [switch]$Quiet)
  $sp = @{ FilePath = $File; ArgumentList = $Arguments; NoNewWindow = $true; PassThru = $true }
  $tmp = @()
  if ($Quiet) {
    $tmp = @([IO.Path]::GetTempFileName(), [IO.Path]::GetTempFileName())
    $sp.RedirectStandardOutput = $tmp[0]
    $sp.RedirectStandardError = $tmp[1]
  }
  $code = -1
  try {
    $p = Start-Process @sp
    $null = $p.Handle   # PS 5.1 leaves ExitCode empty unless the handle was read before the exit
    if ($p.WaitForExit($Minutes * 60000)) {
      $code = $p.ExitCode
    } else {
      & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
      Warn "Qua $Minutes phut chua xong, da dung buoc nay: $File"
      $code = -2
    }
  } catch {
    Warn "Khong chay duoc $File ($($_.Exception.Message))"
  }
  foreach ($t in $tmp) { Remove-Item $t -Force -ErrorAction SilentlyContinue }
  return $code
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
    Line "    Chua co Git, dang cai bang winget (1-3 phut)..."
    Line "    Neu Windows hien bang hoi quyen thi bam Yes."
    Invoke-Capped -File (Get-Command winget).Source -Quiet -Arguments "install -e --id Git.Git --source winget --accept-source-agreements --accept-package-agreements" | Out-Null
    Refresh-Path
  }
}
if (-not (Have "git")) {
  # No winget (older Windows 10 without App Installer): the newest official 64-bit installer,
  # silent and per user so it needs no admin rights.
  try {
    Line "    Dang tai Git for Windows (khoang 65 MB)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/git-for-windows/git/releases/latest" -UseBasicParsing -TimeoutSec 60
    $asset = $rel.assets | Where-Object { $_.name -match "^Git-[0-9.]+-64-bit\.exe$" } | Select-Object -First 1
    if ($asset) {
      $out = Join-Path $env:TEMP $asset.name
      Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $out -UseBasicParsing
      Line "    Dang cai Git..."
      Invoke-Capped -File $out -Arguments "/VERYSILENT /NORESTART /NOCANCEL /SP- /SUPPRESSMSGBOXES /CURRENTUSER" | Out-Null
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
  Line "    Dang tai ma nguon Javis (1-2 phut)..."
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
$instArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$inst`" -NoStart"
if ($SkipCli) { $instArgs += " -SkipCli" }
# Not `& powershell ... | Out-Host`: a pipeline waits until the last helper process that
# install.ps1 left behind lets go of the pipe. Invoke-Capped waits for install.ps1 itself, and
# its lines still reach the wizard because the child writes to the same output.
$instCode = Invoke-Capped -File (Join-Path $PSHOME "powershell.exe") -Arguments $instArgs -Minutes 120
if ($instCode -ne 0) {
  Err "Buoc cai dat bao loi (ma $instCode)."
  Finish 1
}

Finish 0
