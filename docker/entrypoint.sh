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

exec "$@"
