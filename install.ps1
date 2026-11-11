# ============================================================
# JAVIS OS - CAI MOT LAN TREN WINDOWS
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Cai het trong mot luot: Python deps (venv) + BON bo nao CLI chay bang goi thue bao
# (claude, codex, agy, grok) + .env + giai phong port 7777, roi bat server.
#
# Vi sao co file nay: truoc day nguoi dung Windows phai tu di bon duong khac nhau (setup.bat
# chi cai claude + codex; agy va grok phai tu mo PowerShell go tung lenh cua nha cung cap),
# nen ai khong quen ky thuat thi dung o man Models voi hai the bao "CLI chua cai".
#
# HAI CHO DE SAI, ca hai da xu ly trong file nay:
#   1. `pip install` HONG ma khong ai kiem ma loi -> server bat len roi moi chet vi thieu
#      claude-agent-sdk. Buoc [2] duoi day dung han va noi ro neu pip hong.
#   2. Cai CLI xong ma PATH cua PHIEN HIEN TAI chua co -> buoc tong ket bao "chua cai" cho
#      mot CLI vua cai xong. Refresh-Path doc lai PATH tu registry sau moi lan cai.
#
# QUAN TRONG: Javis doc PATH LUC NO BAT. Cai them CLI sau khi server dang chay thi phai
# khoi dong lai Javis moi thay (stop-javis.bat roi start-javis.vbs).
#
# KHONG DUOC DUNG CHO BAN PHIM: JavisOS-Setup.exe chay file nay AN (khong co cua so den) va
# hien tung dong ngay trong man hinh Setup. Moi chuong trinh ngoai (winget, npm, pip, script
# cai cua nha cung cap) di qua Invoke-Capped: cho dung tien trinh do, co gioi han thoi gian.
#
# KHONG dung ky tu co dau trong file .ps1: PowerShell tren Windows doc file khong BOM bang
# ANSI codepage, chu co dau se thanh rac ngay tren man hinh nguoi dung.
# ============================================================
param(
  [switch]$NoStart,      # cai xong khong tu bat server
  [switch]$NoAutostart,  # khong bat tu khoi dong cung Windows (mac dinh BAT tu 0.306.0)
  [switch]$SkipCli       # bo qua buoc cai 4 CLI (chi cai Python deps)
)

$ErrorActionPreference = "Continue"
# The Windows PowerShell 5.1 progress bar makes Invoke-WebRequest about 10x slower: the Python
# and Node downloads below looked like a hang on machines without winget.
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Line($t) { Write-Host $t }
function Step($n, $t) { Write-Host "" ; Write-Host "[$n] $t" -ForegroundColor Cyan }
function Ok($t) { Write-Host "    OK  $t" -ForegroundColor Green }
function Warn($t) { Write-Host "    [!] $t" -ForegroundColor Yellow }
function Err($t) { Write-Host "    [LOI] $t" -ForegroundColor Red }

# PATH cua phien hien tai KHONG tu cap nhat sau khi mot installer ghi vao registry. Doc lai
# ca Machine + User de buoc tong ket noi dung su that, va de `npm` vua cai bang winget dung
# duoc ngay trong cung mot luot chay.
function Refresh-Path {
  $m = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $u = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:PATH = (@($m, $u) | Where-Object { $_ }) -join ";"
  # Where the vendor installers drop agy and grok when they do not (or not yet) write PATH.
  # The server searches the same folders (antigravity_cli.py, grok_cli.py), so the summary
  # below should not call a CLI "missing" that Javis will find anyway.
  foreach ($d in @((Join-Path $env:USERPROFILE ".local\bin"),
                   (Join-Path $env:LOCALAPPDATA "agy\bin"),
                   (Join-Path $env:LOCALAPPDATA "Programs\antigravity"),
                   (Join-Path $env:LOCALAPPDATA "Programs\grok"),
                   (Join-Path $env:USERPROFILE ".grok\bin"),
                   (Join-Path $env:APPDATA "npm"))) {
    if ((Test-Path $d) -and ($env:PATH -notlike "*$d*")) { $env:PATH = "$env:PATH;$d" }
  }
}

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# Runs one outside program and waits for THAT process only, at most $Minutes.
#   - `tool | Out-Null` and `-Wait` also wait for every helper process the tool leaves behind
#     (they hold the output pipe), so one leftover background helper froze the whole install.
#   - Without a cap, an installer stuck on a question nobody can see never returns.
#   - The program writes straight to the screen (or to the Setup window), so its lines show
#     up live and its warnings are not dressed up as red PowerShell errors.
# -Quiet sends the output to a temp file: winget redraws its progress bar thousands of times.
# Returns the exit code, -1 when the program could not start, -2 when it ran out of time.
# The same function lives in packaging/windows/bootstrap.ps1 (that file runs before the clone).
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

