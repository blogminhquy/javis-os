<div align="center">

# 🧠 Javis OS

**Trợ lý AI cá nhân + Second Brain - xây trên CLI của các nhà cung cấp AI (Claude Code, ChatGPT/Codex), có giọng nói, đồ thị tri thức 3D, và tự thông minh dần lên.**

*A personal AI operating layer built on provider agent CLIs (Claude Code, ChatGPT/Codex) - voice, a 3D knowledge graph, MCP-driven business reporting, and a self-improvement loop.*

</div>

---

## Javis là gì?

Javis OS **không phải** một chatbot. Nó là một **lớp điều hành AI** chạy trên máy/VPS của bạn, lấy **CLI của nhà cung cấp AI làm "bộ não"** - **Claude Code CLI** (gói Claude) hoặc **Codex CLI** (gói ChatGPT). Tận dụng chính **gói subscription bạn đang trả** thay vì phải mua thêm API riêng: bộ não đó có đầy đủ khả năng đọc/ghi file, gọi công cụ (MCP), chạy lệnh, dùng skill - rồi Javis gói tất cả vào một **dashboard đẹp, điều khiển bằng giọng nói**, kèm một **Second Brain** (bộ nhớ + wiki) tích luỹ tri thức theo thời gian.

> Triết lý: nhà cung cấp nào có **CLI dạng agent + gói subscription** (Claude Code, Codex, và các CLI ra sau) thì Javis dùng được làm bộ não. Ngoài ra vẫn hỗ trợ chat thuần qua OpenRouter / OpenAI / Anthropic API.

Bạn đấu các **MCP** của riêng mình vào (bán hàng/POS, quảng cáo, lịch, email, ghi chú…) → Javis tự phát hiện và **báo cáo kinh doanh + cuộc sống** bằng số liệu thật, nói chuyện như người.

### Vì sao Javis khác biệt

| | Chatbot thường | **Javis OS** |
|---|---|---|
| Bộ não | API gọi rời từng câu | **Claude Code CLI** - đủ tool, MCP, skill, session, chạy lệnh thật |
| Trí nhớ | Quên sau mỗi phiên | **Second Brain sống** - nhớ bạn, dày lên qua từng hội thoại |
| Dữ liệu | Bịa hoặc không có | **Số liệu thật** từ MCP bạn đấu vào (POS, Ads, Lịch…) |
| Tự cải thiện | Không | **Vòng lặp tự chạy nền** làm nhiệm vụ cụ thể theo lịch |
| Giao diện | Khung chat | Dashboard 3D + **giọng nói rảnh tay** + Telegram |
| Triển khai | Khoá vào 1 nhà cung cấp | **Tự host**: Hostinger 1-click / Docker / VPS bất kỳ |

> 💡 **Triết lý:** Javis *biên dịch một lần* tri thức từ ghi chú thô → Wiki, rồi *duy trì* nó sống cùng mỗi nguồn mới. Tri thức **tích luỹ**, không tái phát hiện mỗi lần.

---

## ✨ Tính năng nổi bật

- 🎙️ **Trò chuyện bằng giọng nói rảnh tay** - nói, Javis nghe và trả lời bằng giọng (Edge TTS tiếng Việt). Giữ phím Cách để bật mic.
- 🌌 **Đồ thị tri thức 3D** - bộ não của bạn hiện ra dưới dạng nebula 3D phản ứng theo âm thanh, các note nối nhau qua `[[wikilink]]`.
- 💬 **Phiên hội thoại** - lưu / mở lại / **tìm kiếm toàn văn** mọi cuộc trò chuyện cũ (kể cả khi đổi máy).
- 🗂️ **Quản lý tệp tin** - duyệt, **sửa file `.md`/`.txt` trực tiếp** trong trình duyệt, tải lên/về, ngay trong brain đang chọn.
- 🧩 **Skills (kiểu Hermes)** - gom nhóm, tìm kiếm, **bật/tắt từng skill**, thêm/sửa/xoá; Javis tự xếp skill mới vào đúng nhóm.
- 🤖 **Agents & Workflows** - tạo trợ lý chuyên biệt + chuỗi tự động (Studio), mỗi bước một agent, có kiểm chứng.
- ♻️ **Tự cải thiện** - Javis tự thức theo lịch làm **một nhiệm vụ cụ thể** (vd: mỗi sáng tổng hợp doanh thu + soạn nháp content) rồi tự kiểm chứng.
- 📊 **Dashboard số liệu** - panel trái tự cập nhật chỉ số kinh doanh thật từ MCP, so sánh kỳ trước, đề xuất hành động.
- 🔌 **Quản lý MCP đa-shop** - đấu nhiều server cùng link khác key (vd nhiều cửa hàng POS), dùng được cho cả Claude Code lẫn model OpenRouter/OpenAI.
- 📱 **Telegram bot** - hỏi Javis qua điện thoại, có cả MCP khi dùng engine Claude.
- 🔄 **Đa engine** - Claude Code CLI (đủ MCP), ChatGPT (Codex), OpenRouter, OpenAI API, Anthropic API - đổi trong Settings.
- 🔐 **An toàn khi lên VPS** - tự bắt buộc đăng nhập khi chạy public, chống chiếm tài khoản, rate-limit.

