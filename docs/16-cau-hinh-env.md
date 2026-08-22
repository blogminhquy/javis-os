# Cấu hình .env

Trang này liệt kê các biến môi trường mà Javis OS đọc lúc khởi động, kèm ý nghĩa, giá trị mặc định và khi nào cần đổi. Nội dung dựa vào file `env.example` và cách server thực sự đọc `os.getenv(...)` trong mã nguồn (`server/config.py`, `server/main.py`, `server/web_security.py`, `server/claude_cli.py`, `server/sessions.py`, `server/plugins_host.py`...).

Điểm quan trọng nhất cần nhớ: **mọi dòng để trống vẫn chạy được**. Trên máy cá nhân, bạn gần như không cần đụng tới file `.env`. Việc chỉnh `.env` chủ yếu dành cho khi bạn đưa Javis lên VPS/server public hoặc muốn đổi giọng đọc, cổng, đường dẫn dữ liệu.

Riêng khi cài bằng **Hostinger Docker Manager**, không cần nhìn thấy toàn bộ danh
sách nâng cao bên dưới. Compose Hostinger chỉ đưa 3 trường người dùng lên ô
Environment: `DOMAIN_NAME`, `JAVIS_ADMIN_USER`, `JAVIS_ADMIN_PASSWORD`. Các biến
nội bộ về cổng, state, brain và thư mục làm việc nằm sẵn trong Docker image.

## Tính năng này là gì

`.env` là một file văn bản đặt ở **thư mục gốc dự án** (nơi có `env.example`, `docker-compose.yml`, thư mục `server/`). Mỗi dòng là một biến dạng `TÊN_BIẾN=giá trị`. Khi Javis khởi động, nó đọc các biến này để biết: nghe ở cổng nào, có bắt buộc đăng nhập không, dữ liệu Second Brain nằm ở đâu, giọng đọc mặc định là gì.

Cần phân biệt rõ 3 nơi cấu hình để khỏi nhầm:

- **File `.env`**: các thiết lập cấp hệ thống, đọc 1 lần lúc khởi động. Đổi xong phải khởi động lại Javis mới có hiệu lực.
- **Bảng ⚙ Cài đặt trong app** (trang Tài khoản, Models, Kênh...): các thiết lập đổi nóng qua giao diện, lưu vào `settings.json`, không cần sửa file. Ví dụ: đổi model, khoá API OpenRouter, token Telegram, tên miền riêng, logo. Xem thêm ở [Models & engine](10-models-va-engine.md), [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md), [Thương hiệu & tên miền](15-thuong-hieu-ten-mien.md).
- **Vài khoá trong `settings.json` chưa có giao diện**: hiện có khối `media` (luật dọn ảnh/tệp tạm). Muốn đổi thì phải mở file sửa tay. Xem mục riêng bên dưới.

Nói gọn: `.env` lo phần "chạy ở đâu, ai được vào, dữ liệu nằm đâu". Bảng Cài đặt trong app lo phần "dùng model nào, khoá gì, giọng gì". Còn `settings.json` là nơi cả hai gặp nhau, và một vài khoá hiếm dùng chỉ sửa được ở đó.

## Mở ở đâu trong Javis

`.env` không có nút bấm trong dashboard. Đây là file bạn tự tạo và sửa bằng trình soạn thảo văn bản (Notepad, VS Code...).

Các bước tạo file `.env` lần đầu:

1. Mở thư mục gốc dự án (nơi bạn tải/giải nén Javis; bản Docker thì là `/app` bên trong image, còn `.env` đặt cạnh `docker-compose.yml` trên host).
2. Tìm file mẫu `env.example` (tên cố ý KHÔNG có dấu chấm đầu - để Docker Manager của Hostinger không tự quét file `.env*` rồi nhập cả dòng chú thích vào ô Environment).
3. Sao chép nó và đổi tên bản sao thành `.env` (bản sao CÓ dấu chấm đầu, không có phần đuôi `.txt`).
4. Mở `.env` bằng trình soạn thảo, bỏ dấu `#` ở đầu dòng biến bạn muốn bật, rồi điền giá trị.
5. Lưu file. Khởi động lại Javis.

Cách sao chép nhanh bằng lệnh (chạy trong thư mục dự án):

