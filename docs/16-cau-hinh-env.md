# Cấu hình .env

Trang này liệt kê đầy đủ mọi biến môi trường mà Javis OS đọc lúc khởi động, kèm ý nghĩa, giá trị mặc định và khi nào cần đổi. Nội dung dựa chính xác vào file `env.example` và cách server đọc `os.getenv(...)` trong mã nguồn (`server/config.py`, `server/main.py`, `server/claude_cli.py`, `server/sessions.py`).

Điểm quan trọng nhất cần nhớ: **mọi dòng để trống vẫn chạy được**. Trên máy cá nhân, bạn gần như không cần đụng tới file `.env`. Việc chỉnh `.env` chủ yếu dành cho khi bạn đưa Javis lên VPS/server public hoặc muốn đổi giọng đọc, cổng, đường dẫn dữ liệu.

## Tính năng này là gì

`.env` là một file văn bản đặt ở thư mục gốc dự án (`D:/Project/Javis-OS/.env`). Mỗi dòng là một biến dạng `TÊN_BIẾN=giá trị`. Khi Javis khởi động, nó đọc các biến này để biết: nghe ở cổng nào, có bắt buộc đăng nhập không, dữ liệu Second Brain nằm ở đâu, giọng đọc mặc định là gì.

Cần phân biệt rõ 2 nơi cấu hình để khỏi nhầm:

- **File `.env`**: các thiết lập cấp hệ thống, đọc 1 lần lúc khởi động. Đổi xong phải khởi động lại Javis mới có hiệu lực.
- **Bảng ⚙ Cài đặt trong app** (trang Tài khoản, Models, Kênh...): các thiết lập đổi nóng qua giao diện, lưu vào `settings.json`, không cần sửa file. Ví dụ: đổi model, khoá API OpenRouter, token Telegram, tên miền riêng, logo. Xem thêm ở [Models & engine](10-models-va-engine.md), [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md), [Thương hiệu & tên miền](15-thuong-hieu-ten-mien.md).

Nói gọn: `.env` lo phần "chạy ở đâu, ai được vào, dữ liệu nằm đâu". Bảng Cài đặt trong app lo phần "dùng model nào, khoá gì, giọng gì".

## Mở ở đâu trong Javis

`.env` không có nút bấm trong dashboard. Đây là file bạn tự tạo và sửa bằng trình soạn thảo văn bản (Notepad, VS Code...).

Các bước tạo file `.env` lần đầu:

1. Mở thư mục dự án `D:/Project/Javis-OS/`.
2. Tìm file mẫu `env.example` (tên cố ý KHÔNG có dấu chấm đầu - để Docker Manager của Hostinger không tự quét file `.env*` rồi nhập cả dòng chú thích vào ô Environment).
3. Sao chép nó và đổi tên bản sao thành `.env` (bản sao CÓ dấu chấm đầu, không có phần đuôi `.txt`).
4. Mở `.env` bằng trình soạn thảo, bỏ dấu `#` ở đầu dòng biến bạn muốn bật, rồi điền giá trị.
5. Lưu file. Khởi động lại Javis.

Cách sao chép nhanh bằng lệnh (chạy trong thư mục dự án):

- Windows PowerShell: `Copy-Item env.example .env`
- Git Bash / Linux / macOS: `cp env.example .env`

Lưu ý về dấu `#`: dòng bắt đầu bằng `#` là dòng chú thích, Javis bỏ qua. Muốn bật một biến đang bị chú thích, xoá dấu `#` ở đầu dòng đó. Ví dụ đổi từ `# JAVIS_PORT=7777` thành `JAVIS_PORT=8080`.

## Danh sách đầy đủ các biến

Dưới đây là mọi biến Javis thực sự đọc, gom theo chức năng. Cột "Mặc định" là giá trị dùng khi bạn để trống hoặc không khai báo.

### Nhóm 1: Hiển thị workspace

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `WORKSPACE_NAME` | Tên workspace hiển thị trên dashboard | `Javis OS` | Muốn đặt tên riêng cho không gian làm việc. Lưu ý: nếu bạn đã đặt tên trong app thì app ưu tiên tên đã lưu, biến này chỉ là dự phòng. |
| `USER_NAME` | Tên người dùng hiển thị | `Bạn` | Muốn Javis xưng hô bằng tên bạn thay vì "Bạn". |

