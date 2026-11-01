# Nối Fanpage Messenger vào Javis từng bước (nhắn tin và trả lời bình luận)

***Tiếng Việt** · [English](en/31-messenger-step-by-step.md)*

Hướng dẫn này đi từng cú bấm trên trang Meta, dành cho người mới làm lần đầu. Tổng thời gian lần đầu khoảng 20 phút. Thêm Trang mới về sau khoảng 2 phút mỗi Trang.

> **Mọi thao tác trong Javis làm ở một chỗ:** thẻ **Facebook Messenger** ở trang **Kết nối**. Thẻ có nút **Đăng nhập Facebook** (cách nhanh nhất, xem [31 - Messenger](31-messenger.md)) và mục **Dán token thay vì đăng nhập** (hướng dẫn này). Nối xong ở đó, Fanpage tự có trong danh sách kênh của trang Chatbot, không phải thêm lại.

Trước khi bắt đầu, bạn cần:

- Javis mở được bằng **tên miền HTTPS** (Cài đặt, Truy cập từ xa). Meta không gửi tin tới localhost hay địa chỉ IP.
- Tài khoản Facebook là **quản trị viên** của Fanpage.
- Một app Meta của riêng bạn. Chưa có thì làm Phần 0 bên dưới. Đã có app (ví dụ app tạo cho thẻ Facebook Trang trong store) thì dùng lại được, bỏ qua Phần 0: một app phục vụ được mọi Fanpage của bạn.

> **Bảo mật:** ai có token hoặc App secret là điều khiển được Fanpage. Không gửi cho người khác, không chụp màn hình khi đang hiện token.

---

## Tổng quan

0. Tạo app Meta (chỉ khi chưa có)
1. Chuẩn bị app Meta (thêm Messenger và quyền bình luận)
2. Lấy token trong Graph API Explorer
3. Dán vào thẻ Facebook Messenger ở trang Kết nối (Javis tự khai webhook và đăng ký sự kiện)
4. Gắn bot
5. Chuyển app sang Live

---

## Phần 0. Tạo app Meta (chỉ khi chưa có)

App Meta là "giấy phép" để Javis nói chuyện với Facebook thay bạn. Tạo miễn phí, chỉ một lần.