- Windows PowerShell: `Copy-Item env.example .env`
- Git Bash / Linux / macOS: `cp env.example .env`

Lưu ý về dấu `#`: dòng bắt đầu bằng `#` là dòng chú thích, Javis bỏ qua. Muốn bật một biến đang bị chú thích, xoá dấu `#` ở đầu dòng đó. Ví dụ đổi từ `# JAVIS_PORT=7777` thành `JAVIS_PORT=8080`.

## Danh sách các biến

Gom theo chức năng. Cột "Mặc định" là giá trị dùng khi bạn để trống hoặc không khai báo. Nhóm 1 đến 5 là những biến người dùng thường đụng; nhóm 6 và 7 là biến nâng cao, hầu như không cần sửa.

### Nhóm 1: Hiển thị workspace

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `WORKSPACE_NAME` | Tên workspace hiển thị trên dashboard | `Javis OS` | Muốn đặt tên riêng cho không gian làm việc. Lưu ý: nếu bạn đã đặt tên trong app thì app ưu tiên tên đã lưu, biến này chỉ là dự phòng. |
| `USER_NAME` | Tên người dùng hiển thị | `Bạn` | Muốn Javis xưng hô bằng tên bạn thay vì "Bạn". |

### Nhóm 2: Mạng (cổng và địa chỉ nghe)

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `JAVIS_HOST` | Địa chỉ server nghe. `127.0.0.1` = chỉ máy này truy cập được. `0.0.0.0` = nghe mọi nơi (public, ai có địa chỉ đều vào được) | `127.0.0.1` (Docker image đặt sẵn `0.0.0.0`) | Chỉ đổi sang `0.0.0.0` khi chạy trên VPS/server và muốn truy cập từ máy khác. Khi đó phải bật đăng nhập (xem nhóm 3). |
| `JAVIS_PORT` | Cổng nghe của dashboard | `7777` | Cổng `7777` bị chiếm hoặc muốn cổng khác. Đổi xong nhớ mở đúng cổng đó trên trình duyệt. |

Chi tiết quan trọng về `JAVIS_HOST`: Javis dùng cơ chế "an toàn mặc định". Nếu bạn để địa chỉ nghe KHÔNG phải loopback (tức khác `127.0.0.1`, `localhost`, `::1`), server tự coi là đang chạy public và **tự bật bắt buộc đăng nhập** để không ai vào được nếu chưa có tài khoản. Lý do: bộ não AI chạy với đầy quyền trên máy, để hở là nguy hiểm.