### Nhóm 2: Mạng (cổng và địa chỉ nghe)

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `JAVIS_HOST` | Địa chỉ server nghe. `127.0.0.1` = chỉ máy này truy cập được. `0.0.0.0` = nghe mọi nơi (public, ai có địa chỉ đều vào được) | `127.0.0.1` | Chỉ đổi sang `0.0.0.0` khi chạy trên VPS/server và muốn truy cập từ máy khác. Khi đó phải bật đăng nhập (xem nhóm 3). |
| `JAVIS_PORT` | Cổng nghe của dashboard | `7777` | Cổng `7777` bị chiếm hoặc muốn cổng khác. Đổi xong nhớ mở đúng cổng đó trên trình duyệt. |

Chi tiết quan trọng về `JAVIS_HOST`: Javis dùng cơ chế "an toàn mặc định". Nếu bạn để địa chỉ nghe KHÔNG phải loopback (tức khác `127.0.0.1`, `localhost`, `::1`), server tự coi là đang chạy public và **tự bật bắt buộc đăng nhập** để không ai vào được nếu chưa có tài khoản. Lý do: Claude chạy với đầy quyền trên máy, để hở là nguy hiểm.

### Nhóm 3: Đăng nhập và bảo mật

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `JAVIS_REQUIRE_LOGIN` | Ép bật/tắt bắt buộc đăng nhập. `1`/`true`/`yes`/`on` = bật. `0`/`false`/`no`/`off` = tắt | Tự động (bật khi bind public) | Chạy localhost rồi expose ra ngoài qua tunnel (Cloudflare, ngrok...): đặt `JAVIS_REQUIRE_LOGIN=1` để chặn người lạ. |
| `JAVIS_ADMIN_USER` | Tên đăng nhập admin tạo sẵn lúc deploy | `admin` | Đặt cùng `JAVIS_ADMIN_PASSWORD` để tạo sẵn tài khoản, khỏi cần lấy MÃ THIẾT LẬP từ log. |
| `JAVIS_ADMIN_PASSWORD` | Mật khẩu admin tạo sẵn lúc deploy | (trống) | Deploy public: đặt mật khẩu mạnh ở đây. Có biến này và chưa có admin, Javis tạo tài khoản admin ngay lúc khởi động và đóng luôn màn hình tạo tài khoản (an toàn nhất cho public). |
| `JAVIS_SECURE_COOKIE` | Bật cookie chỉ gửi qua HTTPS. `1`/`true`/`yes`/`on` = bật | Tắt | Chỉ bật khi CHẮC CHẮN chạy HTTPS đầu-cuối (domain riêng có SSL). Bật nhầm khi proxy đang chạy HTTP sẽ kẹt vòng đăng nhập (nhập đúng mật khẩu vẫn bị đá về trang login). |

Về MÃ THIẾT LẬP: khi chạy public mà chưa có tài khoản admin, lần đầu mở app sẽ yêu cầu nhập một mã thiết lập. Mã này chỉ in ra log server lúc khởi động, nên chỉ người xem được log/terminal mới tạo được tài khoản, kẻ chỉ có URL không làm gì được. Nếu bạn đặt sẵn `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` thì khỏi cần mã này, cứ đăng nhập bằng tài khoản đã đặt. Xem thêm ở [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).

Về tên miền riêng và HTTPS: **không** đặt tên miền trong `.env`. Bạn bật Caddy (qua `docker-compose.https.yml`) rồi nhập tên miền trong app ở phần ⚙ Cài đặt, mục Tên miền riêng. Khi truy cập đúng tên miền qua HTTPS, server tự bật cookie Secure nên bạn cũng không cần đặt `JAVIS_SECURE_COOKIE` thủ công. Chi tiết ở [Thương hiệu & tên miền](15-thuong-hieu-ten-mien.md).

### Nhóm 4: Đường dẫn dữ liệu (Second Brain và state)

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `CLAUDE_CWD` | Thư mục làm việc của Claude CLI (nơi đọc file `CLAUDE.md` và kế thừa MCP) | Thư mục gốc dự án | Muốn Claude làm việc trong một thư mục khác. Docker thường đặt `/app`. |
| `OBSIDIAN_VAULT_PATH` | Đường dẫn vault Second Brain chính | `vault/` trong dự án (Docker: `/data/vault`) | Trên server đã có vault Obsidian thật thì trỏ biến này vào đó. Để trống thì Javis dùng vault mẫu trong repo (máy mới chạy được ngay). |
| `BRAIN_PATH` | Thư mục brain (bản cũ, chỉ dùng để migrate dữ liệu cũ) | `brain/` trong dự án (Docker: `/data/brain`) | Hầu như không cần đụng. Đây là đường dẫn brain đơn kiểu cũ, giữ lại để chuyển dữ liệu. |
| `BRAINS_DIR` | Thư mục cha chứa mọi brain, mỗi thư mục con là một Second Brain | `brains/` trong dự án | Muốn để nhiều brain ở nơi khác (ví dụ ổ dữ liệu riêng, mount git-backup). Docker thường mount `/brains`. |
| `SOURCES_PATH` | Nơi lưu file đính kèm từ chat (làm source cho Second Brain) | `brain/01 - Sources/` trong dự án | Muốn tách thư mục nguồn ra chỗ khác. |
| `JAVIS_STATE_DIR` | Nơi Javis ghi state riêng: `settings.json`, phiên đăng nhập, cấu hình loop | `server/` (Docker: `/data/state`) | Docker/VPS phải trỏ vào volume ghi được (vì cây mã nguồn trong container là chỉ đọc). Máy cá nhân để trống là được. |