function Winget-Install($id, $extra) {
  Line "    Neu Windows hien bang hoi quyen thi bam Yes."
  # --source winget: without it winget also searches the Microsoft Store source, which fails
  # or asks to accept its terms on a PC that never opened the Store.
  $a = "install -e --id $id --source winget --accept-source-agreements --accept-package-agreements"
  if ($extra) { $a = "$a $extra" }
  Invoke-Capped -File (Get-Command winget).Source -Arguments $a -Quiet | Out-Null
  Refresh-Path
}

Line ""
Line " =========================================="
Line "  JAVIS OS - cai dat tren Windows"
Line " =========================================="

# ---------------------------------------------------------------- [1] Python
# A fresh Windows 10/11 already answers to `python`: it is the Microsoft Store alias in
# %LOCALAPPDATA%\Microsoft\WindowsApps, which opens the Store instead of running anything. The
# old `Have "python"` check took that stub for a real interpreter, so `python -m venv` died two
# lines later. Every candidate below is RUN with a version probe before it is trusted.
$script:PyExe = $null
$script:PyArgs = @()
function Test-Py($exe, $pre) {
  try {
    & $exe @pre -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}
function Find-Python {
  $cands = @(
    @{ exe = "py"; pre = @("-3.12") },
    @{ exe = "py"; pre = @("-3.11") },
    @{ exe = "py"; pre = @("-3") },
    @{ exe = "python"; pre = @() },
    @{ exe = (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"); pre = @() },
    @{ exe = (Join-Path $env:ProgramFiles "Python312\python.exe"); pre = @() }
  )
  foreach ($c in $cands) {
    if (-not (Get-Command $c.exe -ErrorAction SilentlyContinue)) { continue }
    if (Test-Py $c.exe $c.pre) { $script:PyExe = $c.exe; $script:PyArgs = $c.pre; return $true }
  }
  return $false
}

Step 1 "Kiem tra Python"
if (-not (Find-Python)) {
  if (Have "winget") {
    Line "    Chua co Python, dang cai bang winget (1-3 phut)..."
    Winget-Install "Python.Python.3.12" "--scope user"
  }
}
if (-not (Find-Python)) {
  # No winget (older Windows 10 without App Installer) or winget failed: the official per-user
  # installer needs no admin rights and puts python on the user PATH.
  try {
    Line "    Dang tai Python 3.12 tu python.org (khoang 27 MB)..."
    $pyInst = Join-Path $env:TEMP "python-3.12-amd64.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $pyInst -UseBasicParsing
    Line "    Dang cai Python..."
    Invoke-Capped -File $pyInst -Arguments "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1" | Out-Null
    Refresh-Path
  } catch {
    Warn "Khong tai duoc Python: $($_.Exception.Message)"
  }
}
if (-not (Find-Python)) {
  Err "Chua co Python. Tai Python 3.12 o python.org, tick 'Add python.exe to PATH', roi chay lai file nay."
  exit 1
}
$pyv = (& $script:PyExe @script:PyArgs --version 2>&1)
Ok "$pyv"

# ---------------------------------------------------------------- [2] venv + deps
Step 2 "Cai thu vien Python (venv)"
if (-not (Test-Path ".venv")) {
  & $script:PyExe @script:PyArgs -m venv .venv
  if ($LASTEXITCODE -ne 0) { Err "Khong tao duoc .venv"; exit 1 }
}
$vpy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { Err "Thieu .venv\Scripts\python.exe - xoa thu muc .venv roi chay lai."; exit 1 }
Line "    Dang tai va cai thu vien, buoc nay lau nhat (2-5 phut)..."
Invoke-Capped -File $vpy -Arguments "-m pip install --upgrade pip -q --disable-pip-version-check" -Minutes 15 | Out-Null
$pipCode = Invoke-Capped -File $vpy -Arguments "-m pip install -r requirements.txt --disable-pip-version-check" -Minutes 60
if ($pipCode -ne 0) {
  Err "pip install THAT BAI. Server se bao 'thieu claude-agent-sdk' neu bo qua buoc nay."
  Line "    Thu lai: .venv\Scripts\python.exe -m pip install -r requirements.txt"
  Line "    Hay gap loi UnicodeDecodeError thi may dang thieu Visual C++ Build Tools / mang chan pypi."
  exit 1
}
Ok "Da cai xong thu vien (gom claude-agent-sdk)"

# ---------------------------------------------------------------- [3] Node + 4 CLI
if ($SkipCli) {
  Step 3 "Bo qua buoc cai CLI (-SkipCli)"
} else {
  Step 3 "Cai 4 bo nao CLI (chay bang goi thue bao, khong can mua API key)"
  if (-not (Have "npm")) {
    if (Have "winget") {
      Line "    Chua co Node.js, dang cai bang winget (1-3 phut)..."
      Winget-Install "OpenJS.NodeJS.LTS" ""
    }
  }
  if (-not (Have "npm")) {
    # No winget: take the current 22 LTS MSI straight from nodejs.org. The file name carries
    # the patch number, so read it from SHASUMS256.txt instead of hardcoding one that goes stale.
    try {
      Line "    Dang tai Node.js 22 LTS tu nodejs.org (khoang 30 MB)..."
      $base = "https://nodejs.org/dist/latest-v22.x/"
      $sums = (Invoke-WebRequest -Uri ($base + "SHASUMS256.txt") -UseBasicParsing).Content
      $msi = ([regex]::Match($sums, "node-v22\.[0-9]+\.[0-9]+-x64\.msi")).Value
      if ($msi) {
        $out = Join-Path $env:TEMP $msi
        Invoke-WebRequest -Uri ($base + $msi) -OutFile $out -UseBasicParsing
        Line "    Dang cai Node.js (neu Windows hoi quyen thi bam Yes)..."
        Invoke-Capped -File "msiexec.exe" -Arguments "/i `"$out`" /passive /norestart" | Out-Null
        Refresh-Path
      }
    } catch {
      Warn "Khong tai duoc Node.js: $($_.Exception.Message)"
    }
  }
  if (Have "npm") {
    foreach ($it in @(
      @{ pkg = "@anthropic-ai/claude-code"; bin = "claude"; ten = "Claude Code" },
      @{ pkg = "@openai/codex"; bin = "codex"; ten = "Codex - goi ChatGPT" }
    )) {
      if (Have $it.bin) { Ok "$($it.ten): da co san"; continue }
      Line "    $($it.ten): dang cai (npm install -g $($it.pkg))..."
      Invoke-Capped -File $env:ComSpec -Arguments "/d /c npm install -g $($it.pkg)" -Minutes 15 | Out-Null
      Refresh-Path
      if (Have $it.bin) { Ok "$($it.ten)" } else { Warn "$($it.ten) cai chua duoc. Cai tay: npm install -g $($it.pkg)" }
    }
  } else {
    Warn "Chua co Node.js nen bo qua Claude Code + Codex. Cai Node LTS o nodejs.org roi chay lai file nay."
  }

  # agy va grok KHONG cai bang npm: moi nha mot script cai rieng. Best-effort tung cai -
  # mot cai hong khong duoc chan ba cai con lai.
  foreach ($it in @(
    @{ bin = "agy"; ten = "Antigravity CLI (Google)"; url = "https://antigravity.google/cli/install.ps1" },
    @{ bin = "grok"; ten = "Grok Build (xAI)"; url = "https://x.ai/cli/install.ps1" }
  )) {
    if (Have $it.bin) { Ok "$($it.ten): da co san"; continue }
    Line "    $($it.ten): dang cai tu $($it.url) ..."
    try {
      # In a CHILD PowerShell, not Invoke-Expression here: a vendor script that ends with
      # `exit` would otherwise end THIS script too, and Python deps, .env and auto-start
      # (the steps below) would silently never run. Invoke-Capped stops it after 10 minutes,
      # helper processes included, so a script that waits on a prompt cannot hang the install.
      $cmd = "`$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm '$($it.url)' | iex"
      # -EncodedCommand: Start-Process joins its arguments without quoting, so a plain
      # -Command string with spaces, quotes and a pipe would reach the child mangled.
      $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
      # -OutputFormat Text: with -EncodedCommand a child PowerShell answers in CLIXML, which put
      # "#< CLIXML" and one 400,000 character line of XML on the screen.
      Invoke-Capped -File (Join-Path $PSHOME "powershell.exe") -Arguments "-NoProfile -ExecutionPolicy Bypass -OutputFormat Text -EncodedCommand $enc" -Minutes 10 | Out-Null
      Refresh-Path
      if (Have $it.bin) { Ok "$($it.ten)" } else { Warn "$($it.ten): script chay xong nhung chua thay binary. Mo PowerShell moi roi thu: irm $($it.url) | iex" }
    } catch {
      Warn "$($it.ten) cai chua duoc ($($_.Exception.Message)). Cai tay: irm $($it.url) | iex"
    }
  }
}

# ---------------------------------------------------------------- [4] .env
Step 4 "Kiem tra .env"
if ((-not (Test-Path ".env")) -and (Test-Path "env.example")) {
  Copy-Item "env.example" ".env"
  Ok "Da tao .env tu env.example"
} else {
  Ok ".env da co"
}

# ---------------------------------------------------------------- [5] port 7777
Step 5 "Giai phong port 7777"
$conns = Get-NetTCPConnection -LocalPort 7777 -State Listen -ErrorAction SilentlyContinue
if ($conns) {
  foreach ($c in $conns) {
    try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop; Ok "Da tat tien trinh cu PID $($c.OwningProcess)" }
    catch { Warn "Khong tat duoc PID $($c.OwningProcess) - dong tay roi chay lai." }
  }
} else {
  Ok "Port 7777 dang trong"
}

# ---------------------------------------------------------------- tong ket
Refresh-Path
Line ""
Line " =========================================="
Line "  BO NAO SAN SANG (chon o trang Models)"
Line " =========================================="
foreach ($it in @(
  @{ bin = "claude"; ten = "Claude Code    " },
  @{ bin = "codex"; ten = "Codex (ChatGPT)" },
  @{ bin = "agy"; ten = "Antigravity CLI" },
  @{ bin = "grok"; ten = "Grok Build     " }
)) {
  if (Have $it.bin) {
    $p = (Get-Command $it.bin).Source
    Write-Host "  [x] $($it.ten)  $p" -ForegroundColor Green
  } else {
    Write-Host "  [ ] $($it.ten)  chua cai" -ForegroundColor Yellow
  }
}
Line ""
Line "  Dang nhap tung bo nao NGAY TRONG trang Models cua dashboard - khong can go lenh."
Line "  Cai them CLI sau nay thi phai KHOI DONG LAI Javis (stop-javis.bat roi start-javis.vbs),"
Line "  vi tien trinh dang chay giu PATH cua luc no bat."
Line ""

# ---------------------------------------------------------------- [5b] tu khoi dong
# 0.306.0, chu repo 24/10/2026: "mac dinh cai javis tren win hoac mac thi cai khoi dong cung trinh duyet".
# Dang nhap may la Javis tu chay nen roi tu mo dashboard. Tat: -NoAutostart, javis-autostart.bat uninstall,
# hoac nut trong trang Cai dat.
if (-not $NoAutostart) {
  $as = Join-Path $Root "javis-autostart.ps1"
  if (Test-Path $as) {
    $asCode = Invoke-Capped -File (Join-Path $PSHOME "powershell.exe") -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$as`" install" -Minutes 2 -Quiet
    if ($asCode -eq 0) { Ok "Tu khoi dong cung Windows: BAT (dang nhap may la Javis tu mo)" }
    else { Warn "Chua bat duoc tu khoi dong. Bat sau: javis-autostart.bat install" }
  }
}

# ---------------------------------------------------------------- [6] bat server
if ($NoStart) {
  Line "  Cai xong. Bat server: start-javis.vbs (chay nen) hoac setup.bat (hien cua so)."
  exit 0
}
Step 6 "Bat Javis"
$vbs = Join-Path $Root "start-javis.vbs"
if (Test-Path $vbs) {
  # /open: cho server len roi mo dashboard luon (0.306.0).
  Start-Process "wscript.exe" -ArgumentList "//nologo `"$vbs`" /open" -WorkingDirectory $Root
  Ok "Server dang chay nen, dashboard se tu mo. Log: server\javis.log"
} else {
  Start-Process $vpy -ArgumentList "main.py" -WorkingDirectory (Join-Path $Root "server")
  Ok "Server dang chay"
}
Line ""
Line "  Mo: http://localhost:7777"
Line ""
