# Khắc phục sự cố & FAQ

Trang này gom các trục trặc hay gặp khi dùng Javis OS và cách xử lý từng bước. Phần lớn sự cố chỉ cần một trong hai thao tác: khởi động lại server, hoặc tải lại trình duyệt bằng Ctrl+Shift+R. Cuối trang có mục Câu hỏi thường gặp (FAQ) ngắn gọn.

Nếu bạn mới cài Javis lần đầu, xem trước [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md). Nếu bạn đang chỉnh biến môi trường, xem [Cấu hình .env](16-cau-hinh-env.md).

## Trước khi đọc: hai thao tác cứu hộ hay dùng nhất

Rất nhiều lỗi biến mất sau một trong hai việc này, nên thử trước khi lo lắng:

1. **Khởi động lại server (khi bạn hoặc bản cập nhật vừa đổi code Python `.py`).**
   - Trên **Windows**: chạy `stop-javis.bat` để tắt, rồi chạy `start-javis.vbs` (chạy ngầm) hoặc `setup.bat` (hiện cửa sổ) để bật lại.
   - Trên **Docker / VPS**: `docker compose restart`.
   - Trên **Linux (systemd)**: `sudo systemctl restart javis`.
2. **Tải lại giao diện sạch bộ nhớ đệm (khi màn hình hiện sai, thiếu nút, hoặc bạn vừa đổi giao diện).** Nhấn **Ctrl+Shift+R** trên trình duyệt (Mac: Cmd+Shift+R). Đây là "hard refresh", buộc trình duyệt tải lại toàn bộ file giao diện thay vì dùng bản cũ trong cache.

> Quy tắc đơn giản để nhớ: đổi phần lõi (file `.py`) thì **restart server**; giao diện hiển thị sai thì **Ctrl+Shift+R**.

## Bảng sự cố thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Sửa code (hoặc vừa cập nhật) mà **không thấy đổi** | Nếu đổi file `.py`: **khởi động lại server** (Windows: `stop-javis.bat` rồi `start-javis.vbs`; Docker: `docker compose restart`). Nếu chỉ đổi giao diện: nhấn **Ctrl+Shift+R**. |
| **Cổng 7777 bị giữ**, bản mới không lên được | Tắt tiến trình cũ TRƯỚC rồi mới bật lại. Windows: chạy `stop-javis.bat`, hoặc `taskkill /F /PID <pid>` với PID đang giữ cổng. Docker: `docker compose down` rồi `docker compose up -d`. |
| **Hostinger không pull được image** | Đặt package GHCR ở chế độ **Public** (GitHub, repo, mục Packages, chọn `javis-os`, Package settings, Visibility = Public). Sau đó đợi GitHub Action build xong (xem tab Actions của repo) rồi Deploy lại. |
| Mở app **báo cần MÃ THIẾT LẬP** | Lấy mã trong App terminal của container: `cat /data/state/.setup_token`. Nếu chạy trên host: `docker compose logs javis` rồi tìm dòng có `SETUP TOKEN`. Cách khỏi cần mã: đặt sẵn env `JAVIS_ADMIN_USER` và `JAVIS_ADMIN_PASSWORD` lúc deploy để đăng nhập luôn. |
| **Claude báo chưa đăng nhập** (Javis không trả lời được) | Đăng nhập lại "bộ não" Claude 1 lần. Cách trong app: mở **Models**, ở thẻ Claude Code bấm **Đăng nhập Claude**, mở link, dán code nếu được yêu cầu. Cách bằng lệnh: `claude auth login --claudeai` (Docker: chạy trong App terminal). |
| **Trang Tệp tin báo lỗi ở "Đang tải..."** | Máy chủ chưa có endpoint Tệp tin (báo lỗi 404). **Khởi động lại server** để nạp endpoint mới, rồi nhấn **Ctrl+Shift+R**. |
| Ảnh trong hội thoại cũ hiện ô xám **Ảnh đã hết hạn** | Đúng thiết kế: `attachments/` và `inbox/` là vùng cache, file quá 30 ngày (hoặc khi vượt trần 300MB) bị dọn. Xem mục "Ảnh và file cũ biến mất" bên dưới để biết cách giữ lại hoặc tắt hẳn. |
| Voice / micro không bật được | Trình duyệt chỉ cấp quyền micro trên **HTTPS** (hoặc localhost). Mở qua `http://<ip>:7777` sẽ luôn bị chặn. Dùng URL `https://` (Hostinger `*.hstgr.cloud`, Cloudflare Tunnel, hoặc tên miền riêng có SSL). Xem [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md). |
| Cập nhật trong app xong mà **phiên bản không đổi** | Đợi thêm; nếu vẫn báo bản cũ, kiểm tra log cập nhật: `update.log` trong thư mục state (`server/update.log` khi chạy local, `/data/state/update.log` trên Docker), hoặc `docker compose logs`. |
| **`javis` báo 401** hoặc "token không hợp lệ" | Token sai hoặc đã bị thu hồi. Tạo cái mới ở **Tài khoản > Token API** rồi `javis login <địa-chỉ>` lại. Xem [Javis CLI](24-cli-terminal.md). |
| **`javis task add` / `javis brain ls` báo 403** | Token của bạn là loại **chỉ chat**. Những lệnh này cần token **toàn quyền** - tạo thêm một cái ở Tài khoản > Token API. |
| **`javis up` báo không thấy bản cài Javis** | Đúng như nó nói: gói CLI KHÔNG chứa server bên trong. Đặt `JAVIS_HOME` trỏ tới thư mục Javis, chạy lệnh từ trong thư mục đó, hoặc `javis login <địa-chỉ>` để nối tới một Javis đang chạy nơi khác. |

