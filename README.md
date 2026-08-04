<div align="center">

# 🧠 Javis OS

**AI agentic đổi được bộ não + Second Brain - chạy trên model nào bạn muốn (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Gemini, Anthropic API, Groq), có giọng nói, đồ thị tri thức, và tự thông minh dần lên.**

*A model-agnostic agentic AI layer - swap the brain (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Gemini, Anthropic API, Groq) without losing tools: voice, a knowledge graph, MCP-driven business reporting, and a self-improvement loop.*

</div>

---

## Javis là gì?

Javis OS **không phải** một chatbot. Nó là một **AI agentic tự host** chạy trên máy/VPS của bạn: đọc/ghi file, gọi công cụ (MCP), chạy skill, giao việc chạy nền, tự đặt lịch - rồi gói tất cả vào một **dashboard đẹp, điều khiển bằng giọng nói**, kèm một **Second Brain** (bộ nhớ + wiki) tích luỹ tri thức theo thời gian.

**Bộ não thì bạn chọn, và đổi lúc nào cũng được.** Bảy đường dùng được ngay: **Claude Code** và **ChatGPT/Codex** (dùng chính gói subscription bạn đang trả, không cần mua API riêng), **OpenRouter · OpenAI API · Google Gemini · Anthropic API · Groq** (chỉ cần API key).

> Triết lý: **năng lực nằm ở Javis, không nằm ở model.** Mọi bộ não đều được cấp cùng bộ đồ nghề qua trung tâm kết nối (MCP Hub) chung - MCP đã đấu, tool đọc/ghi brain, skill, việc Kanban, agent/workflow/loop/nhắc hẹn. Khác biệt duy nhất: hai engine CLI chạy thêm được **lệnh máy**. Đổi từ Claude sang Gemini không làm Javis mất chức năng nào ngoài chuyện đó.

Bạn đấu các **kết nối** của riêng mình vào (bán hàng/POS, quảng cáo, lịch, email, Zalo, ghi chú…) → Javis tự phát hiện và **báo cáo kinh doanh + cuộc sống** bằng số liệu thật, nói chuyện như người.

### Vì sao Javis khác biệt

| | Chatbot thường | **Javis OS** |
|---|---|---|
| Bộ não | Khoá cứng 1 model, API gọi rời từng câu | **Đổi được**: 7 nhà cung cấp, cái nào cũng đủ tool, MCP, skill, session |
| Trí nhớ | Quên sau mỗi phiên | **Second Brain sống** - nhớ bạn, dày lên qua từng hội thoại |
| Dữ liệu | Bịa hoặc không có | **Số liệu thật** từ kết nối bạn đấu vào (POS, Ads, Lịch, Zalo…) |
| Tự cải thiện | Không | **Vòng lặp tự chạy nền** + hàng đợi việc do AI tự vận hành |
| Giao diện | Khung chat | Dashboard + đồ thị tri thức + **giọng nói rảnh tay** + Telegram |
| Triển khai | Khoá vào 1 nhà cung cấp | **Tự host**: Hostinger 1-click / Docker / VPS bất kỳ |

> 💡 **Triết lý:** Javis *biên dịch một lần* tri thức từ ghi chú thô → Wiki, rồi *duy trì* nó sống cùng mỗi nguồn mới. Tri thức **tích luỹ**, không tái phát hiện mỗi lần.

---

## ✨ Tính năng nổi bật