1. Mở [developers.facebook.com](https://developers.facebook.com), đăng nhập bằng tài khoản Facebook là quản trị viên Fanpage.
2. Lần đầu vào, Meta hỏi đăng ký làm nhà phát triển: bấm **Bắt đầu**, xác minh số điện thoại hoặc email, chọn vai trò bất kỳ (ví dụ "Chủ doanh nghiệp").
3. Vào **Ứng dụng của tôi**, bấm **Tạo ứng dụng**.
4. Đặt **tên ứng dụng** tuỳ ý (ví dụ tên shop của bạn kèm chữ "Bot"), điền email liên hệ, bấm **Tiếp**.
5. Ở bước chọn trường hợp sử dụng, chọn **Tương tác với khách hàng trên Messenger from Meta** (nằm trong nhóm Nhắn tin doanh nghiệp). Không thấy thì chọn **Khác** rồi chọn loại **Doanh nghiệp**.
6. Bước chọn Danh mục doanh nghiệp (Business portfolio): chọn danh mục đang quản lý Fanpage, hoặc "Tôi chưa muốn kết nối" nếu chưa có. Bấm **Tạo ứng dụng**, nhập lại mật khẩu Facebook nếu được hỏi.

Xong bước này bạn có một app, chưa làm được gì cả. Phần 1 sẽ thêm quyền cho nó.

**Tìm Page ID của Fanpage:** mở Fanpage, vào **Giới thiệu, Minh bạch về Trang**, dòng **ID Trang** là một dãy số. Hoặc trong Graph API Explorer (Phần 2), gõ `me/accounts?fields=name,id` rồi bấm Gửi để xem ID mọi Trang.

---

## Phần 1. Chuẩn bị app Meta (làm một lần)

Vào **developers.facebook.com, Ứng dụng của tôi, chọn app của bạn, Trường hợp sử dụng**.

**1.1. Thêm Messenger**

- Bấm **Thêm trường hợp sử dụng**, lọc "Nhắn tin doanh nghiệp".
- Tick **Tương tác với khách hàng trên Messenger from Meta**, bấm **Lưu**.

**1.2. Thêm quyền bình luận**

- Ở dòng **Quản lý mọi thứ trên Trang**, bấm **Tùy chỉnh**.
- Bấm **Thêm** cho 3 quyền:
  - `pages_read_engagement`: đọc bài viết, bình luận
  - `pages_read_user_content`: đọc nội dung khách viết
  - `pages_manage_engagement`: trả lời, sửa, xoá bình luận
- Hộp hỏi "ảnh hưởng trường hợp sử dụng khác" thì bấm **Add**.

Kết quả đúng: các quyền đều hiện **Sẵn sàng thử nghiệm**.

---

## Phần 2. Lấy token trong Graph API Explorer

> Không dùng nút **Tạo** trong mục 2 của Cài đặt API Messenger: token đó chỉ có quyền nhắn tin, không trả lời được bình luận.

- Mở [Graph API Explorer](https://developers.facebook.com/tools/explorer).
- **Ứng dụng trên Meta:** chọn app của bạn.
- **Người dùng hoặc Trang:** chọn **Mã người dùng**.
- **Quyền:** thêm đủ 6 quyền (gõ tên rồi bấm vào gợi ý hiện ra):
  - `pages_show_list`
  - `pages_messaging`
  - `pages_manage_metadata`
  - `pages_read_engagement`
  - `pages_read_user_content`
  - `pages_manage_engagement`
- Bấm **Generate Access Token**. Khi popup hiện ra:
  - Bấm **Chỉnh sửa phần cài đặt** (không bấm Tiếp tục).
  - Chọn **áp dụng cho tất cả Trang ở hiện tại và tương lai**, bấm **Tiếp tục**.
  - Để tất cả công tắc **Bật**, bấm **Lưu**, rồi **OK**.
- Chép chuỗi `EAA...` trong ô **Mã truy cập**.

Token này chỉ sống khoảng một giờ, nhưng không sao: ở Phần 3 Javis tự đổi nó sang **token Trang không hết hạn**. Bạn không cần gia hạn hay lấy token Trang bằng tay.

---

## Phần 3. Dán vào thẻ Facebook Messenger ở trang Kết nối

**3.1. Lấy App ID và App secret**

- Trong app của bạn: **Cài đặt ứng dụng, Thông tin cơ bản**.
- **ID ứng dụng** là App ID. Ô **Khoá bí mật của ứng dụng**, bấm **Hiển thị**, là App secret (32 ký tự).
- Một app dùng chung cho mọi Trang, nên hai thứ này dùng lại được cho Trang sau.

**3.2. Kết nối**

- Mở Javis bằng tên miền HTTPS, vào trang **Kết nối**, thẻ **Facebook Messenger**, bấm **Kết nối**.
- Điền **App ID** và **App secret**.
- Bấm **Dán token thay vì đăng nhập**, điền **Page ID** và dán **token** vừa chép ở Phần 2.
- Bấm **Kết nối và kiểm tra**.

Javis tự làm phần còn lại: đổi sang token Trang không hết hạn, khai webhook vào app Meta, đăng ký ba sự kiện `messages`, `messaging_postbacks`, `feed` cho Trang, rồi hiện bảng kiểm tra từng dòng. Dòng nào đỏ thì có cách sửa ngay bên dưới, hoặc bấm **Sửa tự động**.

---

## Phần 4. Gắn bot

- Vào **Chatbot, Bot**, tạo bot mới hoặc sửa bot đang có.
- Tick kênh Messenger vừa nối (nó đã có sẵn trong danh sách, không cần **Thêm kênh**), bấm **Lưu**, bật bot.
- Muốn bot trả lời cả bình luận: trong danh sách Fanpage của thẻ Messenger, chọn **Bot tự trả lời công khai** ở ô Bình luận Fanpage. Mặc định bình luận chỉ hiện ở Hộp thư để bạn tự trả lời.

---

## Phần 5. Chuyển app sang Live

Ở chế độ phát triển, bot chỉ trả lời người có vai trò trong app (admin, nhà phát triển, người thử nghiệm). Muốn trả lời khách thật:

**5.1. Điền đủ thông tin bắt buộc**

Trong app của bạn: **Cài đặt ứng dụng, Thông tin cơ bản**:

- **URL chính sách quyền riêng tư:** chép **Link chính sách quyền riêng tư** trên thẻ Messenger (dạng `https://<tên-miền-Javis-của-bạn>/messenger/privacy`), dán vào ô này và ô Hướng dẫn xoá dữ liệu.
- **Hạng mục** (Category)
- **Biểu tượng ứng dụng** (App icon)
- Bấm **Lưu thay đổi**.

**5.2. Bật Live**

Gạt **Chế độ ứng dụng** từ Phát triển sang **Live**.

**5.3. Xin quyền nâng cao (Advanced Access)**

Thử bằng một nick Facebook **không có vai trò gì trong app**: nhắn tin và bình luận vào Fanpage. Nếu bot trả lời được thì xong. Nếu Meta vẫn chặn, các quyền dưới đây cần qua **Xét duyệt ứng dụng** để trả lời mọi khách ổn định:

- `pages_messaging`
- `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`
- `pages_manage_metadata`

Vào mục 3 "Hoàn tất quy trình Xét duyệt ứng dụng", **Yêu cầu cấp quyền**, mô tả cách dùng và quay video demo theo hướng dẫn của Meta.

---

## Khi bảng kiểm tra báo webhook đỏ: làm tay

Thường Javis tự khai được. Chỉ làm phần này khi dòng **Webhook của app** hoặc **Trang gắn với app** vẫn đỏ sau khi bấm **Sửa tự động**.

Vào app Meta: **Trường hợp sử dụng, Messenger from Meta, Tùy chỉnh, Cài đặt API Messenger**.

**Cấu hình webhook (mục 1)**

- **URL gọi lại:** chép **Địa chỉ webhook** trên thẻ Messenger ở trang Kết nối.
- **Xác minh mã:** chép **Mã xác minh** ngay bên dưới trên thẻ đó.
- Bấm **Xác minh và lưu**. Có dấu tích xanh là xong.

**Đăng ký sự kiện cho Trang (mục 2)**

- Ở dòng Trang, bấm **Thêm đăng ký** (hoặc "Xem toàn bộ trường thông tin", **Chỉnh sửa**).
- Chỉ tick đúng 3 trường: `messages`, `messaging_postbacks`, `feed`. Bấm **Confirm**.

> Không tick hết. Các trường thừa (calls, standby, messaging_handovers...) gửi về những sự kiện Javis không xử lý, chỉ làm rối.

Xong quay lại thẻ Messenger, bấm **Kiểm tra** ở Trang đó.

---

## Thêm Trang mới (khoảng 2 phút mỗi Trang)

1. Lấy token mới ở Phần 2 (token cũ chỉ sống khoảng một giờ). Nếu lúc cấp quyền bạn đã chọn "tất cả Trang hiện tại và tương lai" thì không phải chỉnh gì thêm.
2. Làm lại Phần 3.2 với **Page ID** của Trang mới. App ID và App secret giữ nguyên.
3. Ở Phần 4, tick thêm kênh mới vào bot đang có.

Hoặc bấm **Đăng nhập Facebook** trên thẻ Messenger và tick nhiều Trang một lần.

Mỗi Trang là một kênh riêng trên Javis. Một bot trực được nhiều kênh cùng lúc (nhiều Fanpage, cả Zalo), nên không cần tạo bot riêng cho từng Trang.

---

## Lỗi hay gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Javis báo token đã hết hạn | Token ở Phần 2 sống khoảng một giờ | Bấm Generate Access Token lấy token mới, dán lại ngay |
| Javis báo token được tạo trong app khác | Chọn nhầm app trong Graph API Explorer | Chọn đúng app ở ô Ứng dụng trên Meta, tạo lại token |
| Bot nhắn được nhưng không trả lời bình luận | Token thiếu quyền bình luận, hoặc ô Bình luận Fanpage đang ở "Hiện ở Hộp thư" | Lấy lại token đủ 6 quyền (Phần 2); đổi ô Bình luận Fanpage sang "Bot tự trả lời công khai" |
| Khách nhắn mà bot im | App còn ở chế độ phát triển, hoặc chưa có bot nào bật cho kênh này | Làm Phần 5; vào Chatbot, Bot kiểm tra bot đã bật |
| Popup cấp quyền chỉ có "nhắn tin" | Đang dùng nút "Thêm trang" trong Cài đặt API Messenger | Dùng Graph API Explorer (Phần 2) |
| Bảng kiểm tra báo webhook đỏ | Javis chưa khai được webhook vào app | Bấm Sửa tự động; vẫn đỏ thì làm tay theo mục "Khi bảng kiểm tra báo webhook đỏ" |
