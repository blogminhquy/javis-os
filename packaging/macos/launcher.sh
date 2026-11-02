#!/bin/bash
# ============================================================
# JAVIS OS.app (the one inside JavisOS-macOS.dmg) - what a double-click runs.
#
# First run (no Javis in ~/JavisOS yet): opens Terminal on bootstrap.sh, which checks the Mac,
# installs what is missing and starts Javis. Terminal on purpose: the first install takes
# minutes and may ask for the Mac password once, so the person must SEE what happens.
# Every run after that: bin/javis-start.sh, which only opens the window when Javis is already
# up and starts it first when it is not. It never restarts a running server.
#
# Unlike the in-repo "JAVIS OS.app" (which must stay inside the repo folder), this bundle can
# live in /Applications: it finds Javis through JAVIS_HOME, default ~/JavisOS.
# ============================================================
JAVIS_HOME="${JAVIS_HOME:-$HOME/JavisOS}"
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"

if [ -d "${JAVIS_HOME}/.git" ] && [ -x "${JAVIS_HOME}/.venv/bin/python" ] && [ -x "${JAVIS_HOME}/bin/javis-start.sh" ]; then
  exec "${JAVIS_HOME}/bin/javis-start.sh"
fi

osascript - "${RES}/bootstrap.sh" "${JAVIS_HOME}" <<'AS'
on run argv
  tell application "Terminal"
    activate
    do script "JAVIS_HOME=" & quoted form of (item 2 of argv) & " bash " & quoted form of (item 1 of argv)
  end tell
end run
AS