Ghi chú về Second Brain: hai biến `OBSIDIAN_VAULT_PATH` và `BRAINS_DIR` là phần cấp dữ liệu cho đồ thị tri thức và bộ nhớ. Để trống là chạy được ngay với dữ liệu mẫu trong repo. Đọc thêm cách vận hành bộ nhớ ở [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) và [Đồ thị tri thức 3D](03-do-thi-tri-thuc-3d.md).

### Nhóm 5: Giọng đọc (TTS)

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `TTS_VOICE` | Giọng đọc mặc định (dùng Edge TTS miễn phí) | `vi-VN-HoaiMyNeural` | Muốn giọng khác. Ví dụ giọng nam tiếng Việt hoặc giọng tiếng nước ngoài. |
| `TTS_RATE` | Tốc độ đọc, dạng phần trăm cộng/trừ | `+5%` | Thấy đọc nhanh quá thì giảm (ví dụ `+0%` hoặc `-10%`), muốn nhanh hơn thì tăng (ví dụ `+15%`). |

Lưu ý: hai biến TTS này áp cho giọng Edge TTS miễn phí mặc định. Nếu bạn chọn dùng nhà cung cấp giọng khác (OpenAI TTS hoặc ElevenLabs), phần đó cấu hình trong bảng Cài đặt của app chứ không qua `.env`. Cách trò chuyện và bật giọng nói xem ở [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md).

### Nhóm 6: Cập nhật 1-click và các biến nâng cao

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `WATCHTOWER_TOKEN` | Token cho nút "Cập nhật ngay" (trang Cập nhật) gọi Watchtower khi chạy Docker | `javis-update` | Muốn chặt hơn: đổi thành chuỗi ngẫu nhiên, đặt cùng giá trị cho cả app lẫn service watchtower. |
| `METRICS_TTL` | Thời gian cache số liệu kinh doanh, tính bằng giây | `180` | Muốn số liệu MCP làm mới nhanh hơn hoặc chậm hơn. Xem [MCP & số liệu](09-mcp-va-so-lieu.md). |
| `JAVIS_CLAUDE_IDLE_TIMEOUT` | Thời gian chờ tối đa khi Claude/Codex IM LẶNG mà KHÔNG có tool nào đang chạy, tính bằng giây | `180` | Hiếm khi cần đổi - đây là lưới bắt phiên treo thật. |
| `JAVIS_CLAUDE_TOOL_TIMEOUT` | Trần chờ khi một TOOL đang chạy dở (render video, tách nền, build...), tính bằng giây | `3600` | Tác vụ tool chạy quá 1 tiếng (encode video dài, train model...) thì tăng lên. |
| `JAVIS_CLAUDE_ENGINE` | (Lịch sử) Từ 0.9.37 engine Claude luôn chạy qua Agent SDK chính chủ - biến này không còn tác dụng, đặt `cli`/`sdk-loops` sẽ bị bỏ qua kèm một dòng log | `sdk` | Không cần đụng. Engine Claude trục trặc thì báo lỗi kèm log server. |
| `JAVIS_FILES_ROOT` | Trần duyệt của trang Tệp tin (không cho bấm "Lên" quá đây). `brain`/`vault` = khoá trong brain; `drive`/`root` = cả ổ đĩa chứa brain; `<đường dẫn>` = một thư mục cụ thể (phải chứa brain) | localhost: cả ổ đĩa; bind public: khoá brain | Chạy public (VPS) mà vẫn muốn duyệt rộng thì đặt `drive` hoặc một thư mục cha. Muốn khoá chặt trong brain khi chạy local thì đặt `brain`. |
| `JAVIS_SESSIONS_DB` | Đường dẫn file cơ sở dữ liệu lưu phiên hội thoại (`conversations.db`) | Nằm trong `JAVIS_STATE_DIR` | Muốn để file lịch sử phiên ở nơi khác. Xem [Phiên hội thoại](04-phien-hoi-thoai.md). |