### Nhóm 3: Đăng nhập và bảo mật

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `JAVIS_REQUIRE_LOGIN` | Ép bật/tắt bắt buộc đăng nhập. `1`/`true`/`yes`/`on` = bật. `0`/`false`/`no`/`off` = tắt | Tự động (bật khi bind public) | Chạy localhost rồi expose ra ngoài qua tunnel (Cloudflare, ngrok...): đặt `JAVIS_REQUIRE_LOGIN=1` để chặn người lạ. |
| `JAVIS_ADMIN_USER` | Tên đăng nhập admin tạo sẵn lúc deploy | `admin` | Đặt cùng `JAVIS_ADMIN_PASSWORD` để tạo sẵn tài khoản, khỏi cần lấy MÃ THIẾT LẬP từ log. |
| `JAVIS_ADMIN_PASSWORD` | Mật khẩu admin tạo sẵn lúc deploy | (trống) | Deploy public: đặt mật khẩu mạnh ở đây. Có biến này và chưa có admin, Javis tạo tài khoản admin ngay lúc khởi động và đóng luôn màn hình tạo tài khoản (an toàn nhất cho public). |
| `JAVIS_SECURE_COOKIE` | Bật cookie chỉ gửi qua HTTPS. `1`/`true`/`yes`/`on` = bật | Tắt | Chỉ bật khi CHẮC CHẮN chạy HTTPS đầu-cuối (domain riêng có SSL). Bật nhầm khi proxy đang chạy HTTP sẽ kẹt vòng đăng nhập (nhập đúng mật khẩu vẫn bị đá về trang login). |
| `JAVIS_ALLOWED_HOSTS` | Thêm hostname được phép gọi Javis (chống CSRF và DNS-rebinding). Nhiều tên cách nhau dấu phẩy | (trống) | Chạy sau reverse proxy với tên miền chưa khai trong app mà chưa đặt mật khẩu, bị 403 "host không được phép". Mặc định đã cho `localhost`, `127.0.0.1`, `::1` và tên miền bạn đặt ở Cài đặt. |
| `JAVIS_ENABLE_USER_PLUGINS` | Cổng chặn CỨNG cho plugin do bạn cài. `true` mới nạp | Tắt | Bạn tự cài plugin (thư mục `plugins/` toàn cục hoặc trong brain) và muốn nó chạy. Plugin user chạy CODE PYTHON THẬT trong tiến trình server nên mặc định bị chặn. Alias cũ: `JAVIS_ENABLE_VAULT_PLUGINS`. Plugin đi kèm app (bundled) không chịu cổng này. Xem [Plugins](20-plugins.md). |
| `JAVIS_TERMINAL` | Công tắc tắt hẳn Terminal trong nhóm Code. `0`/`off`/`false`/`no` = tắt | Bật | Không muốn có dòng lệnh nào mở được từ trình duyệt. Terminal vốn đã chỉ mở cho trình duyệt ĐÃ ĐĂNG NHẬP (token API không vào được), nhưng nhiều người vẫn muốn khoá cứng ở tầng máy chủ. Xem [Nhóm Code: Terminal](27-tab-code-terminal.md). |
| `JAVIS_TERMINAL_SHELL` | Shell mà Terminal chạy | `$SHELL`, không có thì `bash`/`sh`. Windows: `powershell.exe` rồi `cmd.exe` | Muốn ép dùng một shell khác (`zsh`, `fish`, `cmd.exe`). |
| `JAVIS_TERMINAL_CWD` | Thư mục terminal mở ra | HOME của user chạy Javis | Muốn shell mở sẵn ở gốc brain hoặc một thư mục dự án khác. |

Về MÃ THIẾT LẬP: khi chạy public mà chưa có tài khoản admin, lần đầu mở app sẽ yêu cầu nhập một mã thiết lập. Mã này chỉ in ra log server lúc khởi động, nên chỉ người xem được log/terminal mới tạo được tài khoản, kẻ chỉ có URL không làm gì được. Nếu bạn đặt sẵn `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` thì khỏi cần mã này, cứ đăng nhập bằng tài khoản đã đặt. Xem thêm ở [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).

Về tên miền riêng và HTTPS: VPS dùng Caddy nhập tên miền ngay trong **Cài đặt → Giọng nói, thương hiệu & truy cập → Tên miền & SSL** rồi bấm **Bật SSL**. Riêng Hostinger, wizard tạo sẵn biến `DOMAIN_NAME` để sao chép sang Docker Manager rồi Redeploy. Khi truy cập đúng tên miền qua HTTPS, server tự bật cookie Secure nên không cần đặt `JAVIS_SECURE_COOKIE` thủ công. Chi tiết ở [Thương hiệu & tên miền](15-thuong-hieu-ten-mien.md).

