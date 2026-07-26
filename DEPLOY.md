# Cài đặt Javis OS trên server / VPS

Javis OS là một AI agent cá nhân + Second Brain. "Bộ não" của nó là **Claude Code CLI**
(đăng nhập một lần, không cần API key). Có 3 cách chạy - chọn 1.

> ⚠️ **An toàn:** Javis chạy Claude với toàn quyền trên máy. Khi chạy public (Docker/VPS/Hostinger),
> Javis **tự bật bắt buộc đăng nhập** - mở app ra là màn **tạo tài khoản admin / đăng nhập**, không
> ai điều khiển được khi chưa đặt mật khẩu. (Chạy nội bộ muốn tắt: `JAVIS_REQUIRE_LOGIN=0`.)

---

## Cách 1 - Hostinger Docker Manager (1-click, nhanh nhất) ⚡

VPS Hostinger → **Docker Manager → Compose → URL** → dán link rồi **Deploy**:
```
https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml
```
Hostinger pull image + chạy. Mở app bằng `http://<ip-vps>:7777` (IP xem ở hPanel → VPS) → ra
màn **tạo tài khoản admin**.

> 🌐 **Muốn LINK RIÊNG có HTTPS (bỏ `:7777`, để mic/voice chạy) mà KHÔNG cần mua tên miền?** Dùng
> `docker-compose.hostinger.yml` + đặt `DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud` - xem mục
> **"Link mặc định + HTTPS trên Hostinger"** ở phần HTTPS bên dưới. Compose gốc này chỉ vào được bằng IP:7777.

**3 việc làm 1 lần:**
1. **Để image GHCR ở chế độ Public:** GitHub → repo `javis-os` → **Packages** → `javis-os`
   → *Package settings* → Visibility = **Public** (để Hostinger pull không cần đăng nhập registry).
   Image do CI tự build mỗi lần push lên `main` (xem mục Cập nhật).
2. **Tạo tài khoản admin an toàn** (Claude chạy full quyền nên không để ai cũng tạo được):
   - **Cách A (khuyến nghị):** trong compose của Hostinger, thêm env `JAVIS_ADMIN_USER` +
     `JAVIS_ADMIN_PASSWORD` → admin tạo sẵn lúc khởi động, mở app ra **đăng nhập luôn**.
   - **Cách B:** bỏ trống → mở app sẽ hỏi **MÃ THIẾT LẬP**. Lấy mã trong **App terminal** (nó vào
     BÊN TRONG container nên KHÔNG có lệnh `docker`): chạy `cat /data/state/.setup_token` → copy chuỗi
     → dán vào màn tạo tài khoản. (Chỉ người xem được file/log mới tạo được admin → kẻ chỉ có URL bó tay.)
3. **Đăng nhập Claude (bộ não) 1 lần:** mở **App terminal** và chạy:
   `claude auth login --claudeai` → mở link, dán code. (token lưu trong volume, không mất khi update.)

---

## Cách 2 - Docker trên VPS bất kỳ (pull image, không cần clone source)

Cần Docker. Chưa có? `curl -fsSL https://get.docker.com | sh`
```bash
mkdir javis && cd javis
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml

docker compose run --rm javis claude auth login --claudeai   # ĐĂNG NHẬP CLAUDE 1 LẦN (link + code)
docker compose up -d                                          # pull image GHCR + chạy
```
Mở `http://<ip-vps>:7777` (hoặc qua tunnel ở dưới) → ra màn tạo tài khoản admin.
Muốn build từ source thay vì pull: `curl -O .../docker-compose.build.yml` rồi
`docker compose -f docker-compose.build.yml up -d --build`.

Lệnh hằng ngày:
```bash
docker compose logs -f     # xem Javis đang làm gì
docker compose restart     # khởi động lại
docker compose down        # tắt
docker compose build --pull && docker compose up -d   # cập nhật
```

Mọi ghi chú / vault / settings nằm trong Docker volume (`javis-data`, `claude-auth`) →
**không mất** khi restart hay update.

### 🔒 HTTPS tự động

> ⚠️ **Voice/mic BẮT BUỘC HTTPS.** Trình duyệt chỉ cho cấp quyền micro/camera trên `https://` (hoặc
> localhost) - mở bằng `http://<ip>:7777` thì mic luôn bị chặn, KHÔNG bật tay được. **Không có chứng
> chỉ HTTPS nào cấp cho IP trần** → muốn mic chạy phải dùng 1 trong các cách dưới (tên miền hoặc tunnel).
>
> **Nhanh nhất (không cần tên miền) - Cloudflare Tunnel:**
> ```bash
> docker compose --profile tunnel up -d
> docker compose logs tunnel | grep trycloudflare
> ```
> → mở URL `https://...trycloudflare.com` → mic + voice chạy. (URL đổi mỗi restart; muốn cố định →
> *named tunnel* + `TUNNEL_TOKEN`, xem mục Cloudflare Tunnel bên dưới.)

