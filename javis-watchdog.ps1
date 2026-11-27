# ============================================================================
# JAVIS OS - watchdog for Windows (the Windows twin of watchdog.sh on the Mac).
# Run it through javis-watchdog.bat; Task Scheduler runs it through javis-watchdog.vbs (hidden window).
#
# Why: 2026-11-26 the server died at 17:37 with no traceback and no crash event, and on Windows
# nothing brought it back: the Run key "JavisOS" only starts Javis at logon. This watchdog asks
# /health every 60 seconds; after JAVIS_WATCHDOG_FAILS (3) misses in a row it runs start-javis.vbs,
# which kills whatever is left (dead or hung) and starts a fresh server.
#
#   javis-watchdog.bat install     register the per-user task "JavisOS Watchdog" (no admin needed)
#   javis-watchdog.bat uninstall   remove the task for good (the server will not register it again)
#   javis-watchdog.bat check       one check (the task calls this; running it by hand is fine)
#   javis-watchdog.bat status      installed or not + current miss count + last log lines
#
# It stays out of the way when:
#   - stop-javis.bat was run on purpose (it leaves server\stopped-on-purpose; start-javis.vbs
#     removes it, and so does this script once /health is green again);
#   - an update is in progress (server\update_state.json in an active phase, younger than 15 min).
#
# Settings from the environment or .env next to this file: JAVIS_PORT (7777),
# JAVIS_STATE_DIR (.\server), JAVIS_WATCHDOG_FAILS (3). Plain ASCII on purpose: Windows
# PowerShell 5.1 reads a BOM-less script in the ANSI code page.
# ============================================================================
param([string]$Action = "status")

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "JavisOS Watchdog"

function Read-DotEnv([string]$Key) {
  $envFile = Join-Path $Root ".env"
  if (-not (Test-Path $envFile)) { return "" }
  $line = Get-Content $envFile -ErrorAction SilentlyContinue |
    Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -Last 1
  if (-not $line) { return "" }
  return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
}

function Get-Setting([string]$Key, [string]$Default) {
  $v = [Environment]::GetEnvironmentVariable($Key)
  if (-not $v) { $v = Read-DotEnv $Key }
  if (-not $v) { $v = $Default }
  return $v
}

$Port = Get-Setting "JAVIS_PORT" "7777"
$StateDir = Get-Setting "JAVIS_STATE_DIR" (Join-Path $Root "server")
$Threshold = [int](Get-Setting "JAVIS_WATCHDOG_FAILS" "3")
$FailFile = Join-Path $StateDir "watchdog-fails"
$StopMarker = Join-Path $StateDir "stopped-on-purpose"
$LogFile = Join-Path $StateDir "watchdog.log"
$OffMarker = Join-Path $StateDir "watchdog-off"
$StartVbs = Join-Path $Root "start-javis.vbs"
$RunnerVbs = Join-Path $Root "javis-watchdog.vbs"
# The restart command lives in a variable so the test can swap it for a harmless one.
$KickCmd = [Environment]::GetEnvironmentVariable("JAVIS_WATCHDOG_KICK_CMD")

function Write-Log([string]$Msg) {
  if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Force -Path $StateDir | Out-Null }
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Msg
  Add-Content -Path $LogFile -Value $line -Encoding UTF8
  Write-Host $line
}

function Get-FailCount {
  try { return [int]((Get-Content $FailFile -ErrorAction Stop | Select-Object -First 1).Trim()) } catch { return 0 }
}

function Set-FailCount([int]$N) {
  if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Force -Path $StateDir | Out-Null }
  Set-Content -Path $FailFile -Value $N -Encoding ASCII
}

function Test-Updating {
  # /health being red DURING an update is expected (the updater handles its own rollback), so a
  # restart here would only break the update. Trust update_state.json only while it is fresh
  # (< 15 minutes): a phase stuck since long ago must not silence the watchdog forever.
  $us = Join-Path $StateDir "update_state.json"
  if (-not (Test-Path $us)) { return $false }
  $item = Get-Item $us
  if ($item.LastWriteTime -lt (Get-Date).AddMinutes(-15)) { return $false }
  $raw = Get-Content $us -Raw -ErrorAction SilentlyContinue
  return [bool]($raw -match '"phase"\s*:\s*"(preparing|pulling|installing|restarting|health_check|rolling_back)"')
}

