# 31 - Messenger (Fanpage Facebook)

***Tiếng Việt** · [English](en/31-messenger.md)*

Từ 0.134.0 một Bot chuyên trách trả lời được hộp thư Fanpage Facebook, giống như bot đang trả lời trên Zalo hay Telegram: cùng Agent, cùng brain, cùng giờ trực, mọi cuộc chat vào Hộp thư, tiếp quản được khi cần người thật.

| | Messenger |
|---|---|
| Javis kết nối thế nào | Webhook: Meta gọi vào Javis, **cần tên miền HTTPS** |
| Nhóm | Không, chỉ chat riêng với Page |
| File | Ảnh và tài liệu, cả hai chiều |
| Tin thoại | Chép thành chữ (cần key Groq ở trang Models) |
| Trả lời | Chỉ trong 24 giờ kể từ tin cuối của khách |
| Định dạng | Chữ thường: Messenger không hiện Markdown, Javis tự bỏ ký hiệu |

## 1. Tạo app Meta (một lần)

1. Mở [developers.facebook.com/apps](https://developers.facebook.com/apps), bấm **Create app**. Chọn mục đích nhắn tin với khách trên Messenger, gắn với Business portfolio của bạn.
2. Trong app, vào **Messenger → Messenger API settings**.
3. Mục **Generate access tokens**: bấm **Connect** (hoặc **Add Page**), chọn Fanpage, rồi bấm **Generate** để lấy **Page access token**. Chép lại.
4. Vào **App settings → Basic**, bấm **Show** ở **App secret**. Chép lại.
5. Lấy **Page ID**: hiện ngay cạnh tên Page ở bước 3, hoặc ở mục Giới thiệu → Minh bạch trang của Fanpage.

## 2. Thêm tài khoản Messenger trong Javis

1. Mở Javis **bằng tên miền HTTPS** (không phải localhost hay IP), vào trang **Chatbot**, tab **Bot**, bấm **Thêm kênh**, chọn **Messenger**.
2. Form hiện **Địa chỉ webhook** và **Mã xác minh**. Quay lại app Meta, mục **Configure webhooks** của Messenger: dán hai thứ này vào Callback URL và Verify token, bấm **Verify and save**. Tick hai trường **messages** và **messaging_postbacks**.
3. Về Javis, dán vào ô token ba thứ cách nhau dấu cách: `Page ID`, `Page access token`, `App secret`. Bấm **Kiểm tra** (Javis hỏi Meta tên Page), rồi **Lưu**.

## 3. Gắn bot

- **Dùng lại bot đang trực Zalo:** mở bot đó ở trang Chatbot, bấm **Sửa**, tick thêm tài khoản Messenger vừa tạo, **Lưu**. Bot trả lời cả Zalo lẫn Messenger bằng cùng một Agent và cùng giờ trực.
- **Hoặc tạo bot mới** chỉ cho Messenger.

Bật bot. Lúc bật, Javis tự đăng ký Page với webhook của app (bạn không phải làm bước này tay); lỗi gì thì thẻ bot báo bằng lời. Nếu token thiếu quyền để tự đăng ký, bot vẫn chạy và thẻ bot nhắc bạn gắn tay một lần: app Meta, Messenger, Webhooks, **Add Subscriptions** cho Page.

## 4. Thử, rồi mở cho mọi người

- Khi app còn ở chế độ phát triển, **chỉ người có vai trò trong app** (admin, developer, tester) nhận được trả lời. Thử bằng chính tài khoản Facebook của bạn: nhắn cho Page một câu.
- Để bot trả lời **mọi người**, app phải qua **App Review** của Meta cho quyền **pages_messaging** (thường kèm xác minh doanh nghiệp và một trang chính sách quyền riêng tư công khai), rồi chuyển app sang **Live**. Trước khi xong bước này, người ngoài nhắn vào Page vẫn được ghi vào Hộp thư nhưng tin trả lời của bot bị Meta chặn; thẻ bot hiện lỗi kèm lý do.

## Lỗi hay gặp

| Javis báo | Nghĩa là | Cách sửa |
|---|---|---|
| quá 24 giờ kể từ tin cuối | Khách nhắn đã hơn một ngày | Chờ khách nhắn lại, hoặc trả lời từ Meta Business Suite |
| app chưa có quyền nhắn tin cho người ngoài (200) | Chưa qua App Review | Thử bằng tài khoản có vai trò trong app, hoặc nộp xét duyệt pages_messaging |
| Page access token hết hạn hoặc sai (190) | Token tạm hoặc đã bị thu hồi | Tạo lại token ở bước 1.3, dán lại vào tài khoản kênh |
| Javis chưa tự gắn được Page vào webhook | Token thiếu quyền pages_manage_metadata | Bot vẫn chạy nếu Page đã gắn tay; chưa thì bấm Add Subscriptions cho Page ở Messenger, Webhooks, hoặc tạo lại token khi đang là quản trị viên Page |
| App secret không khớp với app đã tạo Page access token | Chép App secret của app khác | Lấy lại App secret ở App settings, Basic của đúng app đã tạo token. Sai secret thì Meta gửi tin tới mà Javis không tin được chữ ký, nên Javis chặn ngay từ lúc lưu |
| Meta báo không verify được webhook | Callback URL không phải HTTPS, hoặc sai mã | Mở Javis bằng tên miền HTTPS rồi lấy lại địa chỉ ở form |