#### 🌐 Tên miền + HTTPS trên Hostinger (KHÔNG cần mua tên miền)

Hostinger có sẵn **wildcard DNS** `*.<hostname-vps>.hstgr.cloud` + **Traefik** tự cấp SSL. Nên bạn lấy được
link riêng chạy HTTPS mà không cần mua tên miền. **Lưu ý (đã kiểm chứng):** Hostinger **KHÔNG** tự cấp biến
`TRAEFIK_HOST` cho compose dán tay (chỉ cấp cho app Catalog), nên **bắt buộc đặt 1 biến `DOMAIN_NAME`**:

1. Xem **hostname VPS** ở hPanel → VPS (vd `srv1782015.hstgr.cloud`).
2. Docker Manager → Compose → URL:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. Ô **Environment** (Biến môi trường) đặt **`DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud`**
   (vd `DOMAIN_NAME=javis.srv1782015.hstgr.cloud`). Muốn tên miền RIÊNG (vd `javisos.com`) thì đặt tên miền đó + trỏ DNS A về IP VPS.
4. **Deploy** → đợi 1-3 phút Traefik cấp SSL → mở `https://<DOMAIN_NAME>`.

> Thiếu `DOMAIN_NAME` thì vẫn deploy được (chạy tạm ở `:7777`, chưa có HTTPS). Không thấy ô Environment?
> Bấm **Manage → sửa .yaml**, đổi thẳng dòng `Host(...)` thành `Host(\`javis.srv1782015.hstgr.cloud\`)`.
> **Điểm mấu chốt** (rút từ compose thật của Hermes): nhãn Traefik gắn thẳng vào service, **KHÔNG khai báo
> `networks:` / `external: traefik-proxy`** (chỗ này trước đây làm deploy báo "network not found").
> **Caddy (`docker-compose.https.yml`) KHÔNG dùng trên Hostinger** vì cổng 80/443 đã bị Traefik của họ chiếm.
> Không rành? Dùng **Cloudflare Tunnel** (mục dưới) - cho URL HTTPS mà không đụng gì tới proxy của Hostinger.

**VPS có tên miền riêng - auto Let's Encrypt, đặt NGAY TRONG APP (khuyên dùng):**

Không cần đặt `DOMAIN` lúc chạy nữa - bật Caddy một lần rồi khai báo tên miền trong giao diện.
1. Bật Caddy (On-Demand TLS): `docker compose -f docker-compose.yml -f docker-compose.https.yml up -d`
   *(cần Docker Compose v2.23.1+ - kiểm tra `docker compose version`)*
2. Mở `http://<ip-vps>:7777` → **⚙ Cài đặt → Tên miền riêng** → nhập `javis.tencuaban.com` → **Lưu**.
3. Bấm **Kiểm tra kết nối** → app hiện đúng bản ghi DNS cần tạo (A: `javis.tencuaban.com → <ip-vps>`).
   Trỏ DNS xong, đợi lan.
4. Mở `https://javis.tencuaban.com` → Caddy **tự xin + gia hạn** chứng chỉ ở lần mở đầu, cookie
   Secure tự bật. Xong.