Các biến nhóm 6 hiếm khi cần đụng. `WATCHTOWER_TOKEN` chỉ liên quan khi bạn chạy bản Docker và muốn dùng nút cập nhật một chạm.

## Điểm cần nhớ về ANTHROPIC_API_KEY

Javis dùng đăng ký Claude Code CLI làm bộ não, nên **không cần** biến `ANTHROPIC_API_KEY` trong `.env`. Các MCP bạn cài vào Claude Code, Javis tự kế thừa. Nếu muốn dùng model qua nhà cung cấp khác (OpenRouter, OpenAI API, Anthropic API), bạn nhập khoá trong bảng Cài đặt của app ở trang Models, không đặt trong `.env`. Xem [Models & engine](10-models-va-engine.md).

## Ví dụ một file .env tối giản

Máy cá nhân, chỉ muốn đổi tên và tốc độ đọc, để nguyên phần còn lại:

```
WORKSPACE_NAME=Trợ lý của Quy
USER_NAME=Quy
TTS_RATE=+0%
```

Deploy public trên VPS, tạo sẵn admin và mở cho truy cập từ ngoài:

```
JAVIS_HOST=0.0.0.0
JAVIS_ADMIN_USER=admin
JAVIS_ADMIN_PASSWORD=doi-mat-khau-that-manh-o-day
OBSIDIAN_VAULT_PATH=/data/vault
JAVIS_STATE_DIR=/data/state
```

Ở ví dụ thứ hai, vì `JAVIS_HOST=0.0.0.0` (public) nên Javis tự bật bắt buộc đăng nhập, và vì đã có `JAVIS_ADMIN_PASSWORD` nên bạn đăng nhập luôn bằng tài khoản đó, khỏi cần MÃ THIẾT LẬP.

## Mẹo

1. Luôn giữ lại `env.example` làm bản gốc tham chiếu. Chỉ sửa `.env`.
2. Đổi biến trong `.env` xong phải khởi động lại Javis mới ăn. Khác với bảng Cài đặt trong app (đổi là ăn ngay).
3. Không chắc một biến làm gì thì cứ để nguyên dấu `#` (chú thích) cho an toàn. Mặc định đã chạy tốt.
4. Với các biến bật/tắt (`JAVIS_REQUIRE_LOGIN`, `JAVIS_SECURE_COOKIE`), giá trị bật chấp nhận `1`, `true`, `yes`, `on`. Giá trị tắt chấp nhận `0`, `false`, `no`, `off`.
5. File `.env` chứa mật khẩu và cấu hình nhạy cảm. Không đưa lên nơi công khai. Trên máy chung, đặt quyền đọc hạn chế.

## Sự cố thường gặp

**Sửa .env rồi mà không thấy đổi gì.** Bạn chưa khởi động lại Javis. `.env` chỉ đọc lúc khởi động. Tắt server rồi mở lại.

**Đổi cổng xong không vào được app.** Bạn đang mở trình duyệt ở cổng cũ. Ví dụ đổi `JAVIS_PORT=8080` thì phải mở `http://localhost:8080`, không phải `7777` nữa.

**Đăng nhập đúng mật khẩu nhưng cứ bị đá về trang login.** Nhiều khả năng bạn đã bật `JAVIS_SECURE_COOKIE=1` nhưng thực tế đang truy cập qua HTTP (không phải HTTPS). Cookie Secure chỉ gửi qua HTTPS nên trình duyệt không giữ được phiên. Xoá dòng đó hoặc đặt về tắt, khởi động lại.

**Mở app báo cần MÃ THIẾT LẬP mà không biết lấy ở đâu.** Mã in trong log server lúc khởi động. Với Docker, xem log container tìm dòng "SETUP TOKEN", hoặc đọc file `.setup_token` trong thư mục state. Cách gọn hơn: đặt sẵn `JAVIS_ADMIN_PASSWORD` trong `.env` để bỏ qua bước nhập mã.

**Đặt tên workspace trong .env mà app hiển thị tên khác.** App ưu tiên tên đã lưu trong Cài đặt hơn biến `WORKSPACE_NAME`. Sửa tên trong bảng Cài đặt của app, hoặc xoá tên đã lưu để app dùng lại giá trị từ `.env`.

**Trỏ OBSIDIAN_VAULT_PATH vào vault thật mà Javis không thấy dữ liệu.** Kiểm tra đường dẫn có đúng và Javis có quyền đọc thư mục đó không. Trên Docker phải mount đúng volume vào đường dẫn bạn khai. Sau khi sửa, khởi động lại và dựng lại đồ thị (xem [Đồ thị tri thức 3D](03-do-thi-tri-thuc-3d.md)).

Nếu còn vướng, xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
