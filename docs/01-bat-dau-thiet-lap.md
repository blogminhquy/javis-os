# Bắt đầu & thiết lập lần đầu

Trang này hướng dẫn bạn từ lúc mở Javis lần đầu tiên cho tới khi Javis sẵn sàng trò chuyện: tạo tài khoản admin, đăng nhập Claude làm "bộ não", chọn model, và kiểm tra trạng thái hệ thống ở trang Cài đặt.

## Tính năng này là gì

Javis OS là một lớp điều hành AI chạy trên máy hoặc VPS của bạn, lấy Claude Code làm bộ não. Trước khi dùng được, Javis cần 3 thứ:

1. Một tài khoản admin (để chặn người lạ, bắt buộc khi chạy công khai trên VPS).
2. Một nhà cung cấp AI đã đăng nhập (mặc định là Claude Code, không cần API key).
3. Một model chính để trả lời hội thoại.

Lần đầu mở app, một bộ cài đặt (wizard) sẽ hiện ra và dẫn bạn qua đúng 3 việc này. Mọi thứ đặt ở đây đều đổi lại được sau trong các trang quản lý.

## Mở ở đâu trong Javis

- Trên máy cá nhân, mở trình duyệt và vào `http://localhost:7777` (cổng mặc định là 7777).
- Trên VPS hoặc Docker, dùng địa chỉ mà nhà cung cấp cấp cho bạn, ví dụ `http://<ip-vps>:7777` hoặc link HTTPS dạng `https://<app>.<vps>.hstgr.cloud`.

Sau khi thiết lập xong, các mục liên quan nằm trên thanh điều hướng bên trái:

- **Cài đặt**: trạng thái hệ thống, lối tắt cấu hình, công tắc đồ thị, chuẩn hóa brain, giọng nói và tên miền.
- **Cập nhật**: phiên bản hiện tại, cập nhật/Redeploy, tiến trình và nhật ký phiên bản.
- **Models**: đổi model chính, đăng nhập/ngắt các nhà cung cấp (xem [Models & engine](10-models-va-engine.md)).
- **Tài khoản**: đổi mật khẩu, đăng xuất, tắt đăng nhập (xem [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md)).

## Cách dùng (từng bước)

### Bước 1: Mở app và gặp bộ cài đặt

Mở `http://localhost:7777` (hoặc địa chỉ VPS của bạn). Nếu đây là lần đầu và chưa có tài khoản, Javis hiện cửa sổ **Chào mừng tới Javis** với 3 mục đánh số sẵn.

Nếu bạn chạy trên máy cá nhân (localhost), mục mật khẩu và MÃ THIẾT LẬP là tùy chọn, có thể bỏ trống. Nếu bạn chạy công khai (VPS/Docker), Javis bắt buộc bạn đặt mật khẩu và nhập MÃ THIẾT LẬP mới cho qua.

### Bước 2: Đặt tên Workspace

Ở mục **1. Workspace**, gõ tên hiển thị vào ô **Tên hiển thị** (ví dụ tên cửa hàng hoặc tên bạn). Bỏ trống thì Javis dùng mặc định là "Javis OS". Đây chỉ là nhãn hiển thị, đổi lại bất cứ lúc nào.

### Bước 3: Tạo tài khoản admin (và MÃ THIẾT LẬP nếu cần)

Ở mục **2. Tài khoản admin**:

1. Gõ tên tài khoản vào ô **Tài khoản** (mặc định gợi ý là `admin`).
2. Gõ mật khẩu vào ô **Mật khẩu**. Mật khẩu phải dài tối thiểu 8 ký tự.
3. Nếu Javis chạy công khai, một ô **Mã thiết lập** sẽ hiện ra. Dán MÃ THIẾT LẬP vào đây (cách lấy xem mục "Khi nào cần MÃ THIẾT LẬP" bên dưới).

Trên máy cá nhân, nếu bạn để trống mật khẩu thì Javis không đặt tài khoản và ai mở link máy này cũng dùng được. Chỉ nên bỏ trống khi máy chỉ mình bạn dùng.

### Bước 4: Chọn nhà cung cấp AI (bộ não)

Ở mục **3. Nhà cung cấp AI (bộ não)**, chọn 1 trong các thẻ:

| Lựa chọn | Mô tả | Cần gì để dùng |
|---|---|---|
| **Claude Code** (khuyên dùng) | Đủ MCP, skill, đọc/ghi file, vòng lặp tự cải thiện. Mạnh và đầy đủ nhất. | Đăng nhập subscription Claude 1 lần (không cần API key) |
| **ChatGPT (gói subscription)** | Đăng nhập ChatGPT Plus/Pro qua Codex, vẫn dùng được MCP của Javis. | Đăng nhập ChatGPT ở trang Models |
| **OpenRouter** | Nhiều model giá rẻ, chat thuần, không có MCP. | Dán API key OpenRouter (dán ngay hoặc để sau ở Models) |