> An toàn: Caddy hỏi backend (`/tls-check`) trước khi xin cert → **chỉ** cấp cho đúng tên miền bạn đã
> nhập trong app. Kẻ trỏ DNS bừa vào IP không ép server xin cert lung tung được (khỏi cạn rate-limit
> Let's Encrypt). Đổi/xoá tên miền: sửa lại trong ⚙ Cài đặt, **không** phải chạy lại lệnh compose.

**Không có tên miền:** dùng Cloudflare Tunnel ngay dưới đây (cũng cho URL HTTPS).

---

### 🌐 Truy cập từ xa (Hostinger / VPS bất kỳ) - Cloudflare Tunnel

Mở giao diện Javis từ máy khác mà KHÔNG cần mở port / không cần tên miền - như Hermes:

1. **Đặt mật khẩu TRƯỚC (bắt buộc):** mở Javis (qua SSH tunnel ở bước 5) → Dashboard → **Tài khoản** → đặt mật khẩu admin. Javis chạy Claude toàn quyền trên máy → TUYỆT ĐỐI không phơi ra Internet khi chưa có mật khẩu. (Server cũng in cảnh báo nếu chạy public mà chưa đặt.)
2. Bật tunnel: `docker compose --profile tunnel up -d`
3. Lấy URL: `docker compose logs tunnel | grep trycloudflare` → mở `https://<ngẫu-nhiên>.trycloudflare.com` trên trình duyệt bất kỳ, đăng nhập mật khẩu. Giờ xem & thao tác Javis từ xa.

**URL cố định (tên miền riêng, kiểu `*.hstgr.cloud`):** tạo *named tunnel* ở Cloudflare Zero Trust (miễn phí) → lấy token → `TUNNEL_TOKEN=...` vào `.env` → đổi dòng `command` của service `tunnel` sang bản `run --token` (comment sẵn trong `docker-compose.yml`), trỏ tới `http://javis:7777`. Quick tunnel đổi URL mỗi lần restart; named tunnel cho URL ổn định.

---

## Cách 2 - Cài trực tiếp lên Linux/macOS (không Docker)

```bash
git clone https://github.com/blogminhquy/javis-os.git javis && cd javis
chmod +x install.sh && ./install.sh
```

Script tự cài Python + Node + Claude CLI, tạo venv, cài deps, đăng ký dịch vụ tự chạy khi
boot (systemd) và in ra địa chỉ. Nếu nó báo Claude chưa đăng nhập, chạy 1 lần:
```bash
claude auth login --claudeai
```
Quản lý dịch vụ: `journalctl -u javis -f` · `sudo systemctl restart javis`

---

## Cách 3 - Windows (máy cá nhân)

Double-click `setup.bat` (chạy hiện cửa sổ) hoặc `start-javis.vbs` (chạy ngầm).
Dừng bằng `stop-javis.bat`. Mở http://localhost:7777

---

## Biến môi trường (`.env`)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `JAVIS_HOST` | Địa chỉ nghe. `127.0.0.1` = chỉ máy này; `0.0.0.0` = mọi nơi (Docker tự đặt) | `127.0.0.1` |
| `JAVIS_PORT` | Cổng | `7777` |
| `JAVIS_STATE_DIR` | Nơi Javis ghi state (settings, sessions, loop config) | `server/` (Docker: `/data/state`) |
| `OBSIDIAN_VAULT_PATH` | Vault Second Brain chính | `vault/` trong repo (Docker: `/data/vault`) |
| `BRAIN_PATH` | Thư mục brain | `brain/` trong repo (Docker: `/data/brain`) |
| `CLAUDE_CWD` | Thư mục làm việc của Claude CLI | repo root |

---

## 🔄 Cập nhật khi có code mới

> **Nhanh nhất - bấm ngay trong app:** mở **Cập nhật** (rail trái) → khung **Javis OS** hiện
> phiên bản đang chạy + tự kiểm tra bản mới trên GitHub. Có bản mới → bấm **⬆ Cập nhật ngay**,
> app tự kéo bản mới + khởi động lại (~20-40s), khỏi vào terminal.
> - **Docker/VPS:** cần service **watchtower** (đã có sẵn trong `docker-compose.yml`). Chỉ Watchtower
>   được cấp quyền Docker (socket); app Javis KHÔNG → an toàn. Không muốn thì xoá service đó,
>   nút sẽ chỉ *báo có bản mới* + hướng dẫn.
> - **Native/Windows:** nút chạy `update.sh` (git pull + restart) giúp bạn.

Repo & image GHCR đều **Public** → `git clone`/`pull` và `docker pull` không cần đăng nhập.

Mỗi khi bạn push code mới, trên VPS chỉ cần:

```bash
cd javis && ./update.sh
```

Script tự `git pull` rồi:
- **Docker**: `docker compose build && docker compose up -d` - dữ liệu trong volume KHÔNG mất.
- **Native (systemd)**: `pip install -r requirements.txt` + `systemctl restart javis`.

Ép chế độ: `./update.sh docker` hoặc `./update.sh native`. Làm tay tương đương:
```bash
git pull && docker compose build && docker compose up -d          # Docker
git pull && ./.venv/bin/pip install -r requirements.txt && sudo systemctl restart javis   # Native
```

Trên máy Windows của bạn, đẩy code lên GitHub: `git add -A && git commit -m "..." && git push`

Để trống = dùng mặc định in-repo → cài trên máy mới chạy được ngay, không cần sửa gì.

---

## Đăng nhập Claude là bước duy nhất bắt buộc

"Bộ não" của Javis là Claude Code CLI. Token đăng nhập nằm trong `~/.claude`
(Docker: volume `claude-auth`). Đăng nhập 1 lần → tồn tại qua mọi restart/update.
Nếu đã đăng nhập trên máy khác, có thể copy thư mục `~/.claude` sang.

## (Tuỳ chọn) Dùng ChatGPT (gói Plus) trong chat

Provider **OpenAI OAuth (ChatGPT)** chat qua **Codex CLI** (đã cài sẵn trong image). Đăng nhập 1 lần:
mở **App terminal** chạy `codex login` (mở link, đăng nhập ChatGPT). Token lưu ở `~/.codex`
(Docker: volume `codex-auth`) → giữ qua mọi update. Kiểm tra: `codex --version`. Sau đó vào
**Models → Đổi model → ChatGPT** là chat dùng được. (ChatGPT-qua-codex là thử nghiệm; muốn ổn
định/đa model hơn thì dùng **OpenRouter** - 1 key mọi model - hoặc Claude.)