- 🎙️ **Trò chuyện bằng giọng nói rảnh tay** - nói, Javis nghe và trả lời bằng giọng. Chọn được nhà cung cấp giọng đọc: Edge TTS (miễn phí, mặc định), OpenAI hoặc ElevenLabs.
- 🌌 **Đồ thị tri thức** - bộ não của bạn hiện ra thành mạng note nối nhau qua `[[wikilink]]`, bằng canvas nhẹ và chạy được ngoại tuyến.
- 💬 **Phiên hội thoại** - lưu / mở lại / **tìm kiếm toàn văn** mọi cuộc trò chuyện cũ; phiên dài được nén tóm tắt thay vì cắt cụt trí nhớ.
- 🗂️ **Quản lý tệp tin** - duyệt, **sửa file `.md`/`.txt` trực tiếp** trong trình duyệt, tìm file theo tên hoặc theo nội dung, tải lên/về.
- 🧩 **Skills** - gom nhóm, tìm kiếm, **bật/tắt từng skill**, thêm/sửa/xoá, nhập/xuất gói; Javis tự xếp skill mới vào đúng nhóm.
- 🧰 **Plugins** - thả một thư mục Python vào là có thêm **tool/hook native** cho MỌI engine, không phải sửa lõi.
- 🤖 **Agents & Workflows** - tạo trợ lý chuyên biệt (có bộ nhớ riêng) + chuỗi tự động nhiều bước, có bước kiểm chứng.
- ♻️ **Việc định kỳ & nhắc hẹn** - nhiều vòng lặp chạy nền song song, mỗi vòng làm đúng một việc bạn mô tả rồi tự kiểm chứng; kèm nhắc hẹn theo giờ cố định hoặc cron.
- 🗃️ **Việc (Kanban)** - giao một "goal" bằng lời, AI tự đặc tả, chọn worker, chạy nền và chỉ gọi bạn khi có ngoại lệ.
- 🧠 **Tự học** - sau mỗi hội thoại Javis tự rút ký ức, đúc tri thức Wiki và kỹ năng; mỗi lần học là một commit git nên **hoàn tác được một chạm**.
- 🔌 **Kho kết nối đa tài khoản** - Pancake POS, Zalo, Meta/Google/TikTok Ads, Google Workspace, Slack, Webcake, Substack… nhiều tài khoản cùng một dịch vụ, mỗi tài khoản một mức quyền riêng, Javis **chặn cứng** thao tác vượt quyền.
- 📱 **Telegram & Zalo** - hỏi Javis qua Telegram; đọc, tìm lịch sử và gửi tin Zalo bằng MCP chuẩn của `zalo-agent-cli`.
- 🎨 **Tạo ảnh** bằng chính gói ChatGPT đã đăng nhập, không cần API key riêng.
- 📊 **Mức dùng** - Javis tự đo token vào/ra và chi phí theo ngày, theo nhà cung cấp, tách rõ phần bạn gõ tay với phần Javis tự chạy nền.
- ⇅ **Sao lưu brain lên GitHub** - đồng bộ 2 chiều mọi brain lên một repo riêng tư, dùng chung giữa máy nhà và VPS.
- 🔄 **Đa engine, đổi không mất chức năng** - Claude Code, ChatGPT (Codex), OpenRouter, OpenAI API, Google Gemini, Anthropic API, Groq. Đổi trong **Models** một cú bấm; bộ não nào cũng gọi được MCP Javis, tool file brain và skill.
- 🔐 **An toàn khi lên VPS** - tự bắt buộc đăng nhập khi chạy public, chống chiếm tài khoản, rate-limit, chặn CSRF, mã hoá khoá bí mật trong cấu hình.

---

## 🚀 Cài đặt

> ⚠️ **Quan trọng về bảo mật:** Javis chạy bộ não AI với **toàn quyền** trên máy. Khi chạy public (Docker/VPS/Hostinger), Javis **tự bắt buộc đăng nhập** - mở app ra là màn tạo tài khoản / đăng nhập, không ai điều khiển được khi chưa có mật khẩu.

### Cách 1 - Hostinger Docker Manager (tên miền + HTTPS) ⚡

VPS Hostinger → **Docker Manager → Compose → URL** → dán **file Hostinger** rồi **Deploy**:
```
https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
```
Ô **Environment** của mẫu mới chỉ còn 3 trường cần thiết: `DOMAIN_NAME`,
`JAVIS_ADMIN_USER`, `JAVIS_ADMIN_PASSWORD`. Các biến kỹ thuật về cổng, state,
brain và thư mục chạy đã được ẩn vì Docker image tự đặt đúng.

Đặt `DOMAIN_NAME` để Traefik của Hostinger cấp HTTPS:
- **Link miễn phí** (không cần mua tên miền): `DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud`
  (hostname xem ở hPanel → VPS, vd `javis.srv1562015.hstgr.cloud`).
- **Tên miền riêng:** `DOMAIN_NAME=tenmien.com` + trỏ DNS A về IP VPS.

Deploy → đợi 1-3 phút Traefik cấp SSL → mở `https://<DOMAIN_NAME>`. (Chi tiết + xử lý sự cố: [DEPLOY.md](DEPLOY.md).)

> Chỉ muốn chạy nhanh bằng `http://<ip>:7777` (chưa cần tên miền): dùng `docker-compose.yml` (Cách 2).