### Nhóm 4: Đường dẫn dữ liệu (Second Brain và state)

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `CLAUDE_CWD` | Thư mục làm việc của engine CLI (nơi đọc file `CLAUDE.md` và kế thừa MCP) | Thư mục gốc dự án (Docker: `/app`) | Muốn engine làm việc trong một thư mục khác. |
| `BRAINS_DIR` | Thư mục cha chứa mọi brain, mỗi thư mục con là một Second Brain. Brain mặc định là `<BRAINS_DIR>/Brain Default` | `brains/` trong dự án (Docker: `/brains`) | Muốn để nhiều brain ở nơi khác (ví dụ ổ dữ liệu riêng, mount git-backup). |
| `OBSIDIAN_VAULT_PATH` | Đường dẫn vault Second Brain chính | `vault/` trong dự án (Docker: `/data/vault`) | Trên server đã có vault Obsidian thật thì trỏ biến này vào đó. Để trống thì Javis dùng vault mẫu trong repo (máy mới chạy được ngay). |
| `BRAIN_PATH` | Thư mục brain kiểu cũ, thời một-brain. Chỉ còn để migrate dữ liệu cũ | `brain/` trong dự án (Docker: `/data/brain`) | Hầu như không cần đụng. Đừng dùng cho cài mới. |
| `SOURCES_PATH` | Nơi lưu file đính kèm từ chat (làm source cho Second Brain) | `brain/01 - Sources/` trong dự án | Muốn tách thư mục nguồn ra chỗ khác. |
| `JAVIS_STATE_DIR` | Nơi Javis ghi state riêng: `settings.json`, phiên đăng nhập, cấu hình việc định kỳ, khoá mã hoá `.secret_key`, cơ sở dữ liệu hội thoại | `server/` (Docker: `/data/state`) | Docker/VPS phải trỏ vào volume ghi được (vì cây mã nguồn trong container là chỉ đọc). Máy cá nhân để trống là được. |
| `JAVIS_SESSIONS_DB` | Đường dẫn file cơ sở dữ liệu lưu phiên hội thoại (`conversations.db`) | Nằm trong `JAVIS_STATE_DIR` | Muốn để file lịch sử phiên ở nơi khác. Xem [Phiên hội thoại](04-phien-hoi-thoai.md). |
| `JAVIS_FILES_ROOT` | Trần duyệt của trang Tệp tin (không cho bấm "Lên" quá đây). `brain`/`vault` = khoá trong brain; `drive`/`root` = cả ổ đĩa chứa brain; `<đường dẫn>` = một thư mục cụ thể (phải chứa brain) | localhost: cả ổ đĩa; bind public: khoá brain | Chạy public (VPS) mà vẫn muốn duyệt rộng thì đặt `drive` hoặc một thư mục cha. Muốn khoá chặt trong brain khi chạy local thì đặt `brain`. |

Ghi chú về Second Brain: `BRAINS_DIR` là thư mục thật sự chứa các brain của bạn (không phải `brain/` ở gốc repo, đó là đường dẫn kiểu cũ). Để trống là chạy được ngay với dữ liệu mẫu trong repo. Đọc thêm cách vận hành bộ nhớ ở [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) và [Đồ thị tri thức](03-do-thi-tri-thuc.md).

**Cảnh báo về `.secret_key`:** trong thư mục `JAVIS_STATE_DIR` có một tệp nhỏ tên `.secret_key`. Nó là khoá dùng để mã hoá các trường bí mật trong `settings.json` (API key OpenRouter/Anthropic/OpenAI/Gemini, token đăng nhập ChatGPT, token Telegram, token GitHub sao lưu, key ElevenLabs). Chép `settings.json` sang máy khác mà quên `.secret_key` thì **mọi khoá mất trắng**: Javis không giải mã được nên trả về chuỗi rỗng và bạn phải nhập lại từng cái. Sao lưu thì sao lưu cả cặp. Nếu máy thiếu thư viện `cryptography`, Javis không mã hoá được: secret rơi về tiền tố `plain:` kèm một dòng cảnh báo trong log; cài `pip install cryptography` rồi khởi động lại là xong. Chi tiết ở [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).

### Nhóm 5: Giọng đọc (TTS)

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `TTS_VOICE` | Giọng đọc mặc định (dùng Edge TTS miễn phí) | `vi-VN-HoaiMyNeural` | Muốn giọng khác. Ví dụ giọng nam tiếng Việt hoặc giọng tiếng nước ngoài. |
| `TTS_RATE` | Tốc độ đọc, dạng phần trăm cộng/trừ | `+5%` | Thấy đọc nhanh quá thì giảm (ví dụ `+0%` hoặc `-10%`), muốn nhanh hơn thì tăng (ví dụ `+15%`). |

Lưu ý: hai biến TTS này áp cho giọng Edge TTS miễn phí mặc định. Nếu bạn chọn dùng nhà cung cấp giọng khác (OpenAI TTS hoặc ElevenLabs), phần đó cấu hình trong bảng Cài đặt của app chứ không qua `.env`. Cách trò chuyện và bật giọng nói xem ở [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md).

