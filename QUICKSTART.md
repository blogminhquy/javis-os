# Javis OS - Quick start

Chạy Javis OS trong vài phút. Chi tiết từng phần: [docs/](docs/README.md).

## Cách 1 - Hostinger VPS (Docker Manager, 1-click)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Dán URL:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Tùy chọn, để có HTTPS + tên miền) ở ô **Environment** đặt:
   ```
   DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud
   ```
   (hostname xem ở hPanel → VPS; ví dụ `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Đợi 1-3 phút. Mở app bằng nút **Open** (hoặc `https://<DOMAIN_NAME>`).
5. Lần đầu: màn hình sẽ hỏi tạo tài khoản admin. Sau đó đăng nhập Claude Code trong terminal container 1 lần: `claude auth login --claudeai`.

Cập nhật bản mới: bấm **Redeploy** trong Docker Manager (image `:latest`, `pull_policy: always`). Dữ liệu brain giữ nguyên trong volume.

## Cách 2 - Docker ở máy/VPS bất kỳ

```
docker compose -f docker-compose.yml up -d
```
Mở http://localhost:7777. Muốn HTTPS qua Caddy: thêm `-f docker-compose.https.yml`.

## Cách 3 - Chạy trực tiếp (Windows, không Docker)

1. Cài Python 3.12 + Node 22.
2. Trong thư mục dự án: `setup.bat` một lần - tạo .venv, cài deps, và cài sẵn ba engine CLI (Claude Code, Codex, Gemini CLI).
3. `start-javis.bat` để chạy nền (tắt: `stop-javis.bat`).
4. Mở http://localhost:7777.

## Sau khi chạy

- **Chọn engine/model**: trang **Models** (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Google Gemini, Anthropic API).
- **Đấu kết nối** (POS, quảng cáo, lịch, Zalo...) để báo cáo số liệu thật: trang **Kết nối** - xem [docs/09](docs/09-mcp-va-so-lieu.md).
- **Sao lưu brain lên GitHub** để không mất dữ liệu: trang **Tự học** - xem [docs/18](docs/18-sao-luu-github.md).
- **Theo dõi token đã dùng**: trang **Mức dùng** - xem [docs/23](docs/23-muc-dung-token.md).

## Tài liệu đầy đủ

Xem [docs/README.md](docs/README.md) - hướng dẫn từng chức năng (chat/voice, đồ thị tri thức, skills, agents, workflows, việc định kỳ, Kanban, tự học, kết nối, Telegram, Zalo, plugins, bảo mật, backup...).

## Sự cố hay gặp

- **Không cập nhật được bằng nút trong app trên Hostinger**: đúng thiết kế - trên Hostinger dùng **Redeploy** trong Docker Manager (nút trong app cần Watchtower, Hostinger hay chặn Docker socket).
- **ChatGPT/Codex báo "model không hỗ trợ"**: chọn model Codex hợp lệ ở trang Models (vd `gpt-5.5`), không dùng `gpt-5-mini`/`gpt-4o` (đó là model API, Codex account không chạy).
- Thêm: [docs/17 - Khắc phục sự cố](docs/17-khac-phuc-su-co.md).
