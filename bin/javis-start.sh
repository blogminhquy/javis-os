#!/bin/bash
# ============================================================
# JAVIS OS - macOS launcher (start)
# Starts the FastAPI server (if not already running) and opens
# the dashboard in the default browser. No Docker required.
#
# Paths are resolved from this script's own location, so the repo
# can live anywhere. Run ./install.sh once first to create .venv.
# ============================================================
set -u

# Repo root = parent of this script's directory (bin/)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${JAVIS_PORT:-7777}"
URL="http://127.0.0.1:${PORT}"
LOG="${APP_DIR}/server/javis.log"
PIDF="${APP_DIR}/server/javis.pid"
PY="${APP_DIR}/.venv/bin/python"

# A GUI (Finder/LaunchServices) launch starts with a minimal PATH, so add the
# common CLI locations - the server subprocess needs to find `claude` (the
# brain), plus node/ffmpeg/rg.
export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"
if command -v npm >/dev/null 2>&1; then
  NPM_BIN="$(npm prefix -g 2>/dev/null)/bin"
  [ -d "${NPM_BIN}" ] && export PATH="${NPM_BIN}:${PATH}"
fi

# Already up? Just open it.
if curl -sf -o /dev/null "${URL}/" 2>/dev/null; then
  open "${URL}"
  exit 0
fi

if [ ! -x "${PY}" ]; then
  osascript -e 'display alert "JAVIS OS" message "Chua cai moi truong. Chay ./install.sh trong thu muc du an truoc."' 2>/dev/null || true
  echo "Missing venv at ${PY} - run ./install.sh first." >&2
  exit 1
fi

cd "${APP_DIR}/server" || exit 1
JAVIS_STATE_DIR="${APP_DIR}/server" nohup "${PY}" \
  -m uvicorn main:app --host 127.0.0.1 --port "${PORT}" > "${LOG}" 2>&1 &
echo $! > "${PIDF}"

# Wait until healthy (max ~30s), then open the browser
for _ in $(seq 1 30); do
  sleep 1
  if curl -sf -o /dev/null "${URL}/" 2>/dev/null; then break; fi
done
open "${URL}"