### Nhóm 6: Deploy, tên miền và cập nhật

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `DOMAIN_NAME` | Tên miền mà reverse proxy (Traefik của Hostinger) định tuyến về Javis. Javis đọc để đối chiếu với tên miền bạn nhập trong app và biết có cần Redeploy không | (trống; compose Hostinger đặt `localhost`) | Deploy Hostinger: đặt bằng tên miền của bạn trong Docker Manager rồi Redeploy. Wizard trong app có nút **Sao chép biến** để copy sẵn dòng này. |
| `JAVIS_DEPLOY_TARGET` | Khai rõ đang chạy ở môi trường nào: `hostinger`, `vps`, `native`, `windows` | Tự đoán (hostname `.hstgr.cloud` = hostinger; chạy Docker = vps) | Hầu như không cần đặt tay. Compose Hostinger đã đặt sẵn `hostinger`. Đặt khi Javis đoán sai môi trường và wizard tên miền hiện sai hướng dẫn. |
| `WATCHTOWER_TOKEN` | Token cho nút "Cập nhật ngay" (trang **Cập nhật**) gọi Watchtower khi chạy Docker | Trong `docker-compose.yml`: `javis-update`. Ngoài Docker: trống (không có biến thì Javis coi như Watchtower không chạy) | Muốn chặt hơn: đổi thành chuỗi ngẫu nhiên, đặt cùng giá trị cho cả app lẫn service watchtower. |

### Nhóm 7: Biến nâng cao (hiếm khi cần đụng)

