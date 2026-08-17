#!/bin/bash
# ============================================================
# JAVIS OS - macOS launcher (stop)
# ============================================================
set -u

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDF="${APP_DIR}/server/javis.pid"
PORT="${JAVIS_PORT:-7777}"

if [ -f "${PIDF}" ]; then
  kill "$(cat "${PIDF}")" 2>/dev/null
  rm -f "${PIDF}"
fi
# Fallback: kill whatever holds the port
lsof -ti "tcp:${PORT}" 2>/dev/null | xargs kill 2>/dev/null || true
echo "JAVIS OS stopped."