**3 việc làm 1 lần:**
1. **Để image GHCR ở chế độ Public:** GitHub → repo → **Packages** → `javis-os` → *Package settings* → Visibility = **Public**.
2. **Tạo tài khoản admin** (chọn 1):
   - *Khuyến nghị:* điền sẵn `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` đang có trong ô Environment → mở app **đăng nhập luôn**.
   - *Hoặc:* mở app sẽ hỏi **MÃ THIẾT LẬP** - trong **App terminal** (vào bên trong container) chạy: `cat /data/state/.setup_token`.
3. **Đăng nhập bộ não:** App terminal → `claude auth login --claudeai` → mở link, dán code. (Dùng gói ChatGPT thì đăng nhập ở trang **Models** sau khi mở app.)

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
2. **Chọn bộ não** - đi bằng gói subscription thì đăng nhập 1 lần, không cần API key: Claude Code lưu token trong `~/.claude` (Docker: volume riêng → không mất khi update), ChatGPT/Codex đăng nhập ngay trong trang **Models**. Đi bằng API key thì chỉ dán key OpenRouter / OpenAI / Gemini / Anthropic là xong.
3. **Chọn model** - mặc định chọn sẵn Claude Code, nhưng đổi sang nhà cung cấp nào trong **Models** cũng được và **không mất chức năng nào** (trừ chạy lệnh máy, vốn chỉ có ở hai engine CLI).
4. **Đấu kết nối** (tuỳ chọn) - vào **Kết nối**, chọn dịch vụ trong Kho rồi dán key hoặc quét QR. Javis sẽ báo cáo số liệu thật từ đó.

---

## 📖 Hướng dẫn sử dụng

> 📚 **Tài liệu chi tiết:** xem thư mục **[docs/](docs/README.md)** - hướng dẫn từng chức năng (mở ở đâu, bấm gì, dùng thế nào). Bảng dưới là bản đồ nhanh; cột **Chi tiết** dẫn tới trang hướng dẫn tương ứng.

Thanh điều hướng bên trái gom **17 trang** thành **6 nhóm** (bấm tên nhóm để mở):

| Nhóm | Mục | Làm gì | Chi tiết |
|---|---|---|---|
| **Trợ lý** | **Javis** | Màn chính: trò chuyện (gõ hoặc nói), đồ thị tri thức, cây thư mục brain bên trái. | [Trò chuyện & giọng nói](docs/02-tro-chuyen-va-giong-noi.md) · [Đồ thị tri thức](docs/03-do-thi-tri-thuc.md) |
| | **Trò chuyện** | Khung chat rộng toàn màn hình kèm cột lịch sử hội thoại. | [Phiên hội thoại](docs/04-phien-hoi-thoai.md) |
| **Bộ não** | **Tệp tin** | Duyệt brain, **sửa `.md`/`.txt` trực tiếp**, tìm file theo tên/nội dung, tải lên/về. | [Quản lý tệp tin](docs/05-quan-ly-tep-tin.md) |
| | **Tự học** | Javis tự rút ký ức, đúc Wiki, kỹ năng sau mỗi hội thoại; hoàn tác được. | [Tự học](docs/22-tu-hoc.md) |
| **Năng lực** | **Agents** | Tạo trợ lý chuyên biệt (vai trò + skill + bộ nhớ riêng). | [Agents & Workflows](docs/07-agents-va-workflows.md) |
| | **Skills** | Gom nhóm + tìm kiếm + **bật/tắt** + thêm/sửa/xoá + nhập/xuất skill. | [Skills](docs/06-skills.md) |
| | **Workflows** | Tạo/chạy chuỗi tự động (agent → agent), có bước kiểm chứng. | [Agents & Workflows](docs/07-agents-va-workflows.md) |
| | **Plugins** | Thêm tool/hook native cho mọi engine bằng một thư mục Python. | [Plugins](docs/20-plugins.md) |
| **Việc** | **Việc** | Hàng đợi task nền do AI tự đặc tả và tự chạy; bạn chỉ xử lý ngoại lệ. | [Việc (Kanban)](docs/21-viec-kanban.md) |
| | **Việc định kỳ** | Nhiều vòng lặp chạy nền + nhắc hẹn theo giờ hoặc cron. | [Việc định kỳ & Nhắc hẹn](docs/08-viec-dinh-ky.md) |
| **Kết nối** | **Kết nối** | Kho dịch vụ ngoài, đa tài khoản cùng một dịch vụ, phân quyền 3 mức. | [Kết nối & số liệu](docs/09-mcp-va-so-lieu.md) |
| | **Kênh** | Bật bot Telegram (hỏi Javis qua điện thoại). | [Kênh Telegram](docs/11-telegram.md) · [Kênh Zalo](docs/12-zalo.md) |
| | *(terminal)* | `pip install javis-cli` rồi gõ `javis "..."` - kênh thứ ba, cùng một Javis. | [Javis CLI](docs/24-cli-terminal.md) |
| | **Models** | Main model + các provider + mức suy nghĩ + model việc nền. | [Models & engine](docs/10-models-va-engine.md) |
| **Hệ thống** | **Mức dùng** | Token và chi phí theo ngày, theo nhà cung cấp, theo nguồn phát sinh. | [Mức dùng](docs/23-muc-dung-token.md) |
| | **Cài đặt** | Trạng thái hệ thống, giao diện & brain, giọng nói, thương hiệu, tên miền. | [Bắt đầu & thiết lập](docs/01-bat-dau-thiet-lap.md) |
| | **Cập nhật** | Phiên bản hiện tại, cập nhật/Redeploy, tiến trình và nhật ký tính năng mới. | [Khắc phục sự cố](docs/17-khac-phuc-su-co.md) |
| | **Tài khoản** | Workspace, đăng nhập/đăng xuất, đổi/tắt mật khẩu, token API cho CLI. | [Bảo mật & tài khoản](docs/14-bao-mat-tai-khoan.md) · [Javis CLI](docs/24-cli-terminal.md) |