| Biến | Ý nghĩa | Mặc định | Khi nào đổi |
|---|---|---|---|
| `JAVIS_CLAUDE_IDLE_TIMEOUT` | Trần chờ khi engine đã trả lời rồi im giữa chừng mà KHÔNG có tool nào đang chạy, tính bằng giây. `0` = không giới hạn | `0` | Mặc định bỏ trần: engine im lặng KHÔNG có nghĩa là treo (model suy nghĩ ở mức nỗ lực cao, hoặc đang soạn nội dung một file dài để ghi ra, đều im hàng phút). Chỉ đặt số dương nếu bạn thật sự cần cắt lượt tự động. |
| `JAVIS_CLAUDE_FIRST_TIMEOUT` | Trần chờ chữ ĐẦU TIÊN của một lượt, tính bằng giây. `0` = không giới hạn | `0` | Cùng lý do với biến trên: hội thoại dài thì lượt đầu phải nạp lại toàn bộ ngữ cảnh nên lâu. |
| `JAVIS_CLAUDE_TOOL_TIMEOUT` | Trần chờ khi một TOOL đang chạy dở (render video, tách nền, build...), tính bằng giây. `0` = không giới hạn | `3600` | Trần này giữ lại vì nó đo một tiến trình con CÓ THẬT đang sống, không phải đo sự im lặng. Tác vụ chạy quá 1 tiếng (encode video dài, train model...) thì tăng lên. |
| `JAVIS_CODEX_SANDBOX` | Có dùng rào sandbox riêng của Codex (ChatGPT) cho việc nền không. `auto` = có, khớp mức quyền của việc (suggest thành read-only, auto thành workspace-write). `off` = không đặt rào riêng | `auto`, nhưng **ảnh Docker đặt sẵn `off`** | Codex bọc lệnh đọc/ghi file bằng bubblewrap, mà bubblewrap không khởi động nổi trong container (user thường, không có CAP_SYS_ADMIN, Ubuntu 24.04 còn chặn user namespace bằng AppArmor) nên rào đó không phải chặt hơn mà là chết hẳn - mọi việc nền chạy bằng ChatGPT đều không đọc nổi một file nào. Chạy ngoài Docker thì để `auto`. Đánh đổi khi `off`: Codex không có allowlist per-call như Claude nên mức `suggest` mất thứ chặn nó ghi file; rào tiền/đơn/đăng bài/gửi tin KHÔNG bị ảnh hưởng vì chúng nằm ở MCP Hub. |
| `JAVIS_AGY_PROMPT_DAI` | Ép cách Javis đưa prompt cho Antigravity CLI khi prompt dài hơn trần dòng lệnh: `stdin` (bơm qua ống dẫn), `file` (ghi ra file rồi bảo model tự đọc), `argv` (nhét thẳng vào dòng lệnh) | (trống, Javis tự chọn: stdin trước, hỏng thì tự lui về file) | Chỉ khi máy bạn gặp ca lạ. Windows chặn tổng dòng lệnh ở 32767 ký tự trong khi system prompt của Javis đã hơn 36.000, nên `argv` ở đó là chắc chắn gãy. Xem [Models & engine](10-models-va-engine.md). |
| `JAVIS_AGY_TIMEOUT` | Trần thời gian một lượt chạy của Antigravity CLI, tính bằng giây. Javis truyền luôn số này xuống `--print-timeout` của chính CLI | `900` | Việc nền dài bị cắt ngang thì tăng. Không đặt thì `agy` tự cắt ở phút thứ 5 và trả về câu dở dang chứ không báo lỗi. |
| `JAVIS_MAX_TOOL_ROUNDS` | Số vòng gọi tool tối đa cho MỘT lượt trả lời của các engine dùng API key (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama). Bị kẹp trong khoảng 1 đến 40 | `8` | Việc nền nhiều bước (đọc vài file, tra vài nguồn rồi ghi kết quả) hay dừng giữa chừng kèm câu "đã chạy hết N vòng gọi tool" thì tăng lên 15-20. Đổi xong phải khởi động lại Javis. Claude Code và Codex KHÔNG chịu trần này - chúng tự quản vòng lặp của mình. |
| `JAVIS_KANBAN_MAX_WORKERS` | Số việc Kanban chạy song song. Bị kẹp trong khoảng 1 đến 8 | `2` | VPS khoẻ và hàng việc dài thì tăng; máy yếu hoặc hay nghẽn thì để `1`. Xem [Việc / Kanban](21-viec-kanban.md). |
| `JAVIS_MEMORY_INDEX_MAX` | Trần ký tự của chỉ mục bộ nhớ (`MEMORY.md`) nạp vào mọi lượt chat. Vượt trần thì Javis rút gọn dần mô tả chứ không bỏ ký ức | `20000` | Bộ nhớ quá dày làm mỗi lượt chat tốn token; muốn siết thì hạ số này. Xem [Second Brain](13-second-brain-bo-nho-wiki.md). |
| `JAVIS_CLAUDE_ENGINE` | (Lịch sử) Từ 0.9.37 engine Claude luôn chạy qua Agent SDK chính chủ - biến này không còn tác dụng, đặt `cli`/`sdk-loops` sẽ bị bỏ qua kèm một dòng log | `sdk` | Không cần đụng. Engine Claude trục trặc thì báo lỗi kèm log server. |
| `JAVIS_CODEX_BIN` | Đường dẫn tuyệt đối tới file thực thi `codex` | Tự dò trong PATH và các chỗ cài quen thuộc | Cài Codex CLI ở nơi lạ mà Javis không tìm ra. |
| `CLAUDE_CONFIG_DIR` | Thư mục cấu hình của Claude Code (nơi có `.credentials.json`). Đặt biến này là ĐÈ hẳn, giống hành vi của Claude Code | `~/.claude` | Bạn đã tự đổi thư mục cấu hình Claude Code. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Token OAuth của Claude Code, dùng để hỏi danh sách model thật từ Anthropic | (trống, đọc từ file credentials) | Môi trường không có file credentials (CI, container tối giản) mà vẫn muốn danh sách model động. |
| `JAVIS_CLAUDE_PROJECTS_DIR` | Nơi Javis đọc log phiên Claude Code để tính **Mức dùng** | `~/.claude/projects` | Log Claude Code nằm chỗ khác. Xem [Mức dùng: token & chi phí](23-muc-dung-token.md). |
| `JAVIS_CODEX_SESSIONS_DIR` | Nơi Javis đọc log phiên Codex để tính **Mức dùng** | `~/.codex/sessions` | Log Codex nằm chỗ khác. |
| `JAVIS_YOUTUBE_PROXY` | Proxy RIÊNG cho phần đọc phụ đề YouTube, dạng `http://user:mat-khau@may-chu:cong`. Chỉ lưu lượng đi YouTube mới qua đây | (trống, đi thẳng) | Javis báo "YouTube nghi máy chủ này là robot" lặp đi lặp lại. Gốc rễ của lỗi đó là **danh tiếng địa chỉ IP**: YouTube đánh dấu dải IP của các nhà cung cấp máy chủ (AWS, Google Cloud, Azure, VPS giá rẻ), nên cùng một đoạn mã chạy ở nhà thì trôi chảy còn chạy trên VPS thì bị hỏi giấy. Trỏ qua một proxy dân cư là đứng ở chỗ khác trên Internet. Đừng dùng `HTTPS_PROXY` của hệ thống cho việc này: nó đẩy **toàn bộ** lưu lượng của Javis qua đó, gồm cả gọi model và MCP, vừa chậm vừa lộ dữ liệu cho bên thứ ba. Xem [Trò chuyện](02-tro-chuyen-va-giong-noi.md). |
| `JAVIS_IMAGE_HOST_MODEL` | Model chat "chủ" dùng để gọi tool tạo ảnh qua gói ChatGPT | `gpt-5.5` | Nhà cung cấp đổi tên model làm chức năng tạo ảnh hỏng. |
| `JAVIS_IMAGE_MODEL` | Model sinh ảnh thật sự | `gpt-image-2` | Như trên. |