---

## 🚀 Cài đặt

> ⚠️ **Quan trọng về bảo mật:** Javis chạy Claude với **toàn quyền** trên máy. Khi chạy public (Docker/VPS/Hostinger), Javis **tự bắt buộc đăng nhập** - mở app ra là màn tạo tài khoản / đăng nhập, không ai điều khiển được khi chưa có mật khẩu.

### Cách 1 - Hostinger Docker Manager (tên miền + HTTPS) ⚡

VPS Hostinger → **Docker Manager → Compose → URL** → dán **file Hostinger** rồi **Deploy**:
```
https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
```
Ô **Environment** đặt biến `DOMAIN_NAME` (BẮT BUỘC, để Traefik của Hostinger cấp HTTPS):
- **Link miễn phí** (không cần mua tên miền): `DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud`
  (hostname xem ở hPanel → VPS, vd `javis.srv1562015.hstgr.cloud`).
- **Tên miền riêng:** `DOMAIN_NAME=tenmien.com` + trỏ DNS A về IP VPS.

Deploy → đợi 1-3 phút Traefik cấp SSL → mở `https://<DOMAIN_NAME>`. (Chi tiết + xử lý sự cố: [DEPLOY.md](DEPLOY.md).)

> Chỉ muốn chạy nhanh bằng `http://<ip>:7777` (chưa cần tên miền): dùng `docker-compose.yml` (Cách 2).

**3 việc làm 1 lần:**
1. **Để image GHCR ở chế độ Public:** GitHub → repo → **Packages** → `javis-os` → *Package settings* → Visibility = **Public**.
2. **Tạo tài khoản admin** (chọn 1):
   - *Khuyến nghị:* thêm env `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` ở ô Environment → mở app **đăng nhập luôn**.
   - *Hoặc:* mở app sẽ hỏi **MÃ THIẾT LẬP** - trong **App terminal** (vào bên trong container) chạy: `cat /data/state/.setup_token`.
3. **Đăng nhập Claude (bộ não):** App terminal → `claude auth login --claudeai` → mở link, dán code.

### Cách 2 - Docker trên VPS bất kỳ (pull image, không cần clone)

```bash
# Cần Docker (chưa có?  curl -fsSL https://get.docker.com | sh)
mkdir javis && cd javis
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml

docker compose run --rm javis claude auth login --claudeai   # đăng nhập Claude 1 lần
docker compose up -d                                          # pull image + chạy
```
Mở `http://<ip-vps>:7777` → màn tạo tài khoản admin (xem MÃ THIẾT LẬP trong `docker compose logs javis`).

### Cách 3 - Cài trực tiếp lên Linux/macOS (không Docker)

```bash
git clone https://github.com/blogminhquy/javis-os.git javis && cd javis
chmod +x install.sh && ./install.sh
```
Script tự cài Python + Node + Claude CLI, tạo venv, đăng ký dịch vụ systemd tự chạy khi boot, in ra địa chỉ. Báo Claude chưa đăng nhập thì chạy 1 lần: `claude auth login --claudeai`.

