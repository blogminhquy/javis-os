#!/usr/bin/env bash
# ============================================================================
# Javis OS - cập nhật lên bản mới nhất từ GitHub.
#   ./update.sh            (tự nhận Docker hay native)
#   ./update.sh docker     (ép chế độ Docker)
#   ./update.sh native     (ép chế độ native/systemd)
# ============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
MODE="${1:-auto}"
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"

# Tên bản Javis Ở THƯ MỤC NÀY. Nhiều bản trên cùng VPS thì mỗi bản một .env riêng; không đọc
# .env ở đây thì `./update.sh` của bản này đi restart container/dịch vụ của bản khác.
if [ -z "${JAVIS_NAME:-}" ] && [ -f .env ]; then
  JAVIS_NAME="$(sed -n 's/^[[:space:]]*JAVIS_NAME[[:space:]]*=[[:space:]]*//p' .env | tail -1)"
fi
NAME="${JAVIS_NAME:-javis}"

echo "==> Kéo code mới từ GitHub..."
git pull --ff-only

is_docker() {
  command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ] && \
  docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$NAME"
}

if [ "$MODE" = "docker" ] || { [ "$MODE" = "auto" ] && is_docker; }; then
  echo "==> Docker → pull image mới từ GHCR + restart..."
  # Đang bật HTTPS (Caddy)? Giữ nguyên override để cập nhật KHÔNG gỡ mất Caddy.
  HTTPS_ARGS=""
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$NAME-caddy"; then
    HTTPS_ARGS="-f docker-compose.yml -f docker-compose.https.yml"
    echo "==> Phát hiện Caddy (HTTPS) → giữ nguyên cấu hình HTTPS khi cập nhật."
  fi
  # Đứng sau proxy dùng chung (nhiều bản, mỗi bản một tên miền) thì giữ luôn override multi,
  # không thì lượt cập nhật này gỡ mất nhãn Caddy và bản đó rơi khỏi proxy.
  if [ -f docker-compose.multi.yml ] && docker network inspect javis-web >/dev/null 2>&1; then
    HTTPS_ARGS="-f docker-compose.yml -f docker-compose.multi.yml"
    echo "==> Phát hiện proxy dùng chung (javis-web) → giữ nguyên cấu hình nhiều bản."
  fi
  docker compose $HTTPS_ARGS pull
  docker compose $HTTPS_ARGS up -d
  echo "==> Xong. Theo dõi:  docker compose logs -f"
else
  echo "==> Native → cập nhật thư viện Python + restart dịch vụ..."
  [ -d .venv ] && ./.venv/bin/pip install -r requirements.txt -q || true
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q "^$NAME\.service"; then
    $SUDO systemctl restart "$NAME"
    echo "==> Đã restart. Theo dõi:  journalctl -u $NAME -f"
  elif [ "$(uname)" = "Darwin" ] && \
       launchctl print "gui/$(id -u)/${JAVIS_LAUNCHD_LABEL:-com.javis.os}" >/dev/null 2>&1; then
    # Mac chạy dưới launchd (KeepAlive): kill PID rồi tự chạy nohup là đua bind cổng với bản
    # launchd respawn ([Errno 48], vụ 14/08/2026). Để launchd tự đổi ca bằng kickstart -k.
    TARGET="gui/$(id -u)/${JAVIS_LAUNCHD_LABEL:-com.javis.os}"
    echo "==> Phát hiện launchd ($TARGET) → kickstart -k..."
    launchctl kickstart -k "$TARGET"
    echo "==> Đã yêu cầu launchd khởi động lại. Theo dõi: server/javis.log"
  else
    # Mac / Linux không systemd: kill tiến trình đang giữ cổng rồi chạy lại nền (như install.sh)
    PORT="${JAVIS_PORT:-7777}"
    PIDS="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
    if [ -n "$PIDS" ]; then
      echo "==> Dừng tiến trình cũ (PID: $PIDS)..."
      kill $PIDS 2>/dev/null || true
      sleep 2
    fi
    ( cd server && JAVIS_STATE_DIR="$PWD" nohup ../.venv/bin/python -m uvicorn main:app \
        --host "${JAVIS_HOST:-127.0.0.1}" --port "$PORT" > javis.log 2>&1 & )
    echo "==> Đã khởi động lại (nohup). Logs: server/javis.log"
  fi
fi
