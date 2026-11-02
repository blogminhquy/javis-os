#!/bin/bash
# ============================================================
# JAVIS OS - first install on a Mac (JAVIS OS.app opens Terminal on this file).
#
#   bash bootstrap.sh            # installs into ~/JavisOS (JAVIS_HOME to change it)
#
# Checks and installs what the Mac lacks, WITHOUT Homebrew (most Macs do not have it):
#   1. Git: Apple's Command Line Tools. macOS shows its own "Install" dialog for them.
#   2. Python >= 3.10: macOS only ships 3.9, so if none is found, uv (astral.sh) downloads a
#      standalone Python 3.12 into the home folder. No admin rights, nothing system wide.
#   3. Clones Javis into ~/JavisOS. A clone, not a copy, because the Update button in the app
#      updates with git (server/updater.py).
#   4. install.sh does the rest: Node (nodejs.org build when there is no brew), the four CLI
#      brains, the venv, .env, the admin account, the login auto-start, then opens Javis.
# Running it again is safe: every step that is already done is skipped.
# ============================================================
set -u

JAVIS_HOME="${JAVIS_HOME:-$HOME/JavisOS}"
REPO="${JAVIS_REPO:-https://github.com/blogminhquy/javis-os.git}"
BRANCH="${JAVIS_BRANCH:-main}"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo ""; echo -e "${CYAN}[$1]${NC} $2"; }
ok()   { echo -e "    ${GREEN}OK${NC}  $*"; }
warn() { echo -e "    ${YELLOW}[!]${NC} $*"; }
fail() {
  echo -e "    ${RED}[LOI]${NC} $*"
  echo ""
  echo "Cai dat chua xong. Sua xong thi mo lai JAVIS OS, cac buoc da xong se duoc bo qua."
  echo "Setup did not finish. Fix the line above, then open JAVIS OS again."
  exit 1
}

export PATH="$HOME/.local/bin:$HOME/.javis/node/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo ""
echo " =========================================="
echo "  JAVIS OS - kiem tra va cai nhung gi may con thieu"
echo "  Thu muc cai: $JAVIS_HOME"
echo " =========================================="

# ---------------------------------------------------------------- [A] git
step A "Git (Command Line Tools cua Apple)"
if ! xcode-select -p >/dev/null 2>&1 || ! git --version >/dev/null 2>&1; then
  warn "May chua co Command Line Tools. macOS se hien hop thoai: bam Install (Cai dat) va cho tai xong."
  warn "This Mac lacks Apple's Command Line Tools. Click Install in the dialog macOS shows."
  xcode-select --install >/dev/null 2>&1 || true
  # Wait for the dialog's download (usually 5 to 15 minutes), at most 45 minutes.
  for _ in $(seq 1 540); do
    if xcode-select -p >/dev/null 2>&1 && git --version >/dev/null 2>&1; then break; fi
    sleep 5
  done
fi
git --version >/dev/null 2>&1 || fail "Chua co Git. Chay: xcode-select --install, cai xong roi mo lai JAVIS OS."
ok "$(git --version)"

# ---------------------------------------------------------------- [B] python
step B "Python 3.10 tro len"
py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' >/dev/null 2>&1; }
have_py() {
  local c
  for c in python3.12 python3.11 python3.13 python3.10 python3; do
    command -v "$c" >/dev/null 2>&1 && py_ok "$c" && return 0
  done
  return 1
}
if ! have_py; then
  warn "Chua co Python 3.10+ (macOS chi kem 3.9). Dang tai Python 3.12 rieng cho Javis (uv)..."
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 || true
  fi
  if command -v uv >/dev/null 2>&1; then
    uv python install 3.12 >/dev/null 2>&1 || true
    # Newer uv already links python3.12 into ~/.local/bin; older ones only print where it is.
    UVPY="$(uv python find 3.12 2>/dev/null || true)"
    if [ -n "$UVPY" ] && [ ! -x "$HOME/.local/bin/python3.12" ]; then
      mkdir -p "$HOME/.local/bin" && ln -sf "$UVPY" "$HOME/.local/bin/python3.12"
    fi
  fi
fi
have_py || fail "Chua cai duoc Python 3.12. Tai o https://www.python.org/downloads/macos/ roi mo lai JAVIS OS."
for c in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && py_ok "$c"; then ok "$("$c" --version) ($(command -v "$c"))"; break; fi
done

# ---------------------------------------------------------------- [C] source
step C "Tai Javis ve may"
if [ -d "$JAVIS_HOME/.git" ]; then
  ok "Da co ban Javis o $JAVIS_HOME, giu nguyen (cap nhat bang nut Cap nhat trong app)"
else
  if [ -e "$JAVIS_HOME" ] && [ -n "$(ls -A "$JAVIS_HOME" 2>/dev/null)" ]; then
    fail "Thu muc $JAVIS_HOME da co file nhung khong phai ban Javis tai bang git. Doi ten no roi mo lai JAVIS OS."
  fi
  # blob:none keeps every commit (the updater merges and rolls back on them) and downloads
  # file contents only when needed.
  git clone --filter=blob:none --branch "$BRANCH" "$REPO" "$JAVIS_HOME" || fail "Khong tai duoc Javis (kiem tra mang Internet)."
  ok "Da tai ve $JAVIS_HOME"
fi

# ---------------------------------------------------------------- [D] install.sh
step D "Cai Node, cac bo nao AI, thu vien va tu khoi dong (vai phut)"
cd "$JAVIS_HOME" || fail "Khong vao duoc $JAVIS_HOME"
bash ./install.sh || fail "install.sh bao loi, doc cac dong phia tren."

echo ""
ok "Xong. Lan sau mo Javis bang JAVIS OS trong Launchpad hoac thu muc Applications."
echo "    Done. Next time, open JAVIS OS from Launchpad or Applications. You can close this window."