Các mục dưới đây giải thích chi tiết hơn từng dòng trong bảng.

## Sửa code mà không thấy đổi

Javis gồm hai phần chạy khác nhau, nên cách làm mới cũng khác:

1. **Đổi phần lõi (file Python `.py` trong `server/`)**: server đang chạy vẫn giữ bản cũ trong bộ nhớ. Bạn phải **tắt và bật lại server**:
   - Windows: chạy `stop-javis.bat`, đợi vài giây, rồi chạy `start-javis.vbs`.
   - Docker / VPS: `docker compose restart`.
   - Linux systemd: `sudo systemctl restart javis`.
2. **Đổi phần giao diện (HTML/CSS/JS trong `dashboard/`)**: server không cần restart, nhưng trình duyệt hay giữ bản cũ trong cache. Nhấn **Ctrl+Shift+R** để tải lại sạch.

Nếu làm cả hai vẫn không đổi, kiểm tra bạn có đang mở đúng cổng và đúng brain hay không.

## Cổng 7777 bị giữ, bản mới không lên

Cổng mặc định của Javis là **7777**. Khi một tiến trình cũ chưa tắt hẳn mà bạn bật bản mới, bản mới sẽ báo lỗi vì cổng đang bận. Xử lý theo thứ tự:

1. Tắt tiến trình cũ trước. Windows: chạy `stop-javis.bat`. Nếu vẫn còn, tìm PID đang giữ cổng rồi `taskkill /F /PID <pid>`. Docker: `docker compose down`.
2. Bật lại. Windows: `start-javis.vbs`. Docker: `docker compose up -d`.

Muốn đổi sang cổng khác (khi 7777 đụng phần mềm khác), đặt biến `JAVIS_PORT` trong file `.env`; xem [Cấu hình .env](16-cau-hinh-env.md).

## Hostinger không pull được image

Khi deploy bằng Hostinger Docker Manager mà nó không tải được image, thường do hai nguyên nhân:

1. **Image ở chế độ riêng tư (Private).** Vào GitHub, mở repo, chọn mục **Packages**, chọn `javis-os`, vào **Package settings**, đặt **Visibility = Public**. Có vậy Hostinger mới pull được mà không cần đăng nhập registry.
2. **Image chưa build xong.** Mỗi lần đẩy code mới lên nhánh `main`, GitHub Action mới bắt đầu build. Mở tab **Actions** của repo, đợi lượt build gần nhất chạy xong (dấu tích xanh), rồi bấm Deploy lại trên Hostinger.

## Mở app báo cần MÃ THIẾT LẬP

Khi Javis chạy public (Docker/VPS/Hostinger), lần đầu mở app sẽ ra màn tạo tài khoản admin và có thể hỏi **MÃ THIẾT LẬP**. Đây là cơ chế chống người lạ chỉ có URL cũng tạo được tài khoản (vì engine chạy toàn quyền trên máy). Lấy mã như sau:

