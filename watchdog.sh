#!/usr/bin/env bash
# ============================================================================
# Javis OS - watchdog cho Mac chạy dưới launchd.
#
# Vì sao có file này: vụ treo 14/08/2026. Server SỐNG (vẫn giữ cổng 7777, kernel vẫn nhận
# TCP) nhưng event loop đông cứng - /health không trả lời, SIGTERM bị phớt, phải kill -9.
# KeepAlive của launchd chỉ cứu tiến trình CHẾT, không cứu tiến trình treo. Con chó canh
# này gọi /health mỗi phút; hỏng NGUONG lần liên tiếp thì `launchctl kickstart -k` - launchd
# tự hạ tiến trình cũ (SIGKILL nếu lì) rồi bật bản mới, không cần ai gõ tay lúc 4h sáng.
#
#   ./watchdog.sh install     cài LaunchAgent com.javis.watchdog (chạy check mỗi 60 giây)
#   ./watchdog.sh uninstall   gỡ LaunchAgent
#   ./watchdog.sh check       một nhát kiểm tra (launchd gọi định kỳ; chạy tay cũng được)
#   ./watchdog.sh status      đang cài chưa + đếm hỏng + mấy dòng log cuối
#
# Cấu hình qua env hoặc .env cùng thư mục: JAVIS_PORT (7777), JAVIS_LAUNCHD_LABEL
# (com.javis.os), JAVIS_STATE_DIR (./server), JAVIS_WATCHDOG_FAILS (3).
# ============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# Đọc .env như update.sh: nhiều bản Javis trên một máy thì mỗi bản một cổng/nhãn riêng.
# Env truyền vào thắng .env (`:=` chỉ gán khi biến chưa đặt).
if [ -f .env ]; then
  _env() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env | tail -1; }
  : "${JAVIS_PORT:=$(_env JAVIS_PORT)}"
  : "${JAVIS_LAUNCHD_LABEL:=$(_env JAVIS_LAUNCHD_LABEL)}"
  : "${JAVIS_STATE_DIR:=$(_env JAVIS_STATE_DIR)}"
fi
PORT="${JAVIS_PORT:-7777}"
LABEL="${JAVIS_LAUNCHD_LABEL:-com.javis.os}"
STATE_DIR="${JAVIS_STATE_DIR:-$PWD/server}"
TARGET="gui/$(id -u)/$LABEL"
NGUONG="${JAVIS_WATCHDOG_FAILS:-3}"
DEM_FILE="$STATE_DIR/watchdog-fails"
LOG="$STATE_DIR/watchdog.log"
PLIST="$HOME/Library/LaunchAgents/com.javis.watchdog.plist"
# Lệnh kick tách ra biến để test thay bằng `echo` được - còn lại không ai cần đổi.
KICK_CMD="${JAVIS_WATCHDOG_KICK_CMD:-launchctl kickstart -k $TARGET}"

ghi() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

dang_cap_nhat() {
  # /health đỏ TRONG lúc updater đang chạy là chuyện hợp lệ (updater tự lo rollback) -
  # watchdog kick chen ngang chỉ phá lượt cập nhật. Nhưng chỉ tin update_state.json khi nó
  # còn nóng (<15 phút): phase kẹt từ đời nào không được phép bịt miệng watchdog mãi mãi.
  local us="$STATE_DIR/update_state.json"
  [ -f "$us" ] || return 1
  grep -qE '"phase":[[:space:]]*"(preparing|pulling|installing|restarting|health_check|rolling_back)"' "$us" || return 1
  [ -n "$(find "$us" -mmin -15 2>/dev/null)" ]
}

check() {
  mkdir -p "$STATE_DIR"
  # Log do launchd bơm vào (StandardOutPath) nên tự cắt kẻo phình vô hạn.
  if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 1000000 ]; then
    tail -c 100000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
  if dang_cap_nhat; then
    ghi "đang có lượt cập nhật (update_state.json) - bỏ qua nhát kiểm này"
    echo 0 > "$DEM_FILE"
    return 0
  fi
  if curl -sf -m 10 -o /dev/null "http://127.0.0.1:$PORT/health"; then
    if [ -s "$DEM_FILE" ] && [ "$(cat "$DEM_FILE")" != "0" ]; then
      ghi "/health xanh trở lại"
    fi
    echo 0 > "$DEM_FILE"
    return 0
  fi
  local dem
  dem=$(( $(cat "$DEM_FILE" 2>/dev/null || echo 0) + 1 ))
  echo "$dem" > "$DEM_FILE"
  ghi "/health cổng $PORT KHÔNG trả lời (lần $dem/$NGUONG liên tiếp)"
  if [ "$dem" -ge "$NGUONG" ]; then
    ghi "quá ngưỡng → $KICK_CMD"
    echo 0 > "$DEM_FILE"
    if ! $KICK_CMD; then
      ghi "kick LỖI - job $TARGET có tồn tại không? Soi bằng: launchctl print $TARGET"
    fi
  fi
}

install() {
  if [ "$(uname)" != "Darwin" ]; then
    echo "install chỉ dành cho Mac (launchd). Linux dùng systemd: WatchdogSec / Restart=always."
    exit 1
  fi
  mkdir -p "$HOME/Library/LaunchAgents" "$STATE_DIR"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.javis.watchdog</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>$PWD/watchdog.sh</string>
    <string>check</string>
  </array>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$STATE_DIR/watchdog.log</string>
  <key>StandardErrorPath</key><string>$STATE_DIR/watchdog.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/com.javis.watchdog" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  ghi "đã cài: kiểm /health cổng $PORT mỗi 60 giây, $NGUONG lần hỏng liên tiếp → kickstart $TARGET"
  ghi "log tại: $LOG"
}

uninstall() {
  launchctl bootout "gui/$(id -u)/com.javis.watchdog" 2>/dev/null || true
  rm -f "$PLIST"
  echo "đã gỡ watchdog (com.javis.watchdog)."
}

status() {
  if launchctl print "gui/$(id -u)/com.javis.watchdog" >/dev/null 2>&1; then
    echo "watchdog ĐANG chạy: kiểm /health cổng $PORT mỗi 60 giây, ngưỡng $NGUONG lần → kickstart $TARGET"
  else
    echo "watchdog CHƯA cài. Cài bằng: ./watchdog.sh install"
  fi
  echo "đếm hỏng liên tiếp hiện tại: $(cat "$DEM_FILE" 2>/dev/null || echo 0)"
  if [ -f "$LOG" ]; then
    echo "--- log cuối ---"
    tail -n 5 "$LOG"
  fi
}

case "${1:-status}" in
  install)   install ;;
  uninstall) uninstall ;;
  check)     check ;;
  status)    status ;;
  *) echo "cách dùng: ./watchdog.sh install | uninstall | check | status"; exit 1 ;;
esac
