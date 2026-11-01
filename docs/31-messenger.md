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
| Bình luận Fanpage | Có (từ 0.434.0): mỗi bình luận gốc là một hội thoại trong Hộp thư |

## Cách nhanh nhất: nút Đăng nhập Facebook (từ 0.434.0)

Không cần Graph API Explorer, không cần chép Page ID hay token. Làm lần đầu và muốn xem từng cú bấm trên trang Meta: [Nối Messenger từng bước](31-messenger-tung-buoc.md).

1. Trên [developers.facebook.com/apps](https://developers.facebook.com/apps), tạo app có trường hợp sử dụng Messenger (một lần, bước 1.1 bên dưới).
2. Mở Javis bằng tên miền HTTPS, vào **Kết nối**, thẻ **Facebook Messenger**, bấm **Kết nối**. Form hiện sẵn hai địa chỉ kèm nút **Chép**:
   - **Địa chỉ quay về**: dán vào ô **Valid OAuth Redirect URIs** trong cài đặt Facebook Login của app.
   - **Link chính sách quyền riêng tư**: Javis tự phục vụ trang này. Dán vào **Cài đặt ứng dụng, Thông tin cơ bản**, ô Chính sách quyền riêng tư và ô Hướng dẫn xoá dữ liệu.
3. Dán **App ID** và **App secret**, chọn cách xử lý bình luận, bấm **Đăng nhập Facebook**. Một tab Facebook mở ra: đăng nhập, tick các Fanpage, đồng ý các quyền.
4. Quay lại tab Javis: danh sách Fanpage hiện ra, tick Trang muốn nối, bấm **Kết nối các Trang đã chọn**. Javis tự lấy token Trang không hết hạn, khai webhook, gắn Trang vào app và hiện bảng kiểm tra cho từng Trang.
5. Chuyển app sang chế độ **Live** (mục 4), rồi vào **Chatbot**, **Bot** để tạo bot cho kênh vừa nối.

## Bình luận Fanpage (từ 0.434.0)

Giống cách Pancake hiển thị: **mỗi bình luận gốc dưới bài viết là một hội thoại riêng** trong Hộp thư, các trả lời bên dưới bình luận đó gom chung vào hội thoại ấy. Tiêu đề hội thoại ghi vài chữ đầu của bài viết. Bạn gõ trả lời trong Hộp thư thì câu đó hiện **công khai ngay dưới bình luận gốc** trên Facebook. Ảnh gửi kèm được, file khác thì không (bình luận chỉ nhận ảnh).

Mỗi Fanpage chọn một trong ba cách, ở form kết nối hoặc trong danh sách Fanpage đã nối:

- **Hiện ở Hộp thư, bạn trả lời** (mặc định): bình luận vào Hộp thư, bot không tự trả lời. Bấm nhờ bot soạn câu trả lời vẫn được như mọi hội thoại khác.
- **Bot tự trả lời công khai**: bot trả lời như tin nhắn, nhưng được dặn rằng câu trả lời ai cũng đọc được nên ngắn gọn, không nêu thông tin riêng, cần thì mời khách nhắn tin cho Page.
- **Tắt**: bỏ qua bình luận.

Bình luận cần thêm quyền `pages_read_user_content` và `pages_manage_engagement` (nút Đăng nhập Facebook tự xin). Bảng kiểm tra có dòng **Nhận bình luận Trang**: vàng là còn thiếu quyền hoặc Trang chưa gửi bình luận sang Javis, bấm Đăng nhập Facebook lại rồi **Sửa tự động**. Thiếu quyền bình luận thì tin nhắn Messenger vẫn chạy bình thường.

## Cách dán token (từ 0.311.0)

Phần dễ sai nhất khi tự làm là token: dán token người dùng thay vì token Trang (lỗi 100, lỗi 210), token ngắn hạn chết sau một giờ, hoặc webhook lưu mà chưa tick `messages` nên bot im lặng. Thẻ này làm hộ các bước đó.

1. Trên Meta, tạo app có trường hợp sử dụng Messenger và kết nối Trang (bước 1.1 đến 1.3 bên dưới, chưa cần bấm Generate).
2. Mở [Graph API Explorer](https://developers.facebook.com/tools/explorer), chọn đúng app, thêm quyền `pages_show_list`, `pages_messaging`, `pages_manage_metadata`, `pages_read_engagement`, bấm **Generate Access Token** và tick đúng Trang. Chép chuỗi `EAA...`.
3. Mở Javis bằng tên miền HTTPS, vào **Kết nối**, thẻ **Facebook Messenger**, bấm **Kết nối**, rồi bấm **Dán token thay vì đăng nhập**. Dán App ID, App secret, Page ID và token vừa chép, bấm **Kết nối và kiểm tra**.
4. Javis đổi sang token Trang không hết hạn, khai webhook của app với `messages` và `messaging_postbacks`, gắn Trang vào app, lưu kênh rồi hiện bảng kiểm tra từng dòng xanh hoặc đỏ kèm cách sửa.
5. Vào **Chatbot**, **Bot** để tạo bot cho kênh vừa nối (mục 3).

Mỗi Trang đã nối có nút **Kiểm tra**, **Sửa tự động** (khai lại webhook và gắn lại Trang) và **Đổi token**. Bộ não nào cũng gọi được tool `messenger_check` và `messenger_repair` khi bot im lặng. Xác minh doanh nghiệp và nộp duyệt `pages_messaging` (mục 4) vẫn làm trên trang Meta.

Cách làm tay bên dưới vẫn dùng được.

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
- Để bot trả lời **mọi người**, chuyển app sang chế độ **Live**. Meta đòi một link chính sách quyền riêng tư: dùng **Link chính sách quyền riêng tư** Javis hiện ở form kết nối.
- Theo tài liệu của Meta, app chỉ nhắn tin cho **Fanpage của chính bạn** thì không cần App Review. Một số người vẫn gặp lỗi khi bot trả lời người lạ dù app đã Live, nên hãy thử bằng **một nick Facebook không có vai trò gì trong app**. Nếu Meta vẫn chặn, nộp **App Review** cho quyền **pages_messaging** (thường kèm xác minh doanh nghiệp). Trong lúc chờ, tin của người ngoài vẫn vào Hộp thư; thẻ bot hiện lỗi kèm lý do.

## Lỗi hay gặp

| Javis báo | Nghĩa là | Cách sửa |
|---|---|---|
| quá 24 giờ kể từ tin cuối | Khách nhắn đã hơn một ngày | Chờ khách nhắn lại, hoặc trả lời từ Meta Business Suite |
| app chưa có quyền nhắn tin cho người ngoài (200) | App còn ở chế độ phát triển, hoặc Meta đòi App Review | Chuyển app sang Live (mục 4); vẫn bị thì nộp xét duyệt pages_messaging |
| Facebook báo URL bị chặn khi đăng nhập | Chưa dán Địa chỉ quay về vào app | Chép Địa chỉ quay về ở form, dán vào Valid OAuth Redirect URIs của Facebook Login |
| app chưa có quyền trả lời bình luận | Thiếu quyền pages_manage_engagement | Bấm Đăng nhập Facebook lại, đồng ý đủ quyền |
| Page access token hết hạn hoặc sai (190) | Token tạm hoặc đã bị thu hồi | Tạo lại token ở bước 1.3, dán lại vào tài khoản kênh |
| Javis chưa tự gắn được Page vào webhook | Token thiếu quyền pages_manage_metadata | Bot vẫn chạy nếu Page đã gắn tay; chưa thì bấm Add Subscriptions cho Page ở Messenger, Webhooks, hoặc tạo lại token khi đang là quản trị viên Page |
| App secret không khớp với app đã tạo Page access token | Chép App secret của app khác | Lấy lại App secret ở App settings, Basic của đúng app đã tạo token. Sai secret thì Meta gửi tin tới mà Javis không tin được chữ ký, nên Javis chặn ngay từ lúc lưu |
| Meta báo không verify được webhook | Callback URL không phải HTTPS, hoặc sai mã | Mở Javis bằng tên miền HTTPS rồi lấy lại địa chỉ ở form |