1. **Trong App terminal của container** (terminal này ở BÊN TRONG container nên không có lệnh `docker`): chạy `cat /data/state/.setup_token`, copy chuỗi, dán vào ô MÃ THIẾT LẬP.
2. **Trên host (ngoài container)**: chạy `docker compose logs javis` rồi tìm dòng có chữ `SETUP TOKEN`.
3. **Khỏi cần mã**: đặt sẵn admin lúc deploy bằng hai env `JAVIS_ADMIN_USER` và `JAVIS_ADMIN_PASSWORD` trong compose. Khi đó mở app là đăng nhập luôn, không hỏi mã.

Chi tiết bảo mật và cách đặt mật khẩu xem [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).

## Claude báo chưa đăng nhập

Khi bạn chạy engine Claude, Javis mượn đúng phiên đăng nhập của `claude` CLI trên máy: đăng nhập 1 lần và giữ qua mọi restart/update. Nếu Javis không trả lời hoặc báo chưa đăng nhập:

1. **Cách trong giao diện:** mở **Models** (nhóm **Kết nối** trên thanh nav trái). Ở thẻ Claude Code, dòng trạng thái sẽ hiện **○ Chưa đăng nhập**. Bấm **Đăng nhập Claude**, app hiện một link; mở link để đăng nhập claude.ai; nếu trang hiện một mã code thì dán vào ô rồi bấm **Gửi code**. Khi xong, trạng thái đổi thành **● Đã kết nối**. Có nút **↻ Kiểm tra lại** để làm mới trạng thái.
2. **Cách bằng lệnh:** chạy `claude auth login --claudeai` một lần (trên Docker thì chạy trong **App terminal**), mở link, dán code.

Token đăng nhập nằm trong `~/.claude` (Docker: volume `claude-auth`) nên không mất khi update. Nếu đã đăng nhập trên máy khác, có thể copy thư mục `~/.claude` sang. Xem thêm [Models & engine](10-models-va-engine.md).

## Trang Tệp tin báo lỗi ở "Đang tải..."

Nếu vào **Tệp tin** (nhóm **Bộ não**) mà chỗ danh sách file báo lỗi thay vì lên danh sách, thường do máy chủ đang chạy bản cũ chưa có endpoint Tệp tin (lỗi 404). Bản thân giao diện sẽ nhắc: hãy **khởi động lại server** (Windows: `stop-javis.bat` rồi `start-javis.vbs`) rồi **tải lại trang** bằng Ctrl+Shift+R.

Nếu hiện dòng báo phiên đăng nhập hết hạn (lỗi 401), chỉ cần tải lại trang và đăng nhập lại. Hướng dẫn dùng Tệp tin đầy đủ ở [Quản lý tệp tin](05-quan-ly-tep-tin.md).

## Ảnh và file cũ biến mất (ô xám "Ảnh đã hết hạn")

Cuộn lại một hội thoại cũ mà thấy chỗ ảnh chỉ còn một ô xám ghi **Ảnh đã hết hạn**, hoặc file bạn từng gửi lên không mở được nữa: đây là hành vi cố ý, không phải lỗi.

Hai thư mục `attachments/` và `inbox/` của brain (ảnh Javis tạo, file bạn gửi qua chat hoặc Telegram) được coi là **vùng cache**, không phải tri thức. Tri thức là file `.md`. Javis tự dọn chúng theo hai luật:

| Luật | Mặc định | Ý nghĩa |
|---|---|---|
| Tuổi file | 30 ngày | File trong `attachments/` + `inbox/` già hơn ngần này bị xoá. |
| Trần dung lượng | 300 MB | Nếu tổng vùng cache vượt trần, xoá từ cũ tới mới cho tới khi xuống dưới trần. |
| Thư mục stage tạm | 3 ngày | Nơi file bạn dán/tải lên khung chat rơi xuống trước khi engine đọc (`.staging` trong thư mục state). Ở đây file `.md` cũng bị dọn. |

Lượt dọn chạy nền **6 tiếng một lần**. File `.md` lạc trong `attachments/` và `inbox/` thì **không bao giờ bị xoá** (chỉ riêng thư mục stage tạm là dọn cả `.md`).

**Muốn giữ lâu dài:** đừng để ảnh nằm trong vùng cache. Đọc xong thì rút nội dung ra note `.md` trong brain, hoặc đưa file sang một thư mục khác của brain (chỉ `attachments/`, biến thể của nó, và `inbox/` mới bị dọn), hoặc lưu ở kho ngoài.