> 🍎 **macOS - mở như một app:** sau khi cài xong, double-click `JAVIS OS.app` (hoặc `Start JAVIS OS.command`) để chạy server + mở dashboard; tự chạy khi đăng nhập máy: `./bin/javis-autostart.sh install`. Chi tiết: [bin/README.md](bin/README.md).

### Cách 4 - Windows (máy cá nhân)

```
1. Cài Python 3.12 (tick "Add to PATH") + Node.js LTS
2. npm install -g @anthropic-ai/claude-code  &&  claude auth login --claudeai
3. Double-click  setup.bat   (chạy hiện cửa sổ)
   hoặc           start-javis.vbs   (chạy ngầm, log ở server\javis.log)
4. Mở http://localhost:7777   ·   Dừng: stop-javis.bat
```

📄 Chi tiết hơn (named tunnel URL cố định, build từ source…) xem **[DEPLOY.md](DEPLOY.md)**.

---

## 🎬 Thiết lập lần đầu

Mở Javis → bộ cài đặt sẽ dẫn bạn qua:

1. **Tài khoản admin** - đặt mật khẩu (bắt buộc khi chạy public, để chặn người lạ).
2. **Đăng nhập Claude** - "bộ não". 1 lần, không cần API key. Token lưu trong `~/.claude` (Docker: volume riêng → không mất khi update).
3. **Chọn engine + model** - mặc định Claude Code CLI (đủ MCP). Có thể đổi sang OpenRouter / OpenAI / ChatGPT / Anthropic API trong **Models**.
4. **Đấu MCP** (tuỳ chọn) - vào **MCP**, thêm server (POS, Ads…) bằng URL + key. Javis sẽ báo cáo số liệu thật từ đó.

---

## 📖 Hướng dẫn sử dụng

> 📚 **Tài liệu chi tiết:** xem thư mục **[docs/](docs/README.md)** - hướng dẫn từng chức năng (mở ở đâu, bấm gì, dùng thế nào). Bảng dưới là bản đồ nhanh; cột **Chi tiết** dẫn tới trang hướng dẫn tương ứng.

Dashboard có thanh điều hướng bên trái:

| Mục | Làm gì | Chi tiết |
|---|---|---|
| **Javis** (3D) | Màn chính: trò chuyện (gõ hoặc nói), đồ thị tri thức 3D, panel số liệu trái. | [Trò chuyện & giọng nói](docs/02-tro-chuyen-va-giong-noi.md) · [Đồ thị 3D](docs/03-do-thi-tri-thuc-3d.md) |
| **Tổng quan** | Trạng thái hệ thống, engine, model, công tắc đồ thị, chuẩn hoá brain. | [Bắt đầu & thiết lập](docs/01-bat-dau-thiet-lap.md) |
| **Workflows** | Tạo/chạy chuỗi tự động (agent → agent), có bước kiểm chứng. | [Agents & Workflows](docs/07-agents-va-workflows.md) |
| **Agents** | Tạo trợ lý chuyên biệt (vai trò + skill + bộ nhớ riêng). | [Agents & Workflows](docs/07-agents-va-workflows.md) |
| **Skills** | Gom nhóm + tìm kiếm + **bật/tắt** + thêm/sửa/xoá skill. | [Skills](docs/06-skills.md) |
| **Tệp tin** | Duyệt brain, **sửa `.md`/`.txt` trực tiếp**, tải lên/về, tạo/đổi tên/xoá. | [Quản lý tệp tin](docs/05-quan-ly-tep-tin.md) |
| **Tự cải thiện** | Bật Javis tự chạy nền làm 1 nhiệm vụ cụ thể theo lịch + nhật ký + LINT Wiki. | [Tự cải thiện](docs/08-tu-cai-thien.md) |
| **Lịch** | Quản lý cron/trigger/routine tự động. | [Lịch & tự động hoá](docs/12-lich-tu-dong-hoa.md) |
| **Models** | Main model + các provider (Claude/OpenAI/OpenRouter…) + reasoning + model phụ. | [Models & engine](docs/10-models-va-engine.md) |
| **Kênh** | Bật Telegram bot (hỏi Javis qua điện thoại). | [Kênh Telegram](docs/11-telegram.md) |
| **MCP** | Đấu/quản lý công cụ ngoài (đa-shop cùng link khác key). | [MCP & số liệu](docs/09-mcp-va-so-lieu.md) |
| **Logs** | Nhật ký hoạt động. | [Khắc phục sự cố](docs/17-khac-phuc-su-co.md) |
| **Tài khoản** | Workspace, đăng nhập/đăng xuất, đổi/tắt mật khẩu. | [Bảo mật & tài khoản](docs/14-bao-mat-tai-khoan.md) |