**Mục lục đầy đủ (24 trang):** [docs/README.md](docs/README.md) - gồm thêm [Second Brain: bộ nhớ / Wiki / INGEST](docs/13-second-brain-bo-nho-wiki.md), [Sao lưu brain lên GitHub](docs/18-sao-luu-github.md), [Task & Dataview trong note](docs/19-task-va-dataview.md), [Thương hiệu & tên miền riêng](docs/15-thuong-hieu-ten-mien.md), [Cấu hình .env](docs/16-cau-hinh-env.md).

### Vài luồng hay dùng

- **Hỏi số liệu:** *"Doanh thu hôm nay thế nào? So với hôm qua?"* → Javis gọi đúng kết nối, trả số thật + đề xuất.
- **Tiêu hoá tri thức (INGEST):** thả file/ghi chú vào → Javis tóm tắt, rút insight, viết vào Wiki, gợi ý task.
- **Giao việc nền:** vào **Việc** → **+ Giao goal** → mô tả bằng lời (vd *"tổng hợp bán hàng tuần này, tìm hàng bán chậm, soạn 3 caption đẩy hàng"*) → AI tự đặc tả và chạy, báo kết quả về Telegram.
- **Việc định kỳ:** vào **Việc định kỳ** → **+ Thêm việc** → chọn *Việc lặp* (mỗi N phút) hoặc *Nhắc hẹn* (8h30 mỗi ngày).
- **Giọng nói:** bấm mic (hoặc bật rảnh tay) → nói → Javis trả lời bằng giọng.

---

## ⚙️ Cấu hình (`.env`)

Mọi dòng để trống vẫn chạy được. Sao chép `env.example` → `.env` (file mẫu cố ý KHÔNG có dấu chấm đầu để Docker Manager của Hostinger không tự nhập nó vào ô Environment).

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `JAVIS_HOST` | Địa chỉ nghe. `127.0.0.1`=chỉ máy này; `0.0.0.0`=public | `127.0.0.1` |
| `JAVIS_PORT` | Cổng | `7777` |
| `JAVIS_REQUIRE_LOGIN` | `1`/`0` ép bật/tắt bắt buộc đăng nhập (mặc định: bật khi bind public) | *(auto)* |
| `JAVIS_ADMIN_USER` / `JAVIS_ADMIN_PASSWORD` | Tạo sẵn admin lúc deploy (khỏi cần MÃ THIẾT LẬP) | - |
| `JAVIS_ALLOWED_HOSTS` | Thêm hostname vào danh sách cho phép (chống CSRF / DNS-rebinding) | localhost + tên miền đã đặt |
| `JAVIS_SECURE_COOKIE` | Ép cookie `Secure`. Chỉ bật khi chắc chắn HTTPS đầu-cuối | *(auto theo tên miền)* |
| `JAVIS_STATE_DIR` | Nơi ghi state (settings, sessions, khoá mã hoá, cấu hình việc định kỳ) | `server/` (Docker: `/data/state`) |
| `BRAINS_DIR` | Thư mục CHA chứa mọi brain | `brains/` (Docker: `/brains`) |
| `OBSIDIAN_VAULT_PATH` | Vault Second Brain ngoài (nếu bạn đã có vault sẵn) | `vault/` (Docker: `/data/vault`) |
| `CLAUDE_CWD` | Thư mục làm việc của bộ não Claude | repo root |
| `JAVIS_ENABLE_USER_PLUGINS` | `true` mới cho phép chạy plugin do bạn cài (code Python thật trong server) | *(tắt)* |
| `WATCHTOWER_TOKEN` | Token cho nút "Cập nhật ngay" trên bản Docker | `javis-update` |
| `TTS_VOICE` / `TTS_RATE` | Giọng đọc + tốc độ (Edge TTS) | `vi-VN-HoaiMyNeural` / `+5%` |

