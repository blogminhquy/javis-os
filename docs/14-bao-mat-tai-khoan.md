# Bảo mật & tài khoản

Trang này giải thích cách Javis OS tự bảo vệ khi bạn đưa nó lên mạng, và cách dùng trang **Tài khoản** trong dashboard để đặt mật khẩu, đổi mật khẩu, đăng xuất và đổi tên workspace.

## Tính năng này là gì

Javis chạy Claude với **toàn quyền trên máy/VPS** của bạn: nó đọc được tệp, chạy lệnh, gọi công cụ. Vì thế nếu để dashboard hở ra Internet mà không có mật khẩu thì bất kỳ ai biết địa chỉ cũng điều khiển được máy của bạn.

Javis xử lý việc này theo 3 lớp:

1. **Tự bắt buộc đăng nhập khi chạy public.** Khi server nghe ra ngoài (không phải chỉ máy này), Javis chặn mọi chức năng cho tới khi bạn đăng nhập. Chạy trên máy cá nhân (localhost) thì không ép, dùng thẳng như cũ.
2. **Chống chiếm tài khoản lần đầu.** Người đầu tiên muốn tạo admin phải có **MÃ THIẾT LẬP** (in trong log server) hoặc admin đã được đặt sẵn qua biến môi trường. Kẻ chỉ biết URL không tạo được tài khoản.
3. **Chống dò mật khẩu.** Sai nhiều lần bị khoá tạm theo địa chỉ IP; mỗi lần sai bị làm chậm.

## Mở ở đâu trong Javis

Mọi thao tác tài khoản nằm ở mục **Tài khoản** trong nhóm **Hệ thống** trên thanh nav bên trái (phụ đề "Đăng nhập & workspace"). Từ trang **Cài đặt** cũng có lối tắt tới đây; không có form tài khoản trùng lặp ở nơi khác.

Trang **Tài khoản** có 2 khối:

- **Workspace**: đổi tên workspace hiển thị.
- **Tài khoản đăng nhập**: đặt/đổi mật khẩu, đăng xuất, tắt đăng nhập.

## Khi nào Javis bắt buộc đăng nhập

Javis quyết định có ép đăng nhập hay không dựa vào cách server đang chạy:

| Tình huống | Có bắt buộc đăng nhập? |
|---|---|
| Chạy trên máy cá nhân, nghe `127.0.0.1` / `localhost` (hoặc `::1`) | Không (trừ khi bạn đã tự đặt mật khẩu) |
| Chạy public (Docker/VPS/Hostinger), nghe `0.0.0.0`, `::` hoặc IP LAN | Có, tự bật |
| Đã đặt mật khẩu trong trang Tài khoản | Có, ở mọi chế độ |

Có thể ép cứng bằng biến môi trường `JAVIS_REQUIRE_LOGIN`:

- `JAVIS_REQUIRE_LOGIN=1` : luôn bắt buộc đăng nhập, kể cả localhost. Nên đặt khi bạn mở Javis qua tunnel (Cloudflare Tunnel, ngrok...) trên máy cá nhân.
- `JAVIS_REQUIRE_LOGIN=0` : tắt bắt buộc đăng nhập.

Nguyên tắc an toàn (fail-closed): nếu server nghe địa chỉ **không phải** thuần localhost thì Javis mặc định coi là public và bật đăng nhập. Chi tiết biến môi trường xem [Cấu hình .env](16-cau-hinh-env.md).

## Cách dùng (từng bước)

### A. Tạo tài khoản admin lần đầu trên VPS/public

Khi mở dashboard lần đầu trên server công khai, Javis hiện màn **tạo tài khoản** và yêu cầu **MÃ THIẾT LẬP**. Có 2 cách:

**Cách 1 - Đặt sẵn admin bằng biến môi trường (khuyến nghị):**

1. Trong cấu hình deploy (ví dụ compose của Hostinger), thêm 2 biến:
   - `JAVIS_ADMIN_PASSWORD` : mật khẩu admin bạn chọn.
   - `JAVIS_ADMIN_USER` : tên đăng nhập (tuỳ chọn, mặc định là `admin`).
2. Khởi động Javis. Lúc boot, Javis tự tạo admin từ 2 biến này và **đóng luôn** màn tạo tài khoản. Bạn mở app là vào thẳng màn đăng nhập.
3. Đăng nhập bằng đúng user/password vừa đặt.

**Cách 2 - Dùng MÃ THIẾT LẬP in trong log:**

1. Mở log/terminal của server. Lúc khởi động, nếu đang public mà chưa có admin, Javis sinh mã thiết lập và lưu ra tệp `.setup_token` trong thư mục state.
   - Trên Hostinger, vào bên trong container (App terminal) chạy: `cat /data/state/.setup_token`.
   - Trên VPS chạy Docker: xem `docker compose logs javis` và tìm dòng có `SETUP TOKEN`.
