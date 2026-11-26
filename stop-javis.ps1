# Dung Javis OS - giet theo DUNG python cua venv nay (moi tien trinh cha/con), khong dua vao port/tieu de.
$killed = $false
# LUU Y: python cua venv chi la LAUNCHER - no re-exec Python goc lam tien trinh CON
# (con nay moi giu port). Vi vay chi loc theo COMMANDLINE, KHONG loc theo duong dan exe
# (se bo sot thang con vi exe cua no la Python goc, khong phai venv).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
  $_.CommandLine -like '*server\main.py*'
} | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host "  - Da tat python PID $($_.ProcessId)"
  $killed = $true
}
# Phong ho: ai dang giu port 7777 (truong hop chay bang python khac / cai dat khac)
Get-NetTCPConnection -LocalPort 7777 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
  Write-Host "  - Da tat PID $($_.OwningProcess) (chu port 7777)"
  $killed = $true
}
if (-not $killed) { Write-Host '  (Khong thay server nao dang chay)' }
# Stopped on purpose: tell javis-watchdog.ps1 to leave it down. start-javis.vbs removes this file right
# after its own stop step, so a restart through start-javis.vbs never leaves the watchdog silenced.
$stateDir = $env:JAVIS_STATE_DIR
if (-not $stateDir) { $stateDir = Join-Path $PSScriptRoot "server" }
try { Set-Content -Path (Join-Path $stateDir "stopped-on-purpose") -Value (Get-Date -Format s) -Encoding ASCII -ErrorAction Stop } catch { }
exit 0
