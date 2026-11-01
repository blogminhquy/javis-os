# Nối Fanpage Messenger vào Javis từng bước (nhắn tin và trả lời bình luận)

***Tiếng Việt** · [English](en/31-messenger-step-by-step.md)*

Hướng dẫn này đi từng cú bấm trên trang Meta, dành cho người mới làm lần đầu. Tổng thời gian lần đầu khoảng 20 phút. Thêm Trang mới về sau khoảng 2 phút mỗi Trang.

> **Có cách nhanh hơn:** từ 0.434.0, thẻ **Facebook Messenger** ở trang **Kết nối** có nút **Đăng nhập Facebook**. Bấm đăng nhập, tick Trang là Javis tự lấy token, bỏ qua được Phần 3 và Phần 4 bên dưới. Xem [31 - Messenger](31-messenger.md). Hướng dẫn này là cách dán token bằng tay, dùng khi nút đăng nhập không chạy hoặc bạn muốn tự kiểm soát từng bước.

Trước khi bắt đầu, bạn cần:

- Javis mở được bằng **tên miền HTTPS** (Cài đặt, Truy cập từ xa). Meta không gửi tin tới localhost hay địa chỉ IP.
- Tài khoản Facebook là **quản trị viên** của Fanpage.
- Một app Meta của riêng bạn. Chưa có thì làm Phần 0 bên dưới. Đã có app (ví dụ app tạo cho thẻ Facebook Trang trong store) thì dùng lại được, bỏ qua Phần 0: một app phục vụ được mọi Fanpage của bạn.

> **Bảo mật:** ai có token hoặc App secret là điều khiển được Fanpage. Không gửi cho người khác, không chụp màn hình khi đang hiện token.

---

## Tổng quan

0. Tạo app Meta (chỉ khi chưa có)
1. Chuẩn bị app Meta (thêm Messenger và quyền bình luận)
2. Đặt webhook và đăng ký sự kiện cho Trang
3. Tạo token Trang đủ quyền, không hết hạn
4. Dán vào Javis
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

**Tìm Page ID của Fanpage:** mở Fanpage, vào **Giới thiệu, Minh bạch về Trang**, dòng **ID Trang** là một dãy số. Cũng có thể lấy ở Phần 3.3.

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

## Phần 2. Webhook và đăng ký sự kiện

Vào **Trường hợp sử dụng, Messenger from Meta, Tùy chỉnh, Cài đặt API Messenger**.

**2.1. Đặt cấu hình webhook (mục 1)**

Lấy hai thứ trên form của Javis: **Chatbot, Kênh, Thêm kênh, Messenger**. Form hiện sẵn **Địa chỉ webhook (Callback URL)** và **Mã xác minh (Verify token)**.

- URL gọi lại: dán Địa chỉ webhook, dạng `https://<tên-miền-Javis-của-bạn>/messenger/webhook`
- Xác minh mã: dán Mã xác minh
- Bấm **Xác minh và lưu**. Có dấu tích xanh là xong.

**2.2. Đăng ký sự kiện cho Trang (mục 2)**

- Ở dòng Trang cần gắn bot, bấm **Thêm đăng ký** (hoặc "Xem toàn bộ trường thông tin", **Chỉnh sửa**).
- Chỉ tick đúng 3 trường:
  - `messages`: tin nhắn
  - `messaging_postbacks`: khách bấm nút
  - `feed`: bình luận, bài viết
- Bấm **Confirm**.

> Không tick hết. Các trường thừa (calls, standby, messaging_handovers...) gửi về những sự kiện Javis không xử lý, chỉ làm rối.

---

## Phần 3. Tạo token Trang đủ quyền, không hết hạn

> Không dùng nút **Tạo** trong mục 2 của Cài đặt API Messenger: token đó chỉ có quyền nhắn tin, không trả lời được bình luận.

**3.1. Tạo token người dùng có đủ quyền**

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

**3.2. Gia hạn thành token dài hạn**

- Bấm biểu tượng **(i)** cạnh ô Mã truy cập, chọn **Mở trong Công cụ mã truy cập**.
- Kéo xuống, bấm **Mã truy cập mở rộng**, nhập lại mật khẩu Facebook nếu được hỏi.
- Chép token mới hiện ra bên dưới nút đó.

Kiểm tra: dán token vào trình gỡ lỗi, phải thấy **Loại: User**, **Hết hạn: Không bao giờ**, và mục Phạm vi có đủ 6 quyền.

**3.3. Lấy token của từng Trang**