2. Mở dashboard, ở màn tạo tài khoản nhập: tên tài khoản, mật khẩu (**tối thiểu 8 ký tự**), và dán **MÃ THIẾT LẬP**.
3. Bấm nút tạo tài khoản. Nếu mã đúng, Javis tạo admin, đăng nhập bạn luôn và mã thiết lập tự huỷ (dùng 1 lần).

Nếu nhập sai/thiếu mã, Javis báo: "Sai hoặc thiếu MÃ THIẾT LẬP - xem mã trong log/terminal của server."

### B. Đặt mật khẩu (khi đang chạy máy cá nhân, chưa có mật khẩu)

Nếu bạn chạy Javis ở nhà mà muốn khoá lại trước khi đưa lên VPS:

1. Vào **Tài khoản** trên thanh nav trái.
2. Ở khối **Tài khoản đăng nhập**, nhập **Tài khoản** (để trống sẽ dùng `admin`).
3. Nhập **Mật khẩu**.
4. Bấm **Đặt mật khẩu**.
5. Javis lưu tài khoản và cấp phiên đăng nhập ngay cho bạn (không tự khoá bạn ra ngoài).

Lưu ý về độ dài mật khẩu: khi lưu, server yêu cầu **tối thiểu 8 ký tự**. Bạn nên đặt mật khẩu từ 8 ký tự trở lên trong mọi trường hợp cho an toàn.

### C. Đổi mật khẩu

Khi đã có mật khẩu, khối **Tài khoản đăng nhập** hiện dòng "🔒 Đã đặt mật khẩu · tài khoản: <tên của bạn>" và nút chuyển thành **Đổi mật khẩu**.

1. Vào **Tài khoản**.
2. (Tuỳ chọn) Sửa ô **Tài khoản** nếu muốn đổi tên đăng nhập.
3. Nhập mật khẩu mới vào ô **Mật khẩu** (tối thiểu 8 ký tự).
4. Bấm **Đổi mật khẩu**.

Lưu ý: nếu server báo lỗi "Đã có tài khoản - hãy đăng nhập." khi đổi mật khẩu, hãy **Tắt đăng nhập** trước (khi đang chạy máy cá nhân) rồi đặt lại mật khẩu mới; hoặc trên VPS thì đặt lại qua `JAVIS_ADMIN_PASSWORD` sau khi xoá phần `auth` cũ trong `settings.json`.

### D. Đăng xuất

1. Vào **Tài khoản**.
2. Bấm **Đăng xuất**.
3. Javis xoá phiên hiện tại và tải lại trang. Lần sau vào phải đăng nhập lại.

Đăng xuất chỉ kết thúc phiên trên trình duyệt này, không xoá mật khẩu.

### E. Tắt đăng nhập (xoá mật khẩu)

Chỉ nên làm khi chạy máy cá nhân, tuyệt đối không làm trên VPS.

1. Vào **Tài khoản**.
2. Bấm **Tắt đăng nhập**.
3. Xác nhận ở hộp thoại "Tắt đăng nhập? Ai mở dashboard cũng dùng được."
4. Javis xoá mật khẩu và **đăng xuất mọi phiên** đang mở.

Lưu ý: nếu server vẫn đang chạy public (hoặc bạn đặt `JAVIS_REQUIRE_LOGIN=1`), tắt mật khẩu **không** làm dashboard mở toang, mà quay lại màn ép tạo tài khoản mới. Đăng nhập chỉ thật sự tắt khi server nghe localhost và không ép login.

### F. Đổi tên workspace

1. Vào **Tài khoản**.
2. Ở khối **Workspace**, sửa **Tên workspace**.
3. Bấm **Lưu**. Tên mới hiển thị ngay trên đầu dashboard.

## Cách bảo mật hoạt động (dành cho người muốn hiểu sâu)

| Cơ chế | Chi tiết thực tế |
|---|---|
| Lưu mật khẩu | Không lưu mật khẩu thô. Javis băm bằng PBKDF2-HMAC-SHA256 (120.000 vòng) kèm salt ngẫu nhiên. |
| Phiên đăng nhập | Cấp qua cookie `javis_session`, cookie dạng `httponly` (JavaScript không đọc được), `samesite=lax`. |
| Hết hạn phiên | Mỗi phiên sống tối đa **30 ngày** rồi tự hết hạn, phải đăng nhập lại. |
| Phiên qua khởi động lại | Phiên lưu ra tệp, nên **khởi động lại server không làm bạn bị đăng xuất**. |
| Chống dò mật khẩu | Đếm số lần sai theo IP. Sai đủ số lần liên tiếp (8 lần) bị khoá tạm khoảng 5 phút; mỗi lần sai bị làm chậm nửa giây. Khi bị khoá, Javis báo "Quá nhiều lần sai - thử lại sau ít phút." |
| Cookie an toàn khi HTTPS | Khi bạn truy cập qua **tên miền riêng** đã bật HTTPS (Caddy On-Demand TLS), cookie được đánh dấu `secure` (chỉ gửi qua HTTPS). |