Nếu chọn **OpenRouter**, một ô nhập **OpenRouter API key** sẽ hiện ra, bạn có thể dán key ngay hoặc để trống rồi dán sau ở trang Models.

Bấm **Bắt đầu dùng Javis →** để lưu và vào app.

### Bước 5: Đăng nhập Claude làm bộ não

Đây là bước quan trọng nhất nếu bạn chọn Claude Code. Wizard chỉ lưu lựa chọn nhà cung cấp, việc đăng nhập Claude thực hiện ở trang **Models**:

1. Vào mục **Models** trên thanh trái.
2. Tìm thẻ **Anthropic OAuth (Claude Code)**. Trạng thái ban đầu là "Chưa đăng nhập".
3. Bấm nút **Đăng nhập Claude**.
4. Javis hiện một đường link. Bấm mở link đó (mở trong tab mới) để đăng nhập tại claude.ai.
5. Nếu sau khi đăng nhập trang hiện một mã code, dán mã đó vào ô **dán code (nếu có)** rồi bấm **Gửi code**. Một số luồng không cần dán code, Javis tự nhận biết và cập nhật trạng thái.
6. Khi xong, trạng thái thẻ đổi thành "Đã kết nối" (kèm email/gói nếu có).

Đây là luồng device-code: bạn không cần nhập API key. Cách này chạy được cả trên VPS không có màn hình. Nếu bạn có quyền vào terminal của server, cũng có thể đăng nhập một lần bằng lệnh `claude auth login --claudeai` thay cho các bước trên.

Nút **↻ Kiểm tra lại** trên thẻ dùng để nạp lại trạng thái đăng nhập bất cứ lúc nào. Nút **Ngắt** dùng để đăng xuất Claude khỏi Javis.

### Bước 6: Chọn engine và model mặc định

Sau khi đã đăng nhập, kiểm tra và chọn model chính ở trang **Models**:

- Phần **Main Model** hiển thị model đang dùng cho hội thoại. Bấm **Đổi model ▾** để chọn model khác.
- Với Claude Code, model chạy qua đủ MCP/skill/loop. Với các nhà cung cấp gọi API thẳng (OpenRouter, Anthropic API, OpenAI), model chỉ chat thuần, không có MCP.
- Phần **Auxiliary** cho phép chọn một model rẻ (ví dụ haiku) cho các việc chạy nền như loop, metrics, ingest, để tiết kiệm. Chọn "Mặc định" nếu không muốn đổi.
- Phần **Suy nghĩ** (reasoning) đặt độ sâu suy nghĩ khi trả lời: Tắt, Thấp, Vừa, Cao. Mặc định là Tắt (trả lời nhanh).

Chi tiết đầy đủ về từng nhà cung cấp và model xem [Models & engine](10-models-va-engine.md).

## Trang Cài đặt: kiểm tra hệ thống

Sau khi thiết lập, mở mục **Cài đặt** để xem nhanh trạng thái và các nhóm cấu hình. Nội dung được chia thành nhóm có thể gập/mở:

### Phiên bản và cập nhật

Phần này nằm riêng ở mục **Cập nhật**. Khung Javis OS hiển thị phiên bản đang chạy và cho biết có bản mới trên GitHub hay không.

- Bấm **Kiểm tra lại** để so lại với bản mới nhất.
- Nếu có bản mới, nút **⬆ Cập nhật ngay** hiện ra. Bấm để tải bản mới và khởi động lại (app tự tải lại trang sau khoảng 20 đến 40 giây). Dữ liệu của bạn không mất khi cập nhật. Bản Hostinger không chạy Watchtower nên khung này hướng dẫn **Redeploy**; VPS Docker có Watchtower mới cập nhật một chạm.

### Hệ thống

Bốn thẻ tóm tắt cấu hình hiện tại:

| Thẻ | Cho biết |
|---|---|
| **Engine** | Đang chạy Claude CLI (đầy đủ MCP) hay OpenRouter (chat thuần) |
| **Model** | Model đang dùng, hoặc "mặc định" |
| **Workspace** | Tên workspace bạn đặt ở wizard |
| **Telegram** | Bot Telegram đang Bật hay Tắt (xem [Kênh Telegram](11-telegram.md)) |

### Hiệu năng: công tắc đồ thị 3D

Thẻ **Đồ thị não** cho biết đồ thị tri thức đang bật/tắt và đang dùng chế độ 2D hay 3D.

- Chọn **2D** để nhẹ hơn, **3D** để có chiều sâu, hoặc **Tắt đồ thị** để giảm tải tối đa.
- Nếu màn hình hẹp (điện thoại), Javis tự ép chế độ nhẹ (lite-mode) dù công tắc đang bật.

Chi tiết về đồ thị xem [Đồ thị tri thức 3D](03-do-thi-tri-thuc-3d.md).

### Cấu trúc brain: chuẩn hóa / khởi tạo

