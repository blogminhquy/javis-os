#!/usr/bin/env bash
# ============================================================================
# Javis OS - Linux/macOS native installer (no Docker)
#   ./install.sh
# Installs python3 + node + Claude Code CLI, creates a venv, installs deps,
# seeds .env, and registers a systemd service (or falls back to nohup).
# ============================================================================
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${CYAN}->${NC} $*"; }
ok()   { echo -e "${GREEN}OK${NC} $*"; }
warn() { echo -e "${YELLOW}!!${NC} $*"; }
err()  { echo -e "${RED}xx${NC} $*" >&2; }

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"

# --- 1. python3 >= 3.10 + venv + pip ---
# HARD FLOOR 3.10: uvicorn pinned in requirements.txt needs >=3.10 (every release from
# 0.40 up dropped 3.9). Do NOT trust a bare `python3` here - macOS ships /usr/bin/python3
# = 3.9 and it sits AHEAD of Homebrew in PATH, so the old code happily printed
# "OK Python 3.9.6" and then died 40 lines later with the useless pip error
# "No matching distribution found for uvicorn==0.51.0". Probe for a real interpreter.
PY_MIN="3.10"
py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' >/dev/null 2>&1; }

PYTHON_BIN=""
find_python() {
  local c d
  # NOT newest-first. requirements.txt pins hard (fastapi 0.115.0, cryptography, uvloop,
  # watchfiles, pydantic-core - all need compiled wheels), so prefer the versions with the
  # widest wheel coverage and fall back to a bleeding-edge interpreter only if nothing else
  # exists: on a brand-new 3.x, pip finds no wheel and tries to BUILD from source, which
  # fails on any machine without a compiler toolchain. 3.11/3.12 is the verified sweet spot.
  for c in python3.12 python3.11 python3.13 python3.10 python3 python3.14 python; do
    if py_ok "$c"; then PYTHON_BIN="$(command -v "$c")"; return 0; fi
  done
  # Homebrew python is keg-only on some setups (never linked into PATH); look directly.
  # Same preference order, explicit rather than a glob (a glob sorts 3.10 ahead of 3.12).
  for d in /opt/homebrew/bin /usr/local/bin; do
    for c in python3.12 python3.11 python3.13 python3.10 python3.14; do
      if py_ok "$d/$c"; then PYTHON_BIN="$d/$c"; return 0; fi
    done
  done
  return 1
}

log "Checking Python >= $PY_MIN..."
if ! find_python; then
  log "No Python >= $PY_MIN found - installing..."
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -qq && $SUDO apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then $SUDO dnf install -y python3 python3-pip
  elif command -v brew >/dev/null 2>&1; then brew install python
  else err "Install Python $PY_MIN or newer manually, then re-run."; exit 1; fi
  find_python || {
    err "Still no Python >= $PY_MIN after install (found: $(python3 --version 2>&1 || echo none))."
    err "Install it manually (macOS: brew install python), then re-run."
    exit 1
  }
fi
"$PYTHON_BIN" -m venv --help >/dev/null 2>&1 || { command -v apt-get >/dev/null 2>&1 && $SUDO apt-get install -y python3-venv; }
ok "$("$PYTHON_BIN" --version) ($PYTHON_BIN)"

# --- 2. system deps: git, ripgrep, ffmpeg (best-effort) ---
log "Installing system deps (git, ripgrep, ffmpeg)..."
if command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get install -y git ripgrep ffmpeg curl >/dev/null 2>&1 || warn "some deps skipped"
elif command -v dnf >/dev/null 2>&1; then
  $SUDO dnf install -y git ripgrep ffmpeg curl >/dev/null 2>&1 || warn "some deps skipped"
elif command -v brew >/dev/null 2>&1; then
  brew install git ripgrep ffmpeg >/dev/null 2>&1 || warn "some deps skipped"
fi

