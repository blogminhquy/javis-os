# 35 - Zalo OA (Official Account)

***Tiếng Việt** · [English](en/35-zalo-oa.md)*

Từ 0.412.0 một Bot chuyên trách trả lời được hộp thư **Zalo Official Account** (trang doanh nghiệp khách bấm Quan tâm), giống bot đang trả lời trên Zalo Bot, Messenger hay Telegram: cùng Agent, cùng brain, cùng giờ trực, mọi cuộc chat vào Hộp thư, tiếp quản được khi cần người thật.

Kênh này khác hai kênh Zalo có sẵn:

- **Zalo Bot** (tài liệu 26): bot tạo trong "Zalo Bot Manager", tên phải mở đầu bằng chữ Bot. Không cần tên miền.
- **Zalo cá nhân** (tài liệu 12): chính nick Zalo của bạn, đăng nhập bằng QR.
- **Zalo OA** (tài liệu này): trang Official Account của doanh nghiệp, đi qua API chính thức OA Open API v3.

| | Zalo OA |
|---|---|
| Javis kết nối thế nào | Webhook: Zalo gọi vào Javis, **cần tên miền HTTPS** |
| Nhóm | Không, chỉ chat riêng với OA |
| File | Nhận ảnh, file, tin thoại. Gửi ảnh JPG/PNG/GIF (tối đa 1MB) và PDF, DOC, DOCX (tối đa 5MB) |
| Tin thoại | Chép thành chữ (cần key Groq ở trang Models) |
| Trả lời | Bằng "tin tư vấn", chỉ trong khung thời gian Zalo cho phép sau tin cuối của khách |
| Định dạng | Chữ thường: Zalo không hiện Markdown, Javis tự bỏ ký hiệu |

## 1. Tạo app trên Zalo for Developers (một lần)

1. Mở [developers.zalo.me](https://developers.zalo.me), đăng nhập bằng tài khoản quản trị OA, bấm **Tạo ứng dụng**.
2. Trong app, mục **Official Account**, liên kết OA của bạn với app.
3. Chép **App ID** và **Khóa bí mật của ứng dụng** (App secret key) ở trang Thông tin ứng dụng.

## 2. Xác thực tên miền và đặt webhook

Zalo chỉ gửi tin vào một địa chỉ HTTPS trên tên miền đã xác thực.

1. Mở Javis **bằng tên miền HTTPS**, vào **Chatbot**, tab **Bot**, bấm **Thêm kênh**, chọn **Zalo OA**. Form hiện **Địa chỉ webhook** và ô **Mã xác thực tên miền Zalo**.
2. Trên Zalo, mục **Xác thực tên miền**, nhập tên miền của Javis, chọn cách xác thực bằng **file HTML**. Zalo cho tên file dạng `zalo_verifier<mã>.html`.
3. Dán tên file đó (hoặc thẻ meta Zalo đưa) vào ô của Javis, bấm **Lưu mã**. Javis bắt đầu phục vụ đúng file đó. Quay lại Zalo bấm **Xác thực**.
4. Vào mục **Webhook** của app, dán **Địa chỉ webhook** Javis hiện (dạng `https://<tên miền>/zalo-oa/webhook`), bật các sự kiện **user_send_text**, **user_send_image**, **user_send_file**, **user_send_audio**, **user_send_sticker**, **user_send_location**.
5. Ở mục Webhook có **OA secret key** (khóa bí mật của OA). Chép lại: Javis dùng nó để kiểm chữ ký từng tin, tin không đúng chữ ký bị bỏ.

## 3. Lấy Refresh token

Access token của Zalo OA chỉ sống khoảng 25 giờ, nên Javis giữ **refresh token** và tự làm mới. Mỗi refresh token chỉ dùng được **một lần** và sống khoảng 3 tháng; mỗi lần làm mới Zalo trả về một cặp mới và Javis lưu ngay vào kho tài khoản đã mã hoá.

1. Mở **API Explorer** trên developers.zalo.me (mục Công cụ).
2. Chọn loại token **OA Access Token**, chọn đúng app và OA, bấm lấy token, cho phép app truy cập OA.
3. Chép **Refresh token** (chuỗi dài). Không cần chép access token.

## 4. Thêm tài khoản Zalo OA trong Javis

1. Ở form **Thêm kênh**, **Zalo OA**, dán bốn thứ cách nhau dấu cách, đúng thứ tự:

   ```
   <App ID> <App secret key> <OA secret key> <Refresh token>
   ```

   Muốn chắc thứ tự hai khoá ngắn thì ghi tên: `app_secret=...` và `oa_secret=...`.
2. Bấm **Kiểm tra**. Javis làm mới token một lần và đọc tên OA. Đúng thì hiện tên OA.
3. Bấm **Lưu** ngay sau đó. Lúc kiểm tra, refresh token vừa dán đã bị dùng mất; cặp mới nằm chờ trong Javis khoảng 30 phút và được ghi vào tài khoản khi bạn lưu. Nếu Javis khởi động lại giữa hai bước, lấy refresh token mới ở API Explorer rồi dán lại.
4. Vào **Chatbot**, **Bot** để tạo bot hoặc gắn bot có sẵn cho kênh này. Bot bật lên là bắt đầu trả lời khách nhắn OA.

## 5. Khi bot im lặng

- **Bot báo thiếu OA secret key:** Javis không cho bot chạy khi thiếu khoá này, vì mọi tin sẽ bị từ chối chữ ký mà không ai biết. Sửa kênh, dán lại đủ bốn thứ.
- **"Zalo không làm mới được token":** refresh token sai, đã dùng rồi, hoặc quá 3 tháng. Lấy refresh token mới, sửa kênh và dán lại.
- **Lỗi -230 hoặc báo khách lâu không nhắn:** Zalo chỉ cho OA trả lời trong một khung thời gian sau tin cuối của khách. Khách nhắn lại là mở lại.
- **Lỗi -224:** gói dịch vụ của OA chưa cho dùng tính năng này qua API. Kiểm tra gói ở [oa.zalo.me](https://oa.zalo.me).
- **Không có tin nào tới:** kiểm tra webhook đúng địa chỉ HTTPS của Javis và đã bật sự kiện user_send_*. Zalo bỏ webhook nếu Javis không trả lời nhiều lần liền, khi đó bật lại ở trang app.

Javis không đọc lại được tin nhắn cũ của OA trước lúc nối: Hộp thư bắt đầu từ tin đầu tiên tới qua webhook.