Thẻ **Chuẩn hóa thư mục** gom các thư mục `agents/ workflows/ memory/ skills/` của brain đang chọn về dạng phẳng đồng nhất. Bấm **Chuẩn hóa brain đang chọn** để chạy.

Thao tác này an toàn: chỉ di chuyển khi thư mục đích chưa có, không ghi đè, chạy lại nhiều lần cũng vô hại (ví dụ chuyển `Javis/agents` sang `agents`, `Memory` sang `memory`; có git backup). Sau khi chạy, Javis báo đã di chuyển gì hoặc "Không có gì cần di chuyển (đã chuẩn)".

Về Second Brain (bộ nhớ, Wiki, cấu trúc vault), xem [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

## Khi nào cần MÃ THIẾT LẬP và lấy ở đâu

**MÃ THIẾT LẬP (setup token)** chỉ xuất hiện khi Javis chạy công khai (nghe trên `0.0.0.0`, tức VPS/Docker/Hostinger) và chưa có tài khoản admin. Vì lúc này Claude chạy với toàn quyền trên máy, Javis không cho phép bất kỳ ai chỉ có đường link cũng tạo được tài khoản admin. MÃ THIẾT LẬP là chuỗi bí mật chỉ in ra log/terminal của server, nên chỉ người có quyền xem server mới lấy được.

Trên máy cá nhân (localhost), Javis không hỏi mã này.

Cách lấy mã:

| Tình huống | Lệnh chạy |
|---|---|
| Hostinger, vào App terminal (bên trong container `javis`) | `cat /data/state/.setup_token` |
| SSH vào host chạy Docker | `docker compose logs javis` rồi tìm dòng `SETUP TOKEN` |

Sau khi có mã, dán vào ô **Mã thiết lập** trong wizard rồi bấm **Bắt đầu dùng Javis →**. Mã được dùng một lần, sau khi tạo tài khoản thành công Javis xóa mã đi.

**Cách khỏi cần mã:** khi deploy, đặt sẵn hai biến môi trường `JAVIS_ADMIN_USER` và `JAVIS_ADMIN_PASSWORD`. Javis tự tạo tài khoản admin lúc khởi động, mở app ra là màn đăng nhập luôn, không hỏi MÃ THIẾT LẬP. Chi tiết biến môi trường xem [Cấu hình .env](16-cau-hinh-env.md).

## Mẹo

- Nếu chỉ chạy máy cá nhân và không sợ người lạ, cứ để trống mật khẩu ở wizard để vào nhanh. Bạn có thể đặt mật khẩu sau ở trang **Tài khoản**.
- Sau khi vào app, nếu thấy Claude báo "chưa đăng nhập", quay lại **Models** bấm **Đăng nhập Claude** một lần là xong.
- Đổi giao diện (avatar, tên miền, giọng nói, tốc độ) nằm ở mục **CÀI ĐẶT NHANH** ở thanh bên phải, không phải trong wizard.
- Sau khi cập nhật phiên bản, nếu giao diện không đổi, nhấn Ctrl+Shift+R để tải lại trang sạch.

## Sự cố thường gặp

- **Mở app báo cần MÃ THIẾT LẬP nhưng không biết lấy đâu:** vào App terminal (Hostinger) chạy `cat /data/state/.setup_token`, hoặc trên host chạy `docker compose logs javis` tìm dòng `SETUP TOKEN`. Hoặc đặt sẵn env `JAVIS_ADMIN_PASSWORD` để khỏi cần mã.
- **Báo "Sai hoặc thiếu MÃ THIẾT LẬP":** mã dán vào sai hoặc thiếu. Lấy lại mã đúng từ log server rồi dán lại, chú ý không dính khoảng trắng thừa.
- **Báo "Mật khẩu tối thiểu 8 ký tự":** đặt mật khẩu dài từ 8 ký tự trở lên.
- **Báo "Đã có tài khoản - hãy đăng nhập":** admin đã được tạo trước đó (ví dụ qua env). Dùng màn đăng nhập với tài khoản/mật khẩu đã đặt.
- **Claude báo chưa đăng nhập:** vào **Models**, bấm **Đăng nhập Claude**, mở link, dán code nếu được hỏi. Hoặc chạy `claude auth login --claudeai` trong terminal server.
- **Quên mật khẩu admin:** ở màn đăng nhập bấm "Quên mật khẩu?" để xem hướng dẫn. Cách xử lý là mở file `server/settings.json`, xóa khối `"auth"` (hoặc đặt rỗng), rồi khởi động lại server; mở lại app sẽ về wizard để tạo tài khoản mới. Xem thêm [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).
- **Sai quá nhiều lần khi đăng nhập, bị báo "Quá nhiều lần sai":** Javis khóa tạm để chống dò mật khẩu. Đợi ít phút rồi thử lại.
- **Mở đúng cổng nhưng không thấy app:** kiểm tra địa chỉ có đúng `http://localhost:7777` (hoặc IP VPS kèm cổng 7777) không. Nếu vừa sửa code, khởi động lại server rồi thử lại.

Còn vướng, xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