Ghi chú: `JAVIS_ENABLE_USER_PLUGINS` cũng là biến nâng cao nhưng vì nó là rào bảo mật nên đã nằm ở nhóm 3.

## Khối `media` trong settings.json (không có giao diện)

Thư mục `attachments/` và `inbox/` của mỗi brain là **vùng cache**, không phải kho tri thức: ảnh là nguyên liệu đi qua, đọc xong rút thành `.md` là đủ. Vì thế Javis tự dọn chúng theo tuổi và theo dung lượng, sáu tiếng quét một lần. Thư mục stage tạm (nơi tệp bạn dán vào khung chat rơi xuống) có hạn riêng, ngắn hơn hẳn.

Luật dọn này **chưa có ô nào trong Cài đặt**. Muốn đổi, mở `settings.json` trong thư mục state (máy cá nhân: `server/settings.json`; Docker: `/data/state/settings.json`) và sửa khối `media`:

```json
"media": {
  "enabled": true,
  "max_age_days": 30,
  "max_mb": 300,
  "staging_days": 3
}
```

| Khoá | Ý nghĩa | Mặc định |
|---|---|---|
| `enabled` | `false` = không dọn gì cả | `true` |
| `max_age_days` | Tệp media cũ hơn số ngày này bị xoá. Đặt `0` hoặc số âm = tắt luật tuổi | `30` |
| `max_mb` | Trần dung lượng vùng media của mỗi brain, tính bằng MB. Đặt `0` hoặc số âm = tắt luật dung lượng | `300` |
| `staging_days` | Hạn riêng cho thư mục stage tạm trong thư mục state | `3` |

Sửa xong phải khởi động lại Javis. Ảnh đã bị dọn mà vẫn còn được nhắc trong hội thoại cũ sẽ hiện thành một ô xám báo ảnh đã hết hạn, không phải icon vỡ. Muốn giữ ảnh lâu dài thì đấu một kho ngoài (ví dụ Drive) qua trang **Kết nối**, đừng để Javis ôm.

## Điểm cần nhớ về ANTHROPIC_API_KEY

Javis dùng chính **gói subscription** bạn đang trả làm bộ não (Claude Code cho gói Claude, Codex cho gói ChatGPT), nên **không cần** biến `ANTHROPIC_API_KEY` trong `.env`. Các MCP bạn cài vào Claude Code, Javis tự kế thừa. Nếu muốn dùng model qua nhà cung cấp API (OpenRouter, OpenAI API, Anthropic API, Google Gemini API, Groq API), bạn nhập khoá trong app ở trang **Models**, không đặt trong `.env`. Khoá nhập ở đó được mã hoá trước khi lưu xuống `settings.json`. Xem [Models & engine](10-models-va-engine.md).

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
JAVIS_ALLOWED_HOSTS=javis.tencuaban.com
```

Ở ví dụ thứ hai, vì `JAVIS_HOST=0.0.0.0` (public) nên Javis tự bật bắt buộc đăng nhập, và vì đã có `JAVIS_ADMIN_PASSWORD` nên bạn đăng nhập luôn bằng tài khoản đó, khỏi cần MÃ THIẾT LẬP.

## Mẹo

1. Luôn giữ lại `env.example` làm bản gốc tham chiếu. Chỉ sửa `.env`.
2. Đổi biến trong `.env` xong phải khởi động lại Javis mới ăn. Khác với bảng Cài đặt trong app (đổi là ăn ngay).
3. Không chắc một biến làm gì thì cứ để nguyên dấu `#` (chú thích) cho an toàn. Mặc định đã chạy tốt.
4. Với các biến bật/tắt (`JAVIS_REQUIRE_LOGIN`, `JAVIS_SECURE_COOKIE`, `JAVIS_ENABLE_USER_PLUGINS`), giá trị bật chấp nhận `1`, `true`, `yes`, `on`. Giá trị tắt chấp nhận `0`, `false`, `no`, `off`.
5. File `.env` chứa mật khẩu và cấu hình nhạy cảm. Không đưa lên nơi công khai. Trên máy chung, đặt quyền đọc hạn chế. Tệp `.secret_key` trong thư mục state cũng vậy, và nó còn quan trọng hơn: mất là mất luôn mọi API key đã lưu.
6. Bật `JAVIS_ENABLE_USER_PLUGINS=true` là một quyết định có trọng lượng: plugin do bạn cài chạy code Python thật trong tiến trình server. Chỉ bật khi bạn biết rõ từng plugin trong thư mục `plugins/` đến từ đâu.