- Quay lại Graph API Explorer, dán token dài hạn vào ô **Mã truy cập**.
- **Không bấm Generate Access Token nữa** (bấm là mất token dài hạn vừa làm).
- Ô truy vấn gõ: `PAGE_ID?fields=name,access_token` (thay `PAGE_ID` bằng dãy số ID của Trang).
- Bấm **Gửi**, chép giá trị `access_token` (phần trong ngoặc kép, không lấy dấu ngoặc kép).

Muốn xem token của mọi Trang cùng lúc: gõ `me/accounts?fields=name,id,access_token`.

---

## Phần 4. Dán vào Javis

**4.1. Lấy App secret**

- Trong app của bạn: **Cài đặt ứng dụng, Thông tin cơ bản**, ô **Khoá bí mật của ứng dụng**, bấm **Hiển thị**.
- App secret dùng chung cho mọi Trang của cùng một app.

**4.2. Ghép một dòng**

Mở Notepad, ghép 3 thứ trên **cùng một dòng**, cách nhau **một dấu cách**:

```
PAGE_ID TOKEN_TRANG APP_SECRET
```

Javis tự nhận ra từng phần theo hình dạng, nhưng giữ đúng thứ tự trên cho dễ kiểm.

**4.3. Lưu trên Javis**

- Javis, **Chatbot, Kênh, Thêm kênh, Messenger**.
- Dán dòng trên vào ô **Token Messenger**, bấm **Kiểm tra**.
- Đúng khi hiện: "✓ Đúng bot PAGE_ID (Tên Trang)".
- Điền **Tên gợi nhớ**, bấm **Lưu**.
- Vào **Chatbot, Bot**, tạo bot mới hoặc sửa bot đang có, tick kênh Messenger vừa thêm, bật bot.

> Cách khác: thẻ **Facebook Messenger** ở trang **Kết nối**, mục **Dán token thay vì đăng nhập**, nhận App ID, App secret, Page ID và token riêng từng ô, rồi tự khai webhook, tự đăng ký sự kiện và hiện bảng kiểm tra. Kênh nối ở đâu cũng là một, hiện ở cả hai trang.

---

## Phần 5. Chuyển app sang Live

Ở chế độ phát triển, bot chỉ trả lời người có vai trò trong app (admin, nhà phát triển, người thử nghiệm). Muốn trả lời khách thật:

**5.1. Điền đủ thông tin bắt buộc**

Trong app của bạn: **Cài đặt ứng dụng, Thông tin cơ bản**:

- **URL chính sách quyền riêng tư:** Javis có sẵn trang này tại `https://<tên-miền-Javis-của-bạn>/messenger/privacy`, dán vào ô này và ô Hướng dẫn xoá dữ liệu.
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

## Thêm Trang mới (khoảng 2 phút mỗi Trang)

Token người dùng dài hạn ở Phần 3.2 dùng lại được, không phải làm lại từ đầu:

1. **Phần 2.2:** đăng ký `messages`, `messaging_postbacks`, `feed` cho Trang mới.
2. **Phần 3.3:** đổi `PAGE_ID` trong truy vấn, lấy token Trang mới.
3. **Phần 4:** thêm một kênh Messenger mới trên Javis, dán `PAGE_ID TOKEN_TRANG APP_SECRET`.

Mỗi Trang là một token riêng, một kênh riêng trên Javis. Một bot trực được nhiều kênh cùng lúc (nhiều Fanpage, cả Zalo), nên không cần tạo bot riêng cho từng Trang.

---

## Lỗi hay gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Javis báo "Còn thiếu: Page ID, App secret" | Mới dán mỗi token | Dán đủ 3 thứ trên một dòng (Phần 4.2) |
| Bot nhắn được nhưng không trả lời bình luận | Token thiếu quyền bình luận, hoặc Trang chưa đăng ký `feed` | Kiểm tra Phạm vi của token (Phần 3.2) và đăng ký `feed` (Phần 2.2) |
| Khách nhắn mà bot im | App còn ở chế độ phát triển, hoặc chưa có bot nào bật cho kênh này | Làm Phần 5; vào Chatbot, Bot kiểm tra bot đã bật |
| Popup cấp quyền chỉ có "nhắn tin" | Đang dùng nút "Thêm trang" trong Cài đặt API Messenger | Dùng Graph API Explorer (Phần 3.1) |
| Token cũ hết tác dụng | Đã bấm Generate lại, hoặc đổi mật khẩu Facebook | Làm lại Phần 3, cập nhật token trên Javis |
| "Hết hạn truy cập dữ liệu: khoảng 3 tháng" | Quy định của Meta với người dùng | Vào lại app định kỳ, hoặc làm lại Phần 3.1 khi được nhắc |