Danh sách đầy đủ mọi biến: [docs/16 - Cấu hình .env](docs/16-cau-hinh-env.md).

---

## 🔐 Bảo mật

- Khi chạy public, **bắt buộc đăng nhập** trước khi dùng bất kỳ chức năng nào (bộ não chạy full quyền trên máy).
- Tạo admin lần đầu cần **MÃ THIẾT LẬP** (in trong log server) hoặc admin đặt sẵn qua env → chống kẻ chỉ-có-URL chiếm tài khoản.
- **Rate-limit** đăng nhập (khoá tạm sau nhiều lần sai), mật khẩu ≥ 8 ký tự, cookie `secure` khi HTTPS, session hết hạn 30 ngày.
- **Chặn CSRF và DNS-rebinding**: mọi request ghi có Origin lạ đều bị từ chối.
- **Khoá bí mật được mã hoá** trong `settings.json` (API key, token OAuth, token bot Telegram, token backup) bằng khoá riêng của máy ở `JAVIS_STATE_DIR/.secret_key`.
- **Plugin do bạn cài mặc định bị chặn** - phải tự bật `JAVIS_ENABLE_USER_PLUGINS=true` vì chúng chạy code Python thật trong tiến trình server.
- Truy cập từ xa nên qua **HTTPS** (Hostinger `*.hstgr.cloud` hoặc Cloudflare Tunnel) - đừng phơi cổng thô.

---

## 🔄 Cập nhật

```bash
# Trên máy bạn (sau khi sửa code): đẩy lên GitHub
git add -A && git commit -m "..." && git push     # → CI tự build image mới lên GHCR

# Trên VPS: kéo bản mới
cd javis && ./update.sh          # tự pull image + restart (dữ liệu trong volume KHÔNG mất)
```

Trong app: mở **Cập nhật** (nhóm Hệ thống) → **⬆ Cập nhật ngay** nếu môi trường hỗ trợ, có thanh tiến trình và nút lùi bản khi bản mới hỏng.

## 🌐 Truy cập từ xa (VPS không phải Hostinger)

```bash
docker compose --profile tunnel up -d
docker compose logs tunnel | grep trycloudflare   # → URL https://xxx.trycloudflare.com
```

---

## 🏗️ Kiến trúc

```
Trình duyệt (voice + đồ thị) ─┐                        ┌→ Claude Agent SDK   (gói Claude)
Telegram ─────────────────────┤→ FastAPI (server/) ────┼→ Codex CLI          (gói ChatGPT)
Zalo Agent MCP ──────────────┤          │             └→ OpenRouter / OpenAI / Gemini / Anthropic API
                              │          ├→ MCP Hub  (kho Kết nối dùng chung cho MỌI engine)
                              └──────────┴→ Second Brain (vault markdown: Memory + Wiki + Sources)
```
- **Backend:** Python FastAPI trong `server/`.
  - Bộ não & engine: `claude_sdk_engine.py` (engine Claude, qua Claude Agent SDK), `claude_cli.py` (factory + auth cho Claude/Codex), `engine.py` (năm engine API kèm vòng gọi tool MCP), `aux_engine.py` (chọn engine cho việc nền + chuỗi dự phòng khi engine chết).
  - Công cụ: `mcp_hub.py`, `mcp_store.py`, `mcp_client.py`, `mcp_catalog.py`, `plugins_host.py`, `oauth_mcp.py`.
  - Việc nền: `self_improve.py` (việc định kỳ), `reminders.py` (nhắc hẹn), `tasks.py` + `task_store.py` (Kanban), `learn.py` (tự học).
  - Dữ liệu: `sessions.py`, `compaction.py`, `git_brain.py`, `media_gc.py`, `usage_index.py` + `usage_store.py`.
  - Kênh: `telegram_bot.py`, `channel_context.py`; Zalo đi qua MCP Hub.
  - Nền tảng: `main.py`, `routes/` (domain, graph), `config.py`, `web_security.py`, `secrets_store.py`.