**Mục lục đầy đủ (17 trang):** [docs/README.md](docs/README.md) - gồm thêm [Phiên hội thoại](docs/04-phien-hoi-thoai.md), [Second Brain: bộ nhớ / Wiki / INGEST](docs/13-second-brain-bo-nho-wiki.md), [Thương hiệu & tên miền riêng](docs/15-thuong-hieu-ten-mien.md), [Cấu hình .env](docs/16-cau-hinh-env.md).

### Vài luồng hay dùng

- **Hỏi số liệu:** *"Doanh thu hôm nay thế nào? So với hôm qua?"* → Javis gọi MCP, trả số thật + đề xuất.
- **Tiêu hoá tri thức (INGEST):** thả file/ghi chú vào → Javis tóm tắt, rút insight, viết vào Wiki, gợi ý task.
- **Tự cải thiện:** vào **Tự cải thiện** → chọn "Tự định nghĩa" → mô tả nhiệm vụ (vd *"mỗi sáng tổng hợp bán hàng hôm qua, tìm hàng bán chậm, soạn 1 caption đẩy hàng vào Projects"*) → bật chạy nền.
- **Giọng nói:** bấm mic (hoặc bật rảnh tay) → nói → Javis trả lời bằng giọng. Esc để ngắt.

---

## ⚙️ Cấu hình (`.env`)

Mọi dòng để trống vẫn chạy được. Sao chép `env.example` → `.env` (file mẫu cố ý KHÔNG có dấu chấm đầu để Docker Manager của Hostinger không tự nhập nó vào ô Environment).

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `JAVIS_HOST` | Địa chỉ nghe. `127.0.0.1`=chỉ máy này; `0.0.0.0`=public | `127.0.0.1` |
| `JAVIS_PORT` | Cổng | `7777` |
| `JAVIS_REQUIRE_LOGIN` | `1`/`0` ép bật/tắt bắt buộc đăng nhập (mặc định: bật khi bind public) | *(auto)* |
| `JAVIS_ADMIN_USER` / `JAVIS_ADMIN_PASSWORD` | Tạo sẵn admin lúc deploy (khỏi cần MÃ THIẾT LẬP) | - |
| `JAVIS_STATE_DIR` | Nơi ghi state (settings, sessions, loop) | `server/` (Docker: `/data/state`) |
| `OBSIDIAN_VAULT_PATH` | Vault Second Brain chính | `vault/` (Docker: `/data/vault`) |
| `BRAIN_PATH` | Thư mục brain | `brain/` (Docker: `/data/brain`) |
| `CLAUDE_CWD` | Thư mục làm việc của Claude CLI | repo root |
| `TTS_VOICE` / `TTS_RATE` | Giọng đọc + tốc độ | `vi-VN-HoaiMyNeural` / `+5%` |

---

## 🔐 Bảo mật

- Khi chạy public, **bắt buộc đăng nhập** trước khi dùng bất kỳ chức năng nào (Claude full quyền).
- Tạo admin lần đầu cần **MÃ THIẾT LẬP** (in trong log server) hoặc admin đặt sẵn qua env → chống kẻ chỉ-có-URL chiếm tài khoản.
- **Rate-limit** đăng nhập (khoá tạm sau nhiều lần sai), mật khẩu ≥ 8 ký tự, cookie `secure` khi HTTPS, session hết hạn 30 ngày.
- Truy cập từ xa nên qua **HTTPS** (Hostinger `*.hstgr.cloud` hoặc Cloudflare Tunnel) - đừng phơi cổng thô.

---

## 🔄 Cập nhật