**Muốn tắt hẳn việc dọn:** mở file `settings.json` trong thư mục state (`server/settings.json` khi chạy local, `/data/state/settings.json` trên Docker) và thêm khối `media`:

```json
"media": { "enabled": false }
```

Đặt `"enabled": false` là không dọn gì cả. Muốn nới thay vì tắt thì chỉnh số: `"max_age_days": 90`, `"max_mb": 2000`, `"staging_days": 7`; đặt `max_age_days` hoặc `max_mb` bằng 0 là tắt riêng luật đó. Sửa xong **khởi động lại server**.

Lưu ý nếu bạn đang bật đồng bộ GitHub: `attachments/` và `inbox/` VẪN nằm trong phạm vi đồng bộ, nên việc dọn cũng lan sang repo backup và sang máy khác ở lần đồng bộ sau. Xem [Sao lưu brain lên GitHub](18-sao-luu-github.md).

## Nhà cung cấp báo vượt hạn mức

Gói miễn phí của các nhà cung cấp API (Groq rõ nhất) siết **bốn thứ song song**, và chúng đòi bốn cách xử lý khác hẳn nhau. Javis đọc câu báo lỗi rồi tự phân loại, nên đọc thông báo trong chat là biết mình đang dính cái nào:

- **Token mỗi phút, lượt này quá to.** Javis tự rút gọn ngữ cảnh rồi gửi lại. Không vừa nữa thì bật mức **Tối ưu** ở đầu trang Mức dùng, hoặc hỏi câu ngắn hơn.
- **Token mỗi phút, cửa sổ đang đầy.** Các lượt trước chưa trôi qua. Javis tự chờ đúng số giây nhà cung cấp nói rồi gửi lại. Rút gọn câu hỏi không giúp gì.
- **Số lượt mỗi phút.** Gọi quá dày. Chờ một lát rồi hỏi lại.
- **Hạn mức theo NGÀY** (token hoặc số lượt). Hết quota ngày. Rút gọn câu hỏi hoàn toàn không giúp. Phải chờ sang ngày mới, đổi tạm sang bộ não khác ở trang **Models**, hoặc nâng gói với nhà cung cấp.

Nếu Javis không nhận ra loại nào, nó sẽ **đưa nguyên văn câu báo lỗi của nhà cung cấp** ra thay vì đoán. Gửi nguyên câu đó khi báo lỗi thì dễ lần ra hơn nhiều.

Mẹo giảm hẳn tần suất gặp: chọn mức **Tối ưu** hoặc **Siêu tiết kiệm** ở đầu trang **Mức dùng** (từ 0.24.7 máy mới đã mặc định ở Siêu tiết kiệm). Sau lần đầu bị từ chối, Javis nhớ luôn hạn mức thật của tài khoản đó (do chính nhà cung cấp nói ra) và tự canh ngữ cảnh dưới ngưỡng cho các lượt sau, không cần khai gì cả.

### Nhà cung cấp gãy một nhịp thì Javis tự hỏi lại

Từ bản 0.24.4, lượt gọi model gãy vì lỗi **tạm thời** (429 gọi quá dày, 5xx quá tải, mạng chớp tắt) được tự chạy lại tối đa ba lần, cách nhau vài giây. Nhà cung cấp có gửi kèm `Retry-After` thì Javis nghe theo đúng số giây đó. Bạn thường không thấy gì cả, chỉ là câu trả lời tới chậm hơn một hai giây.

Hai trường hợp Javis **cố ý không** chạy lại:

- **Câu trả lời đã bắt đầu hiện ra.** Chạy lại là bạn đọc câu trả lời hai lần.
- **Lượt đó đã chạy công cụ** (gửi tin, ghi file, đặt lịch). Chạy lại cả vòng là làm những việc đó lần thứ hai. Thà báo lỗi.

Hết ba lần vẫn hỏng thì Javis báo nguyên văn lỗi của nhà cung cấp, kèm chữ *(đã thử lại 3 lần)* để bạn biết đây không phải sự cố chớp nhoáng. Lỗi **không** tạm thời (sai khoá, sai tên model, hết quota ngày, vượt kích thước ngữ cảnh) thì báo ngay từ lần đầu, vì thử lại y nguyên chỉ tốn thêm một lượt gọi để nhận lại đúng lỗi đó.

## Xem nhật ký (log) ở đâu

Có vài nơi xem "nhật ký" tùy loại thông tin:

1. **Nhật ký Javis tự chạy nền**: mở nhóm **Việc** ở thanh nav trái, chọn **Việc định kỳ**, kéo xuống mục **Nhật ký gần đây**. Đây là nơi ghi lại các lượt Javis tự thức làm nhiệm vụ, lọc được theo từng loop. Xem [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md).
2. **Nhật ký tự học**: trang **Tự học** (nhóm **Bộ não**) có hai khung riêng là **Javis đã tự học gì (commit gần nhất)** và **Nhật ký học**. Xem [Tự học](22-tu-hoc.md).
3. **Trang Cập nhật** (nhóm **Hệ thống**, tiêu đề trang là **Nhật ký cập nhật**): đây là nơi xem phiên bản đang chạy và lịch sử tính năng mới theo từng bản. Không còn trang "Logs" hay "Nhật ký hoạt động" riêng nào nữa; mục `logs` trên rail chính là trang này.
4. **Log kỹ thuật của server** (khi cần soi lỗi sâu):
   - Windows chạy ngầm bằng `start-javis.vbs`: log ghi ở `server\javis.log`.
   - Docker / VPS: `docker compose logs javis` (thêm `-f` để xem trực tiếp: `docker compose logs -f`).
   - Linux systemd: `journalctl -u javis -f`.
5. **Log cập nhật** khi bấm nút cập nhật trong app: file `update.log` nằm trong thư mục state, tức `server/update.log` khi chạy local và `/data/state/update.log` trên Docker (đường dẫn theo biến `JAVIS_STATE_DIR`). Thường bạn không cần mở tệp: khi cập nhật lỗi, giao diện đã hiện sẵn thông báo và app cũng đọc 50 dòng cuối của tệp này để báo trạng thái.

## Câu hỏi thường gặp (FAQ)

### Dữ liệu có mất khi cập nhật không?

Không, nếu chạy bằng Docker. Mọi ghi chú, brain, settings và cả token đăng nhập Claude nằm trong **Docker volume** (`javis-data`, `claude-auth`), tách khỏi image. Khi bạn cập nhật (bấm **⬆ Cập nhật ngay** trong **Cập nhật**, Redeploy trên Hostinger, hoặc chạy `./update.sh` trên VPS), image được thay mới nhưng volume giữ nguyên nên dữ liệu **không mất**. Với bản cài native, dữ liệu nằm trong thư mục `brains/` của repo, cũng không bị `git pull` xoá.

### Cập nhật trong app hoạt động thế nào?

Mở **Cập nhật** (nhóm **Hệ thống**); thẻ **Javis OS** hiện phiên bản đang chạy và tự kiểm tra bản mới trên GitHub. Nếu có bản mới, dòng trạng thái hiện **🆕 Có bản mới** kèm khung **Bản mới có gì**, và nút **⬆ Cập nhật ngay** xuất hiện khi môi trường hỗ trợ. Bấm nút, xác nhận, app chạy qua 6 bước hiện trên thanh tiến trình (Chuẩn bị, Tải code, Cài thư viện, Khởi động lại, Kiểm tra sức khoẻ, Xong) rồi tự tải lại trang. Nếu bản mới lỗi, Javis **tự quay về bản cũ** và báo **↩ Bản mới lỗi, đã tự quay về bản cũ**. Bên dưới thẻ là timeline nhật ký cập nhật của các bản đã ra.

Bản cài trực tiếp trên máy (Windows, Linux, macOS) luôn tự cập nhật được. Bản Docker chỉ tự cập nhật tại chỗ khi container **Watchtower** đang chạy.

Watchtower nằm trong `profiles: ["update"]`, nên `docker compose up -d` **không** bật nó - đó là lý do phổ biến nhất khiến máy này có nút mà máy kia không. Bật một lần bằng `docker compose --profile update up -d` rồi tải lại trang. Stack Hostinger cố tình không kèm Watchtower (không đụng được Docker socket), máy đó cập nhật bằng **Redeploy**. Khung Cập nhật tự nói máy bạn rơi vào trường hợp nào.

**Gõ lệnh compose mà báo `not found`** - ba kiểu, ba nguyên nhân khác hẳn:

| Báo lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `no configuration file provided: not found` | Đứng sai thư mục. Tên thư mục tuỳ lúc clone: `javis` nếu theo đúng lệnh trong DEPLOY.md, `javis-os` nếu clone thẳng không đổi tên | `cd` vào đúng thư mục chứa `docker-compose.yml`. Không nhớ nó đâu thì hỏi Docker: `docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project.working_dir"}}'` |
| `docker: command not found` | Đang gõ **bên trong** container Javis (terminal của app) chứ không phải trên máy chủ | SSH vào VPS rồi gõ |
| `docker: 'compose' is not a docker command` | Compose bản cũ (v1) | Viết có gạch nối: `docker-compose --profile update up -d` |

### Chạy nhiều brain (second brain) được không?

Được. Javis quản lý nhiều brain trong thư mục `brains/`. Ở dropdown chọn brain trên giao diện, bạn có thể:

1. Tạo brain mới: bấm nút thêm brain, đặt tên khi được hỏi.
2. Chuyển brain: chọn brain khác trong dropdown; mọi thao tác Tệp tin, đồ thị và bộ nhớ sẽ theo brain đang chọn.
3. Xoá brain: chọn brain cần xoá rồi bấm nút xoá, giao diện yêu cầu **gõ chính xác tên brain** để xác nhận (chống xoá nhầm). Không xoá được **Brain mặc định**.

Xem chi tiết ở [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

### Lỡ xoá brain thì cứu được không?

Được, trong 30 ngày. Xoá brain không phải là xoá vĩnh viễn: Javis chuyển cả thư mục brain vào **thùng rác cục bộ** `brain-trash` nằm trong thư mục state (`server/brain-trash` khi chạy local, `/data/state/brain-trash` trên Docker), đặt tên dạng `<tên brain>__<ngày giờ>`. Bản sao này được giữ 30 ngày rồi mới bị dọn, và nó **không** đi lên repo đồng bộ. Muốn cứu, copy thư mục đó trở lại `brains/` rồi tải lại trang.

Ngược lại, việc xoá sẽ được **lan sang các máy khác** đang đồng bộ chung repo (Javis ghi một "giấy báo tử" để máy kia không hồi sinh brain đã xoá). Nên nếu muốn phục hồi, làm sớm và làm trên máy còn giữ bản trong thùng rác.

### Ảnh và file gửi lên có được giữ mãi không?

Không. `attachments/` và `inbox/` là vùng cache: mặc định file quá **30 ngày** hoặc phần vượt trần **300 MB** sẽ bị dọn, thư mục stage tạm thì **3 ngày**. Ảnh đã bị dọn hiện thành ô xám **Ảnh đã hết hạn** trong hội thoại cũ. Cách giữ lại hoặc tắt hẳn xem mục "Ảnh và file cũ biến mất" ở trên.

### Đổi giọng nói của Javis thế nào?

Giọng đọc mặc định là `vi-VN-HoaiMyNeural` (Edge TTS tiếng Việt), tốc độ `+5%`. Muốn đổi giọng hoặc tốc độ, đặt hai biến trong file `.env` rồi khởi động lại server:

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `TTS_VOICE` | Tên giọng đọc | `vi-VN-HoaiMyNeural` |
| `TTS_RATE` | Tốc độ đọc | `+5%` |

Xem cách đặt biến ở [Cấu hình .env](16-cau-hinh-env.md). Lưu ý: nút loa trên giao diện chỉ để **bật/tắt** việc đọc trả lời bằng giọng, không phải để đổi giọng. Cách dùng giọng nói trong trò chuyện xem [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md).

### Truy cập từ xa mà micro không bật được?

Trình duyệt bắt buộc **HTTPS** mới cho cấp quyền micro (trừ localhost). Mở app qua IP trần `http://<ip>:7777` thì micro luôn bị chặn và không có cách bật tay. Giải pháp: dùng URL `https://` qua Hostinger (`*.hstgr.cloud`), Cloudflare Tunnel (cho URL `https://...trycloudflare.com`), hoặc tên miền riêng có SSL. Xem [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md).

## Vẫn chưa xử lý được?

1. Thu thập log server (xem mục "Xem nhật ký (log) ở đâu" phía trên) để biết lỗi cụ thể.
2. Thử lần lượt: khởi động lại server, rồi Ctrl+Shift+R.
3. Kiểm tra biến môi trường trong `.env` có đặt đúng không, xem [Cấu hình .env](16-cau-hinh-env.md).
4. Kiểm tra "bộ não" còn đăng nhập không (mục **Models**, thẻ engine bạn đang dùng phải hiện **● Đã kết nối**).