- **Frontend:** HTML/CSS/JS thuần (`dashboard/`) - không framework, nhẹ cho VPS.
- **Second Brain:** vault markdown trong `brains/<tên brain>/` - bộ nhớ sống + Wiki tích luỹ.

---

## 🩺 Khắc phục sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Sửa code mà không thấy đổi | Đã đổi `.py`? **Khởi động lại server** (Windows: `stop-javis.bat` → `start-javis.vbs`). Đổi giao diện? **Ctrl+Shift+R**. |
| Port 7777 bị giữ, bản mới không lên | Kill tiến trình cũ TRƯỚC (`stop-javis.bat`, hoặc `taskkill /F /PID <pid>`), rồi start lại. |
| Hostinger không pull được image | Để package GHCR = **Public**; đợi GitHub Action build xong (tab Actions). |
| Mở app báo cần MÃ THIẾT LẬP | App terminal (trong container): `cat /data/state/.setup_token`. Trên host: `docker compose logs javis \| grep "SETUP TOKEN"`. Hoặc đặt env `JAVIS_ADMIN_PASSWORD` để khỏi cần mã. |
| Bộ não báo chưa đăng nhập | Vào **Models**, thẻ nhà cung cấp tương ứng, bấm đăng nhập. Hoặc chạy 1 lần `claude auth login --claudeai` (Docker: trong App terminal). |
| Ảnh cũ trong hội thoại hiện ô xám | Đúng thiết kế: `attachments/` là vùng cache, hết hạn 30 ngày hoặc 300MB. Xem [Khắc phục sự cố](docs/17-khac-phuc-su-co.md). |

---

## 📂 Cấu trúc thư mục

```
javis-os/
├── server/              # Backend FastAPI (engine, kết nối, việc nền, kênh, bộ nhớ…)
│   └── routes/          # Route tách riêng (tên miền, đồ thị)
├── dashboard/           # Frontend (voice, đồ thị, console, studio, usage)
├── brains/              # MỌI second brain (brain mặc định: brains/Brain Default)
├── system/              # Đi kèm app: plugin bundled, skill hệ thống, kho kết nối mẫu
├── tests/               # Bộ test Python
├── website/             # Trang giới thiệu
├── docs/                # Hướng dẫn sử dụng chi tiết (23 trang + mục lục)
├── Dockerfile           # Image: python + Node + Claude CLI
├── docker-compose.yml   # Production (pull image GHCR) - VPS thường, vào bằng http://<ip>:7777
├── docker-compose.hostinger.yml  # Cho Hostinger: tên miền + HTTPS qua Traefik (đặt DOMAIN_NAME)
├── docker-compose.https.yml      # Auto-HTTPS bằng Caddy cho VPS thường (kèm file trên)
├── install.sh           # Cài native Linux/macOS
├── update.sh            # Cập nhật trên VPS
├── env.example          # Mẫu biến môi trường
├── VERSION · CHANGELOG.md
├── QUICKSTART.md        # Bắt đầu nhanh
├── DEPLOY.md            # Hướng dẫn deploy chi tiết
└── CLAUDE.md            # "System prompt" + quy ước cho AI agent
```

---

## 🙏 Cảm hứng & ghi nhận

- **Bộ não:** [Claude Code](https://claude.com/claude-code) và [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) (Anthropic), [Codex CLI](https://developers.openai.com/codex/cli) (OpenAI), cùng API của [OpenRouter](https://openrouter.ai), OpenAI, [Google Gemini](https://ai.google.dev), Anthropic và [Groq](https://groq.com).
- **Chuẩn công cụ:** [Model Context Protocol](https://modelcontextprotocol.io) - toàn bộ kho Kết nối của Javis chạy trên chuẩn này.
- Pattern Second Brain + Bullet Journal số hoá.

---

<div align="center">

Made with ☕ by **[Minh Quý](https://minhquy.vn)** · Repo: `github.com/blogminhquy/javis-os`

</div>