```bash
# Trên máy bạn (sau khi sửa code): đẩy lên GitHub
git add -A && git commit -m "..." && git push     # → CI tự build image mới lên GHCR

# Trên VPS: kéo bản mới
cd javis && ./update.sh          # tự pull image + restart (dữ liệu trong volume KHÔNG mất)
```

## 🌐 Truy cập từ xa (VPS không phải Hostinger)

```bash
docker compose --profile tunnel up -d
docker compose logs tunnel | grep trycloudflare   # → URL https://xxx.trycloudflare.com
```

---

## 🏗️ Kiến trúc

```
Trình duyệt (voice + 3D) ─┐
Telegram ─────────────────┤→  FastAPI (server/) ──→  Claude Code CLI (bộ não, đủ MCP/skill)
                          │                       └→  engine khác: OpenRouter/OpenAI/Codex/Anthropic
                          └→  Second Brain (markdown vault: Memory + Wiki + Sources)
```
- **Backend:** Python FastAPI (`server/`) - `main.py`, `engine.py`, `claude_cli.py`, `sessions.py`, `self_improve.py`, `mcp_*`, `config.py`.
- **Frontend:** HTML/CSS/JS thuần (`dashboard/`) - không framework, nhẹ cho VPS.
- **Bộ não:** Claude Code CLI cài sẵn (subprocess) → kế thừa MCP, skill, auth.
- **Second Brain:** vault markdown (`brain/` hoặc Obsidian vault) - bộ nhớ sống + Wiki tích luỹ.

---

## 🩺 Khắc phục sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Sửa code mà không thấy đổi | Đã đổi `.py`? **Khởi động lại server** (Windows: `stop-javis.bat` → `start-javis.vbs`). Đổi giao diện? **Ctrl+Shift+R**. |
| Port 7777 bị giữ, bản mới không lên | Kill tiến trình cũ TRƯỚC (`stop-javis.bat`, hoặc `taskkill /F /PID <pid>`), rồi start lại. |
| Hostinger không pull được image | Để package GHCR = **Public**; đợi GitHub Action build xong (tab Actions). |
| Mở app báo cần MÃ THIẾT LẬP | App terminal (trong container): `cat /data/state/.setup_token`. Trên host: `docker compose logs javis \| grep "SETUP TOKEN"`. Hoặc đặt env `JAVIS_ADMIN_PASSWORD` để khỏi cần mã. |
| Claude báo chưa đăng nhập | Chạy 1 lần `claude auth login --claudeai` (Docker: trong App terminal). |
| Trang Tệp tin treo "Đang tải" | Khởi động lại server để nạp endpoint mới, rồi Ctrl+Shift+R. |

---

## 📂 Cấu trúc thư mục

```
javis-os/
├── server/              # Backend FastAPI (não, engine, sessions, MCP, self-improve…)
├── dashboard/           # Frontend (voice, đồ thị 3D, console, studio)
├── Brain Default/       # Brain mẫu (agents/workflows/wiki - dữ liệu cá nhân được .gitignore)
├── Dockerfile           # Image: python + Node + Claude CLI
├── docker-compose.yml   # Production (pull image GHCR) - VPS thường, vào bằng http://<ip>:7777
├── docker-compose.hostinger.yml  # Cho Hostinger: tên miền + HTTPS qua Traefik (đặt DOMAIN_NAME)
├── docker-compose.https.yml      # Auto-HTTPS bằng Caddy cho VPS thường (kèm file trên)
├── install.sh           # Cài native Linux/macOS
├── update.sh            # Cập nhật trên VPS
├── docs/                # Hướng dẫn sử dụng chi tiết từng chức năng (17 trang + mục lục)
├── DEPLOY.md            # Hướng dẫn deploy chi tiết
└── CLAUDE.md            # "System prompt" + quy ước cho AI agent
```

---

## 🙏 Cảm hứng & ghi nhận

- **Bộ não:** [Claude Code](https://claude.com/claude-code) (Anthropic).
- **Kiến trúc agent & UI:** học hỏi từ [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) - sessions, skill management, packaging, self-improvement.
- Pattern Second Brain + Bullet Journal số hoá.

---

<div align="center">

Made with ☕ by **[Minh Quý](https://minhquy.vn)** · Repo: `github.com/blogminhquy/javis-os`

</div>