Về cookie `secure`: mặc định Javis **không** ép cookie `secure` để chạy được cả HTTP lẫn HTTPS (tránh kẹt vòng đăng nhập sau proxy HTTP như đường dẫn dạng `http://host/PORT/`). Nếu bạn chắc chắn chạy HTTPS đầu-cuối, bật `JAVIS_SECURE_COOKIE=1` trong biến môi trường (xem [Cấu hình .env](16-cau-hinh-env.md)). Truy cập qua đúng tên miền riêng thì Javis tự bật `secure` mà không cần đặt biến này (dựa vào Host khớp tên miền, không suy từ `X-Forwarded-Proto`).

## Mẹo

- **Luôn đặt admin trước khi công khai.** Cách chắc nhất là đặt `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` khi deploy, khỏi phải đi tìm MÃ THIẾT LẬP.
- **Đặt mật khẩu đủ dài.** Tối thiểu 8 ký tự; dùng cụm dài, khó đoán.
- **Chạy qua HTTPS khi truy cập từ xa.** Dùng tên miền riêng (ví dụ Hostinger `*.hstgr.cloud`) hoặc Cloudflare Tunnel thay vì phơi cổng 7777 thô ra Internet. Cách trỏ tên miền và bật HTTPS xem [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md).
- **Localhost + tunnel thì bật `JAVIS_REQUIRE_LOGIN=1`.** Khi máy chỉ nghe localhost nhưng bạn mở ra ngoài bằng tunnel, Javis không tự biết là đang public, nên hãy ép login thủ công.
- **MÃ THIẾT LẬP chỉ dùng 1 lần.** Sau khi tạo admin xong, mã tự huỷ. Muốn tạo lại admin (đã có admin cũ) thì phải đăng nhập bằng admin cũ hoặc xoá state.

## Sự cố thường gặp

**Mở app báo cần MÃ THIẾT LẬP.**
Bạn đang chạy public và chưa có admin. Lấy mã trong state: App terminal (trong container) chạy `cat /data/state/.setup_token`; trên host chạy `docker compose logs javis` rồi tìm dòng có `SETUP TOKEN`. Hoặc đặt `JAVIS_ADMIN_PASSWORD` để khỏi cần mã.

**Nhập đúng user/password nhưng vẫn quay lại màn đăng nhập (kẹt vòng đăng nhập).**
Thường do cookie `secure` bị bật trong khi bạn đang truy cập qua HTTP (nhiều proxy phục vụ HTTP dạng `http://host/PORT/`). Đừng bật `JAVIS_SECURE_COOKIE` trừ khi bạn chắc chắn HTTPS đầu-cuối. Nếu đã lỡ bật, gỡ biến này rồi khởi động lại server.

**Bị báo "Quá nhiều lần sai - thử lại sau ít phút."**
Bạn (hoặc ai đó cùng IP) đã sai mật khẩu quá số lần cho phép. Đợi khoảng 5 phút rồi thử lại. Khởi động lại server cũng xoá bộ đếm này.

**Quên mật khẩu.**
Cách chắc chắn nhất là sửa/xoá phần `auth` của tài khoản trong tệp `settings.json` ở thư mục state (Docker: `/data/state`) rồi khởi động lại; hoặc đặt lại admin bằng `JAVIS_ADMIN_PASSWORD` sau khi đã xoá phần `auth` cũ.

**Tắt đăng nhập rồi mà vẫn bị hỏi tài khoản.**
Vì server vẫn đang public (hoặc `JAVIS_REQUIRE_LOGIN=1`). Ở chế độ này Javis không cho tắt đăng nhập hoàn toàn, mà bắt tạo lại tài khoản. Muốn dùng không mật khẩu thì phải chạy server nghe thuần localhost.

## Xem thêm

- [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) - dựng Javis và tạo admin lần đầu.
- [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md) - trỏ tên miền và bật HTTPS tự động.
- [Cấu hình .env](16-cau-hinh-env.md) - danh sách biến môi trường bảo mật (`JAVIS_HOST`, `JAVIS_REQUIRE_LOGIN`, `JAVIS_ADMIN_USER/PASSWORD`, `JAVIS_SECURE_COOKIE`, `JAVIS_STATE_DIR`).
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md) - các lỗi thường gặp khác.
