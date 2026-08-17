#!/bin/bash
# ============================================================
# JAVIS OS - macOS auto-start (LaunchAgent) installer
#   ./bin/javis-autostart.sh install     # start at login (default)
#   ./bin/javis-autostart.sh uninstall    # remove
#
# Generates ~/Library/LaunchAgents/vn.minhquy.javis-os.plist with paths
# computed for THIS machine (nothing hardcoded in the repo).
# ============================================================
set -u

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Nhãn PHẢI khớp mặc định của updater.py/watchdog.sh (com.javis.os): update trên Mac nhận
# diện launchd qua đúng nhãn này để đổi ca bằng kickstart -k; lệch nhãn là updater tưởng
# không có launchd, kill PID + nohup -> KeepAlive respawn giành cổng 7777.
LABEL="${JAVIS_LAUNCHD_LABEL:-com.javis.os}"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PORT="${JAVIS_PORT:-7777}"
PY="${APP_DIR}/.venv/bin/python"
ACTION="${1:-install}"

if [ "${ACTION}" = "uninstall" ]; then
  launchctl unload "${PLIST}" 2>/dev/null || true
  rm -f "${PLIST}"
  echo "JAVIS OS auto-start removed."
  exit 0
fi

if [ ! -x "${PY}" ]; then
  echo "Missing venv at ${PY} - run ./install.sh first." >&2
  exit 1
fi

# Build a PATH that includes the npm global bin (where `claude` lives)
NPM_BIN=""
command -v npm >/dev/null 2>&1 && NPM_BIN="$(npm prefix -g 2>/dev/null)/bin"
PATH_STR="${NPM_BIN}:${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "${HOME}/Library/LaunchAgents"
cat > "${PLIST}" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PY}</string>
        <string>-m</string><string>uvicorn</string><string>main:app</string>
        <string>--host</string><string>127.0.0.1</string>
        <string>--port</string><string>${PORT}</string>
    </array>
    <key>WorkingDirectory</key><string>${APP_DIR}/server</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>JAVIS_STATE_DIR</key><string>${APP_DIR}/server</string>
        <key>PATH</key><string>${PATH_STR}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>${APP_DIR}/server/javis.log</string>
    <key>StandardErrorPath</key><string>${APP_DIR}/server/javis.log</string>
</dict>
</plist>
PLISTEOF

launchctl unload "${PLIST}" 2>/dev/null || true
launchctl load "${PLIST}"
echo "JAVIS OS auto-start installed -> http://127.0.0.1:${PORT}"
echo "Remove with: ./bin/javis-autostart.sh uninstall"
