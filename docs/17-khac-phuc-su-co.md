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
| Voice / micro không bật được | Trình duyệt chỉ cấp quyền micro trên **HTTPS** (hoặc localhost). Mở qua `http://<ip>:7777` sẽ luôn bị chặn. Dùng URL `https://` (Hostinger `*.hstgr.cloud`, Cloudflare Tunnel, hoặc tên miền riêng có SSL). Xem [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md). |
| Cập nhật trong app xong mà **phiên bản không đổi** | Đợi thêm; nếu vẫn báo bản cũ, kiểm tra log cập nhật: xem `update.log` hoặc `docker compose logs`. |

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

Khi Javis chạy public (Docker/VPS/Hostinger), lần đầu mở app sẽ ra màn tạo tài khoản admin và có thể hỏi **MÃ THIẾT LẬP**. Đây là cơ chế chống người lạ chỉ có URL cũng tạo được tài khoản (vì Claude chạy toàn quyền trên máy). Lấy mã như sau:

1. **Trong App terminal của container** (terminal này ở BÊN TRONG container nên không có lệnh `docker`): chạy `cat /data/state/.setup_token`, copy chuỗi, dán vào ô MÃ THIẾT LẬP.
2. **Trên host (ngoài container)**: chạy `docker compose logs javis` rồi tìm dòng có chữ `SETUP TOKEN`.
3. **Khỏi cần mã**: đặt sẵn admin lúc deploy bằng hai env `JAVIS_ADMIN_USER` và `JAVIS_ADMIN_PASSWORD` trong compose. Khi đó mở app là đăng nhập luôn, không hỏi mã.

Chi tiết bảo mật và cách đặt mật khẩu xem [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).

## Claude báo chưa đăng nhập

"Bộ não" của Javis là Claude Code CLI, đăng nhập 1 lần và giữ qua mọi restart/update. Nếu Javis không trả lời hoặc báo chưa đăng nhập:

1. **Cách trong giao diện:** mở **Models** ở thanh nav trái. Ở thẻ Claude Code, dòng trạng thái sẽ hiện **○ Chưa đăng nhập**. Bấm **Đăng nhập Claude**, app hiện một link; mở link để đăng nhập claude.ai; nếu trang hiện một mã code thì dán vào ô rồi bấm **Gửi code**. Khi xong, trạng thái đổi thành **● Đã kết nối**. Có nút **↻ Kiểm tra lại** để làm mới trạng thái.
2. **Cách bằng lệnh:** chạy `claude auth login --claudeai` một lần (trên Docker thì chạy trong **App terminal**), mở link, dán code.

Token đăng nhập nằm trong `~/.claude` (Docker: volume `claude-auth`) nên không mất khi update. Nếu đã đăng nhập trên máy khác, có thể copy thư mục `~/.claude` sang. Xem thêm [Models & engine](10-models-va-engine.md).

## Trang Tệp tin báo lỗi ở "Đang tải..."

Nếu vào **Tệp tin** mà chỗ danh sách file báo lỗi thay vì lên danh sách, thường do máy chủ đang chạy bản cũ chưa có endpoint Tệp tin (lỗi 404). Bản thân giao diện sẽ nhắc: hãy **khởi động lại server** (Windows: `stop-javis.bat` rồi `start-javis.vbs`) rồi **tải lại trang** bằng Ctrl+Shift+R.

Nếu hiện dòng báo phiên đăng nhập hết hạn (lỗi 401), chỉ cần tải lại trang và đăng nhập lại. Hướng dẫn dùng Tệp tin đầy đủ ở [Quản lý tệp tin](05-quan-ly-tep-tin.md).

## Xem Logs ở đâu

Có vài nơi xem "nhật ký" tùy loại thông tin:

1. **Nhật ký hoạt động của Javis khi tự chạy nền**: mở **Tự cải thiện** ở thanh nav trái, kéo xuống mục **Nhật ký gần đây**. Đây là nơi ghi lại các lượt Javis tự thức làm nhiệm vụ. Xem [Tự cải thiện](08-tu-cai-thien.md).
2. **Mục Logs ở thanh nav** ("Nhật ký hoạt động"): đây là khung điều hướng dành sẵn, hiện đang phát triển; nội dung chi tiết theo dõi ở mục Tự cải thiện phía trên.
3. **Log kỹ thuật của server** (khi cần soi lỗi sâu):
   - Windows chạy ngầm bằng `start-javis.vbs`: log ghi ở `server\javis.log`.
   - Docker / VPS: `docker compose logs javis` (thêm `-f` để xem trực tiếp: `docker compose logs -f`).
   - Linux systemd: `journalctl -u javis -f`.
   - Log cập nhật khi bấm nút cập nhật trong app: `update.log`.

## Câu hỏi thường gặp (FAQ)

### Dữ liệu có mất khi cập nhật không?

Không, nếu chạy bằng Docker. Mọi ghi chú, vault, settings và cả token đăng nhập Claude nằm trong **Docker volume** (`javis-data`, `claude-auth`), tách khỏi image. Khi bạn cập nhật (bấm **⬆ Cập nhật ngay** trong **Cập nhật**, Redeploy trên Hostinger, hoặc chạy `./update.sh` trên VPS), image được thay mới nhưng volume giữ nguyên nên dữ liệu **không mất**. Với bản cài native, dữ liệu nằm trong thư mục brain/vault của repo, cũng không bị `git pull` xoá.

### Cập nhật trong app hoạt động thế nào?

Mở **Cập nhật**; khung **Javis OS** hiện phiên bản đang chạy và tự kiểm tra bản mới trên GitHub. Nếu có bản mới, dòng trạng thái hiện **🆕 Có bản mới** và nút **⬆ Cập nhật ngay** xuất hiện khi môi trường hỗ trợ. Bấm nút, xác nhận, app sẽ tự tải bản mới và khởi động lại (khoảng 20 đến 40 giây), sau đó tự tải lại trang. Hostinger không hỗ trợ Watchtower nên khung sẽ hướng dẫn **Redeploy**; VPS Docker cần bật profile `update` để dùng cập nhật một chạm.

### Chạy nhiều brain (second brain) được không?

Được. Javis hỗ trợ nhiều brain trong cùng một thư mục. Ở dropdown chọn brain trên giao diện, bạn có thể:

1. Tạo brain mới: bấm nút thêm brain, đặt tên khi được hỏi.
2. Chuyển brain: chọn brain khác trong dropdown; mọi thao tác Tệp tin, đồ thị và bộ nhớ sẽ theo brain đang chọn.
3. Xoá brain: chọn brain cần xoá rồi bấm nút xoá, giao diện yêu cầu **gõ chính xác tên brain** để xác nhận (chống xoá nhầm). Không xoá được **Brain mặc định**.

Xem chi tiết ở [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

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

1. Thu thập log server (xem mục "Xem Logs ở đâu" phía trên) để biết lỗi cụ thể.
2. Thử lần lượt: khởi động lại server, rồi Ctrl+Shift+R.
3. Kiểm tra biến môi trường trong `.env` có đặt đúng không, xem [Cấu hình .env](16-cau-hinh-env.md).
4. Kiểm tra "bộ não" Claude còn đăng nhập không (mục **Models**, thẻ Claude Code phải hiện **● Đã kết nối**).