function Test-Health {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 10
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

function Invoke-Check {
  # The log is appended forever by the task, so trim it.
  if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 1000000)) {
    $tail = Get-Content $LogFile -Tail 1000
    Set-Content -Path $LogFile -Value $tail -Encoding UTF8
  }
  if (Test-Health) {
    if ((Get-FailCount) -ne 0) { Write-Log "/health is green again" }
    Set-FailCount 0
    # The server is up, so whoever stopped it has started it again (maybe not via start-javis.vbs).
    if (Test-Path $StopMarker) { Remove-Item $StopMarker -Force -ErrorAction SilentlyContinue }
    return
  }
  if (Test-Path $StopMarker) {
    # Stopped on purpose with stop-javis.bat: stay quiet until someone starts Javis again.
    Set-FailCount 0
    return
  }
  if (Test-Updating) {
    Write-Log "an update is in progress (update_state.json), skipping this check"
    Set-FailCount 0
    return
  }
  $n = (Get-FailCount) + 1
  Set-FailCount $n
  Write-Log "/health on port $Port did not answer ($n/$Threshold in a row)"
  if ($n -ge $Threshold) {
    Set-FailCount 0
    if ($KickCmd) {
      Write-Log "over the threshold, running: $KickCmd"
      & cmd.exe /c $KickCmd
    } else {
      Write-Log "over the threshold, restarting through start-javis.vbs"
      Start-Process -FilePath "wscript.exe" -ArgumentList @("//nologo", "`"$StartVbs`"") -WindowStyle Hidden
    }
  }
}

switch ($Action.ToLower()) {
  "install" {
    if (-not (Test-Path $RunnerVbs) -or -not (Test-Path $StartVbs)) {
      Write-Host "javis-watchdog.vbs or start-javis.vbs is missing next to this script."
      exit 1
    }
    $act = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$RunnerVbs`""
    # Repeat every minute forever, starting now; plus once at logon so it resumes after a reboot.
    $every = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
      -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    try {
      Register-ScheduledTask -TaskName $TaskName -Action $act -Trigger @($every, $logon) -Settings $set `
        -Description "Restarts Javis OS when http://127.0.0.1:$Port/health stops answering." -Force -ErrorAction Stop | Out-Null
    } catch {
      Write-Host "Could not register the task: $($_.Exception.Message)"
      exit 1
    }
    Set-FailCount 0
    if (Test-Path $OffMarker) { Remove-Item $OffMarker -Force -ErrorAction SilentlyContinue }
    Write-Log "installed: checks /health on port $Port every 60 seconds, $Threshold misses in a row -> start-javis.vbs"
    Write-Host "Log: $LogFile"
  }
  "uninstall" {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    # Removed by hand: the server must not register it again on its next start (server\windows_watchdog.py).
    if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Force -Path $StateDir | Out-Null }
    Set-Content -Path $OffMarker -Value (Get-Date -Format s) -Encoding ASCII
    Write-Host "Watchdog removed ($TaskName). Install it again with: javis-watchdog.bat install"
  }
  "remove" {
    # Autostart was turned off in the dashboard: take the task away without opting out for good.
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  }
  "check" { Invoke-Check }
  default {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) {
      Write-Host "Watchdog is INSTALLED ($($t.State)): checks /health on port $Port every 60 seconds, threshold $Threshold."
    } else {
      Write-Host "Watchdog is NOT installed. Install with: javis-watchdog.bat install"
    }
    if (Test-Path $StopMarker) { Write-Host "Javis was stopped on purpose (stop-javis.bat): the watchdog waits." }
    Write-Host "Misses in a row right now: $(Get-FailCount)"
    if (Test-Path $LogFile) {
      Write-Host "--- last log lines ---"
      Get-Content $LogFile -Tail 5
    }
  }
}