## Sự cố thường gặp

**Sửa .env rồi mà không thấy đổi gì.** Bạn chưa khởi động lại Javis. `.env` chỉ đọc lúc khởi động. Tắt server rồi mở lại.

**Đổi cổng xong không vào được app.** Bạn đang mở trình duyệt ở cổng cũ. Ví dụ đổi `JAVIS_PORT=8080` thì phải mở `http://localhost:8080`, không phải `7777` nữa.

**Đăng nhập đúng mật khẩu nhưng cứ bị đá về trang login.** Nhiều khả năng bạn đã bật `JAVIS_SECURE_COOKIE=1` nhưng thực tế đang truy cập qua HTTP (không phải HTTPS). Cookie Secure chỉ gửi qua HTTPS nên trình duyệt không giữ được phiên. Xoá dòng đó hoặc đặt về tắt, khởi động lại.

**Mọi thao tác trả 403 "host không được phép".** Bạn vào Javis bằng một tên miền chưa nằm trong allowlist, trong lúc chưa đặt mật khẩu. Thêm tên miền vào `JAVIS_ALLOWED_HOSTS` (hoặc nhập nó ở Cài đặt → Tên miền & SSL), hoặc đơn giản là đặt mật khẩu.

**Đã bật plugin trong app rồi mà nó vẫn không chạy.** Plugin do bạn cài cần thêm biến `JAVIS_ENABLE_USER_PLUGINS=true` trong `.env` rồi khởi động lại. Trong app, Javis cũng ghi rõ câu này khi bạn bật một plugin đang bị chặn.

**Mở app báo cần MÃ THIẾT LẬP mà không biết lấy ở đâu.** Mã in trong log server lúc khởi động. Với Docker, xem log container tìm dòng "SETUP TOKEN", hoặc đọc file `.setup_token` trong thư mục state. Cách gọn hơn: đặt sẵn `JAVIS_ADMIN_PASSWORD` trong `.env` để bỏ qua bước nhập mã.

**Đặt tên workspace trong .env mà app hiển thị tên khác.** App ưu tiên tên đã lưu trong Cài đặt hơn biến `WORKSPACE_NAME`. Sửa tên trong bảng Cài đặt của app, hoặc xoá tên đã lưu để app dùng lại giá trị từ `.env`.

**Trỏ OBSIDIAN_VAULT_PATH vào vault thật mà Javis không thấy dữ liệu.** Kiểm tra đường dẫn có đúng và Javis có quyền đọc thư mục đó không. Trên Docker phải mount đúng volume vào đường dẫn bạn khai. Sau khi sửa, khởi động lại và dựng lại đồ thị (xem [Đồ thị tri thức](03-do-thi-tri-thuc.md)).

**Khôi phục backup xong thì mọi API key trống trơn.** Bạn chép `settings.json` mà không chép `.secret_key` cùng thư mục. Không khôi phục được, phải nhập lại key ở trang Models và Kênh.

Nếu còn vướng, xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

## Liên quan

- [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md)
- [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md)
- [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md)
- [Models & engine](10-models-va-engine.md)
- [Plugins](20-plugins.md)
- [Mức dùng: token & chi phí](23-muc-dung-token.md)
