#!/bin/sh
# Entrypoint container: DỜI các thư mục HOME mà CLI ngoài ghi vào sang volume /data
# rồi mới chạy lệnh chính (uvicorn).
#
# Vì sao tồn tại (báo cáo 16/08): Antigravity CLI (`agy`) do người dùng tự cài vào
# ~/.local/bin và giữ đăng nhập trong ~/.antigravity / ~/.config / ~/.gemini - tất cả nằm trong
# HOME của container, mà HOME KHÔNG nằm trên volume nào (chỉ /data, /brains, ~/.claude,
# ~/.codex được persist). Mỗi lần cập nhật image là container mới, HOME mới tinh: bay
# cả binary lẫn đăng nhập, người dùng phải cài + đăng nhập lại từ đầu, mãi mãi.
#
# Cách chữa: mỗi lần boot, link ~/.local, ~/.antigravity, ~/.config, ~/.gemini, ~/.grok vào /data/home/
# (volume /data sẵn có nên KHÔNG cần người dùng sửa docker-compose - chỉ cần image mới).
# Lần đầu sau khi có bản này, nội dung đang có trong HOME được dọn sang volume trước
# khi link, nên ai đã lỡ cài agy trong container hiện tại cũng không mất gì.
#
# An toàn: mọi bước đều nhịn lỗi (|| true / continue) - /data hỏng quyền thì bỏ qua
# việc link và server VẪN LÊN, chỉ mất tính năng giữ-qua-update chứ không chết app.
set -u

PERSIST_ROOT="${JAVIS_HOME_PERSIST:-/data/home}"

# ~/.gemini: `agy` để cấu hình MCP (~/.gemini/config/mcp_config.json - chỗ Javis đấu hub
# vào) và token OAuth của MCP ở đó. Thiếu nó thì mỗi lần cập nhật là mất hết kết nối MCP
# người dùng tự thêm, dù đăng nhập Google vẫn còn.
#
# ~/.grok: đăng nhập xAI của Grok Build (`~/.grok/auth.json`) cộng cấu hình cá nhân. Bỏ sót
# từ 0.50.0 tới 0.50.3, và nó hỏng đúng kiểu đã hỏng với `agy` hồi 16/08 - chỉ khó thấy hơn
# một bậc: binary `grok` nằm ở ~/.local/bin nên ĐƯỢC giữ, thẻ Models vẫn báo "Đã cài CLI",
# chỉ mỗi phiên đăng nhập là bay. Người dùng báo 29/08: "mỗi lần nâng cấp bản mới là grok
# lại bị logout". Thêm một chữ vào danh sách này là xong, không phải sửa docker-compose.
for d in .local .antigravity .config .gemini .grok; do
    src="$HOME/$d"
    dst="$PERSIST_ROOT/$d"
    # Đã là symlink (boot thứ hai trở đi) → xong từ lâu.
    [ -L "$src" ] && continue
    mkdir -p "$dst" 2>/dev/null || continue
    # Container hiện tại đã có sẵn nội dung (agy cài trước bản này) → dọn sang volume,
    # KHÔNG ghi đè file đã có bên volume (bản bên volume là bản sống qua update).
    if [ -d "$src" ]; then
        cp -an "$src/." "$dst/" 2>/dev/null || true
        rm -rf "$src" 2>/dev/null || continue
    fi
    ln -sfn "$dst" "$src" 2>/dev/null || true
done

# Tự cài Antigravity CLI (`agy`) và Grok Build (`grok`) nếu máy chưa có (0.85.1).
#
# Vì sao không có sẵn trong image như claude/codex: hai CLI này không phát hành qua npm mà qua
# script tải về của chính Google và xAI, và nhúng binary của họ vào image công khai trên GHCR là
# phân phối lại phần mềm của người khác. Nên image để trống, còn container tự tải về lúc chạy,
# đúng như `install.sh` và `install.ps1` đã làm cho bản cài trên máy từ 0.59.13.
#
# Trước bản này, người dùng Docker thấy thẻ "CLI chưa cài" ở trang Models kèm một lệnh phải tự gõ,
# mà khách cài qua Hostinger gần như không có chỗ để gõ. Giờ container tự làm hộ.
#
# - CHẠY NỀN: server lên ngay, không chờ hai lượt tải. Thẻ Models đọc file trạng thái bên dưới
#   để nói "đang tự cài" thay vì đưa lệnh bắt người ta gõ.
# - CÀI MỘT LẦN: agy vào ~/.local/bin, grok vào ~/.grok/bin, cả hai đã được link sang /data ở
#   vòng lặp trên nên SỐNG QUA mọi lần cập nhật image. Boot sau thấy có rồi thì không làm gì.
# - HỎNG THÌ THÔI: mạng chặn, nhà cung cấp đổi URL... chỉ ghi lại để thẻ Models nói thật, lần
#   khởi động sau thử lại. Không bao giờ cản server lên.
# - Tắt hẳn: đặt JAVIS_AUTO_INSTALL_CLIS=0 (máy không ra Internet, hoặc không muốn có hai CLI này).
CLI_STATE="$PERSIST_ROOT/.cli-auto-install"
co_cli() {   # <tên binary> <đường dẫn cài mặc định>
    command -v "$1" >/dev/null 2>&1 || [ -x "$2" ] || [ -x "$HOME/.local/bin/$1" ]
}
tu_cai_cli() {   # <tên binary> <đường dẫn cài mặc định> <URL script cài>
    co_cli "$1" "$2" && { echo "ok $(date +%s)" > "$CLI_STATE/$1" 2>/dev/null; return 0; }
    echo "installing $(date +%s)" > "$CLI_STATE/$1" 2>/dev/null
    echo "[$(date -u +%FT%TZ)] cài $1 từ $3" >> "$CLI_STATE/install.log" 2>/dev/null
    if curl -fsSL --max-time 300 "$3" | bash >> "$CLI_STATE/install.log" 2>&1 && co_cli "$1" "$2"; then
        echo "ok $(date +%s)" > "$CLI_STATE/$1" 2>/dev/null
    else
        echo "failed $(date +%s)" > "$CLI_STATE/$1" 2>/dev/null
    fi
}
# Tách hai lớp: lớp ngoài thoát ngay nên lớp trong mồ côi và về tay tini (PID 1), tini dọn nó khi
# xong. Chỉ một lớp thì sau `exec` nó là con của uvicorn, Python không dọn con lạ, để lại zombie.
if [ "${JAVIS_AUTO_INSTALL_CLIS:-1}" != "0" ] && mkdir -p "$CLI_STATE" 2>/dev/null; then
    ( (
        tu_cai_cli agy "$HOME/.local/bin/agy" https://antigravity.google/cli/install.sh
        tu_cai_cli grok "$HOME/.grok/bin/grok" https://x.ai/cli/install.sh
    ) </dev/null >/dev/null 2>&1 & )
fi

exec "$@"