# --- 3. Node.js 22 LTS (system pkg -> nodejs.org tarball fallback) ---
need_node() { ! command -v node >/dev/null 2>&1 || [ "$(node -v | sed 's/v//;s/\..*//')" -lt 20 ]; }
if need_node; then
  log "Installing Node.js 22 LTS..."
  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO -E bash - >/dev/null 2>&1 && $SUDO apt-get install -y nodejs || true
  elif command -v brew >/dev/null 2>&1; then brew install node@22 || true; fi
  if need_node; then
    arch=$(uname -m); case "$arch" in x86_64) na=x64;; aarch64|arm64) na=arm64;; *) err "unsupported arch $arch"; exit 1;; esac
    tb=$(curl -fsSL https://nodejs.org/dist/latest-v22.x/ | grep -oE "node-v22\.[0-9]+\.[0-9]+-linux-${na}\.tar\.xz" | head -1)
    tmp=$(mktemp -d); curl -fsSL "https://nodejs.org/dist/latest-v22.x/${tb}" -o "$tmp/n.tar.xz"
    mkdir -p "$HOME/.javis"; rm -rf "$HOME/.javis/node"
    tar xf "$tmp/n.tar.xz" -C "$tmp"; mv "$tmp"/node-v22* "$HOME/.javis/node"; rm -rf "$tmp"
    mkdir -p "$HOME/.local/bin"
    ln -sf "$HOME/.javis/node/bin/node" "$HOME/.local/bin/node"
    ln -sf "$HOME/.javis/node/bin/npm"  "$HOME/.local/bin/npm"
    ln -sf "$HOME/.javis/node/bin/npx"  "$HOME/.local/bin/npx"
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi
ok "Node $(node -v)"

# --- 4. Claude Code CLI (the brain) ---
if ! command -v claude >/dev/null 2>&1; then
  log "Installing Claude Code CLI globally via npm..."
  if ! npm install -g @anthropic-ai/claude-code >/dev/null 2>&1; then
    warn "global npm install needs sudo; retrying..."
    $SUDO npm install -g @anthropic-ai/claude-code
  fi
fi
ok "Claude CLI $(claude --version 2>/dev/null || echo installed)"

# --- 5. venv + python deps ---
log "Creating virtualenv (.venv)..."
# A .venv left over from a failed run can be built on 3.9 - reusing it reproduces the
# exact uvicorn resolve error the probe above exists to prevent. Rebuild instead.
if [ -d .venv ] && ! py_ok ./.venv/bin/python; then
  warn ".venv runs $(./.venv/bin/python --version 2>&1 || echo 'an unusable Python') - rebuilding with $PYTHON_BIN"
  rm -rf .venv
fi
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
./.venv/bin/pip install --upgrade pip -q
./.venv/bin/pip install -r requirements.txt -q
ok "Python deps installed"

# --- 6. .env (chmod 600 - holds tokens) ---
if [ ! -f .env ]; then cp env.example .env; chmod 600 .env; ok "Created .env from template"; else chmod 600 .env 2>/dev/null || true; ok ".env exists"; fi

# --- 7. minimal config prompt ---
if [ -t 0 ]; then
  read -rp "Vault path [blank = in-repo vault/]: " VP || true
  if [ -n "${VP:-}" ]; then
    if grep -q '^OBSIDIAN_VAULT_PATH=' .env; then sed -i.bak "s|^OBSIDIAN_VAULT_PATH=.*|OBSIDIAN_VAULT_PATH=$VP|" .env && rm -f .env.bak; else echo "OBSIDIAN_VAULT_PATH=$VP" >> .env; fi
  fi
fi
grep -q '^JAVIS_HOST=' .env || echo "JAVIS_HOST=127.0.0.1" >> .env

# --- 8. one-time Claude auth reminder ---
if ! claude auth status >/dev/null 2>&1; then
  warn "Claude CLI is not logged in. Run this ONCE (opens a browser-login URL):"
  echo "      claude auth login --claudeai"
fi

# --- 9. service: systemd if available, else nohup ---
PY="$APP_DIR/.venv/bin/python"
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  log "Installing systemd service..."
  $SUDO tee /etc/systemd/system/javis.service >/dev/null <<UNIT
[Unit]
Description=Javis OS
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$APP_DIR/server
Environment="JAVIS_HOST=127.0.0.1"
Environment="JAVIS_PORT=7777"
Environment="JAVIS_STATE_DIR=$APP_DIR/server"
Environment="PATH=$APP_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PY -m uvicorn main:app --host 127.0.0.1 --port 7777
Restart=always
RestartSec=5
KillSignal=SIGTERM
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now javis.service
  ok "Service installed. Logs: journalctl -u javis -f"
else
  warn "systemd not available - starting under nohup..."
  ( cd "$APP_DIR/server" && JAVIS_STATE_DIR="$APP_DIR/server" nohup "$PY" -m uvicorn main:app --host 127.0.0.1 --port 7777 > "$APP_DIR/server/javis.log" 2>&1 & )
  ok "Started. Logs: $APP_DIR/server/javis.log"
fi

echo ""
ok "Javis OS is up at: http://127.0.0.1:7777"
log "Remote access (SSH tunnel): ssh -L 7777:localhost:7777 $(whoami)@<vps-ip>"
echo ""
log "Truy cập từ xa qua Cloudflare Tunnel (không cần mở port, có HTTPS):"
echo "    1) Đặt MẬT KHẨU trong Dashboard → Tài khoản TRƯỚC (Claude chạy full quyền!)."
if command -v cloudflared >/dev/null 2>&1; then
  echo "    2) cloudflared tunnel --url http://localhost:7777   → mở URL https://<random>.trycloudflare.com"
else
  echo "    2) Cài cloudflared:  curl -fsSL https://pkg.cloudflare.com/cloudflared.deb -o /tmp/cf.deb && $SUDO dpkg -i /tmp/cf.deb"
  echo "       Rồi:  cloudflared tunnel --url http://localhost:7777"
fi
