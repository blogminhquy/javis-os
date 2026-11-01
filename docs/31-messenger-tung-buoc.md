# Nối Fanpage vào Javis từng bước (tin nhắn, bình luận, đăng bài)

***Tiếng Việt** · [English](en/31-messenger-step-by-step.md)*

Hướng dẫn này đi từng cú bấm, dành cho người làm lần đầu. Lần đầu mất khoảng 20 phút, chủ yếu là cài app trên trang Meta. Thêm Trang mới về sau chỉ vài cú bấm.

> **Nối một lần, dùng cho cả ba việc:** bot trả lời tin nhắn, trả lời bình luận, và Javis đăng bài lên Fanpage (ngay khi bạn nhờ hoặc tự động theo lịch). Mọi thao tác trong Javis làm ở một chỗ: thẻ **Facebook Messenger** ở trang **Kết nối**. Nối xong, Fanpage tự có trong danh sách kênh của trang Chatbot, không phải thêm lại ở chỗ nào khác.

Trước khi bắt đầu, bạn cần:

- Javis mở được bằng **tên miền HTTPS** (Cài đặt, Truy cập từ xa). Meta không gửi tin tới localhost hay địa chỉ IP.
- Tài khoản Facebook là **quản trị viên** của Fanpage.
- Một app Meta của riêng bạn. Chưa có thì làm Phần 0. Đã có app (ví dụ app tạo cho thẻ Facebook Trang trong store) thì dùng lại được, bỏ qua Phần 0: một app phục vụ được mọi Fanpage của bạn.

> **Bảo mật:** ai có App secret hay token là điều khiển được Fanpage. Không gửi cho người khác, không chụp màn hình khi đang hiện chúng.

---

## Tổng quan

**Trên trang Meta (làm một lần):**

0. Tạo app Meta (chỉ khi chưa có)
1. Thêm Messenger và các quyền cần thiết
2. Khai Facebook Login và hai địa chỉ của Javis

**Trong Javis:**

3. Bấm Đăng nhập Facebook, chọn Fanpage
4. Gắn bot cho kênh vừa nối

**Mở cho khách thật:**

5. Chuyển app sang Live và thử

Nút Đăng nhập Facebook báo lỗi thì dùng [cách dán token](#nếu-nút-đăng-nhập-facebook-không-chạy-dán-token) ở cuối bài.

---

## Phần 0. Tạo app Meta (chỉ khi chưa có)

App Meta là "giấy phép" để Javis nói chuyện với Facebook thay bạn. Tạo miễn phí, chỉ một lần.

1. Mở [developers.facebook.com](https://developers.facebook.com), đăng nhập bằng tài khoản Facebook là quản trị viên Fanpage.
2. Lần đầu vào, Meta hỏi đăng ký làm nhà phát triển: bấm **Bắt đầu**, xác minh số điện thoại hoặc email, chọn vai trò bất kỳ (ví dụ "Chủ doanh nghiệp").
3. Vào **Ứng dụng của tôi**, bấm **Tạo ứng dụng**.
4. Đặt **tên ứng dụng** tuỳ ý (ví dụ tên shop của bạn kèm chữ "Bot"), điền email liên hệ, bấm **Tiếp**.
5. Ở bước chọn trường hợp sử dụng, chọn **Tương tác với khách hàng trên Messenger from Meta** (nằm trong nhóm Nhắn tin doanh nghiệp). Không thấy thì chọn **Khác** rồi chọn loại **Doanh nghiệp**.
6. Bước chọn Danh mục doanh nghiệp (Business portfolio): chọn danh mục đang quản lý Fanpage, hoặc "Tôi chưa muốn kết nối" nếu chưa có. Bấm **Tạo ứng dụng**, nhập lại mật khẩu Facebook nếu được hỏi.

Xong bước này bạn có một app, chưa làm được gì cả. Phần 1 thêm quyền cho nó.

**Tìm Page ID của Fanpage:** mở Fanpage, vào **Giới thiệu, Minh bạch về Trang**, dòng **ID Trang** là một dãy số. Đi đường Đăng nhập Facebook thì không cần Page ID: Javis tự liệt kê các Trang.

---

## Phần 1. Thêm Messenger và các quyền cần thiết

Vào **developers.facebook.com, Ứng dụng của tôi, chọn app của bạn, Trường hợp sử dụng**.

**1.1. Thêm Messenger**

- Bấm **Thêm trường hợp sử dụng**, lọc "Nhắn tin doanh nghiệp".
- Tick **Tương tác với khách hàng trên Messenger from Meta**, bấm **Lưu**. Trường hợp sử dụng này kèm sẵn quyền nhắn tin (`pages_messaging`), xem danh sách Trang (`pages_show_list`) và gắn Trang vào app (`pages_manage_metadata`).

**1.2. Thêm quyền bình luận và đăng bài**

- Ở dòng **Quản lý mọi thứ trên Trang**, bấm **Tùy chỉnh**.
- Bấm **Thêm** cho 4 quyền:
  - `pages_read_engagement`: đọc bài viết, bình luận
  - `pages_read_user_content`: đọc nội dung khách viết
  - `pages_manage_engagement`: trả lời bình luận
  - `pages_manage_posts`: đăng bài, ảnh, video, sửa và xoá bài
- Hộp hỏi "ảnh hưởng trường hợp sử dụng khác" thì bấm **Add**.

Kết quả đúng: các quyền đều hiện **Sẵn sàng thử nghiệm**. Thiếu quyền nào thì lúc đăng nhập Facebook sẽ báo lỗi "Invalid Scopes" kèm tên quyền đó.

---

## Phần 2. Khai Facebook Login và hai địa chỉ của Javis

**2.1. Lấy hai địa chỉ từ Javis**

- Mở Javis bằng tên miền HTTPS, vào trang **Kết nối**, thẻ **Facebook Messenger**, bấm **Kết nối**.
- Form hiện sẵn hai dòng, mỗi dòng có nút **Chép**:
  - **Địa chỉ quay về**, dạng `https://<tên-miền-Javis-của-bạn>/messenger/oauth/callback`
  - **Link chính sách quyền riêng tư**, dạng `https://<tên-miền-Javis-của-bạn>/messenger/privacy`
- Để form đó mở, lát nữa quay lại điền tiếp.

**2.2. Khai Địa chỉ quay về vào Facebook Login**

- Trong app Meta, tìm mục **Facebook Login** ở menu bên trái. Tên có thể là **Facebook Login for Business** hoặc **Đăng nhập Facebook cho doanh nghiệp**. Chưa có thì bấm **Thêm sản phẩm** (hoặc **Thêm trường hợp sử dụng**) và chọn nó.
- Vào **Cài đặt** của Facebook Login.
- Hai công tắc **Đăng nhập OAuth ứng dụng khách** và **Đăng nhập OAuth trên web** phải **Bật** (mặc định đã bật).
- Ô **URI chuyển hướng OAuth hợp lệ** (Valid OAuth Redirect URIs): dán **Địa chỉ quay về** vừa chép, đúng từng ký tự.
- Bấm **Lưu thay đổi**.

Thiếu bước này, lúc bấm Đăng nhập Facebook sẽ gặp lỗi "URL bị chặn".

**2.3. Điền thông tin cơ bản của app**

Vào **Cài đặt ứng dụng, Thông tin cơ bản**:

- **URL chính sách quyền riêng tư** và **Hướng dẫn xoá dữ liệu người dùng**: dán **Link chính sách quyền riêng tư** từ Javis vào cả hai ô. Javis tự phục vụ trang này trên tên miền của bạn.
- **Hạng mục** (Category) và **Biểu tượng ứng dụng** (App icon): chọn bất kỳ cho hợp với shop.
- Bấm **Lưu thay đổi**.
- Chép hai thứ trên trang này để dùng ở Phần 3: **ID ứng dụng** (App ID) và **Khoá bí mật của ứng dụng** (App secret, bấm **Hiển thị**, đủ 32 ký tự).

---

## Phần 3. Bấm Đăng nhập Facebook, chọn Fanpage

Quay lại form Facebook Messenger trong Javis (Phần 2.1):

1. Điền **App ID** và **App secret**.
2. Ô **Bình luận Fanpage**, chọn một trong ba:
   - **Hiện ở Hộp thư, bạn trả lời** (mặc định): mỗi bình luận gốc thành một hội thoại trong Hộp thư, bạn trả lời tay hoặc nhờ bot soạn.
   - **Bot tự trả lời công khai**: bot trả lời ngay dưới bình luận.
   - **Tắt**: bỏ qua bình luận.
3. Bấm **Đăng nhập Facebook**. Một tab Facebook mở ra:
   - Đăng nhập bằng tài khoản quản trị viên Fanpage.
   - Bấm **Chỉnh sửa cài đặt** (hoặc **Chọn Trang**), tick những Fanpage muốn nối.
   - Đồng ý **tất cả** quyền Facebook hỏi, đừng tắt quyền nào.
   - Xong, tab báo "Đã đăng nhập Facebook" rồi tự đóng.
4. Quay lại tab Javis: danh sách Fanpage hiện ra, mặc định tick hết. Bỏ tick Trang không muốn nối, bấm **Kết nối các Trang đã chọn**.

Javis tự làm phần còn lại cho từng Trang: lấy token Trang không hết hạn, khai webhook vào app Meta, đăng ký tin nhắn và bình luận, rồi hiện bảng kiểm tra. Dòng xanh là xong. Dòng vàng là nhắc nhẹ, bot vẫn chạy. Dòng đỏ có cách sửa ngay bên dưới, hoặc bấm **Sửa tự động** trong danh sách Fanpage.

> Trình duyệt chặn tab mới thì dưới nút sẽ hiện link **Mở trang đăng nhập Facebook**, bấm vào đó.

---

## Phần 4. Gắn bot cho kênh vừa nối

Chưa có bot thì Javis chưa nhận tin, Hộp thư cũng trống.

- Vào **Chatbot, Bot**, tạo bot mới hoặc bấm **Sửa** ở bot đang có (ví dụ bot đang trực Zalo).
- Tick kênh Messenger vừa nối. Kênh đã có sẵn trong danh sách, không cần **Thêm kênh**.
- Bấm **Lưu**, bật bot.

Một bot trực được nhiều kênh cùng lúc (nhiều Fanpage, cả Zalo), dùng chung một Agent và giờ trực.

**Đăng bài:** không cần cài thêm gì. Nhắn Javis kiểu "đăng bài này lên Fanpage kèm 3 ảnh" hoặc "8 giờ sáng mỗi ngày đăng một bài giới thiệu sản phẩm" là Javis dùng đúng kết nối này. Đăng và sửa bài là việc thật, công khai, nên chỉ chạy khi Javis ở mức Toàn quyền. Muốn đổi cách xử lý bình luận về sau: trang **Kết nối**, thẻ Facebook Messenger, **Xem chi tiết**, ô Bình luận Fanpage ở từng Trang.

---

## Phần 5. Chuyển app sang Live và thử

Ở chế độ phát triển, bot chỉ trả lời người có vai trò trong app (admin, nhà phát triển, người thử nghiệm). Muốn trả lời khách thật:

**5.1. Bật Live**

Trong app Meta, gạt **Chế độ ứng dụng** từ Phát triển sang **Live**. Meta đòi đủ thông tin ở Phần 2.3; thiếu ô nào nó sẽ chỉ ra.

**5.2. Thử bằng người ngoài**

Nhờ một người, hoặc dùng một nick Facebook **không có vai trò gì trong app**: nhắn tin cho Fanpage và bình luận dưới một bài viết. Tin nhắn và bình luận phải hiện trong **Hộp thư** của Javis, và bot trả lời được (nếu đã bật).

**5.3. Nếu Meta vẫn chặn: xin quyền nâng cao (Advanced Access)**

Theo tài liệu của Meta, app chỉ phục vụ Fanpage của chính bạn thì không cần xét duyệt. Nếu thử ở 5.2 mà bot vẫn không trả lời được người ngoài, các quyền dưới đây cần qua **Xét duyệt ứng dụng**:

- `pages_messaging`
- `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`
- `pages_manage_metadata`

Vào mục "Xét duyệt ứng dụng", **Yêu cầu cấp quyền**, mô tả cách dùng và quay video demo theo hướng dẫn của Meta. Trong lúc chờ, tin của khách vẫn vào Hộp thư để bạn trả lời tay từ Meta Business Suite.

---

## Thêm Trang mới

Bấm **Kết nối** trên thẻ Facebook Messenger lần nữa, điền lại App ID và App secret, **Đăng nhập Facebook**, tick Trang mới. Phần 0 đến Phần 2 không phải làm lại. Sau đó tick kênh mới vào bot ở Phần 4.

---

## Nếu nút Đăng nhập Facebook không chạy: dán token

Dùng khi Phần 3 báo lỗi mà không sửa được. Phần 0, 1 và 2.3 vẫn cần làm; Phần 2.2 (Facebook Login) thì không.

**A. Lấy token trong Graph API Explorer**

> Không dùng nút **Tạo** trong mục 2 của Cài đặt API Messenger: token đó chỉ có quyền nhắn tin, không trả lời được bình luận.

- Mở [Graph API Explorer](https://developers.facebook.com/tools/explorer).
- **Ứng dụng trên Meta:** chọn app của bạn. **Người dùng hoặc Trang:** chọn **Mã người dùng**.
- **Quyền:** thêm đủ 7 quyền: `pages_show_list`, `pages_messaging`, `pages_manage_metadata`, `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`, `pages_manage_posts`.
- Bấm **Generate Access Token**, bấm **Chỉnh sửa phần cài đặt**, chọn **áp dụng cho tất cả Trang ở hiện tại và tương lai**, để mọi công tắc **Bật**, **Lưu**.
- Chép chuỗi `EAA...` trong ô **Mã truy cập**. Token này chỉ sống khoảng một giờ, Javis sẽ tự đổi sang token Trang không hết hạn nên không cần gia hạn.

**B. Dán vào Javis**

- Trên form Facebook Messenger: điền **App ID**, **App secret**.
- Bấm **Dán token thay vì đăng nhập**, điền **Page ID** (Phần 0 có cách tìm) và dán **token**.
- Bấm **Kết nối và kiểm tra**. Javis làm phần còn lại như Phần 3.

Rồi làm tiếp Phần 4 và 5.

---

## Khi bảng kiểm tra báo webhook đỏ: làm tay

Thường Javis tự khai được. Chỉ làm phần này khi dòng **Webhook của app** hoặc **Trang gắn với app** vẫn đỏ sau khi bấm **Sửa tự động**.

Vào app Meta: **Trường hợp sử dụng, Messenger from Meta, Tùy chỉnh, Cài đặt API Messenger**.

- **Cấu hình webhook (mục 1):** ô **URL gọi lại** dán **Địa chỉ webhook**, ô **Xác minh mã** dán **Mã xác minh** (cả hai có trên form Facebook Messenger, mỗi dòng có nút Chép). Bấm **Xác minh và lưu**.
- **Đăng ký sự kiện cho Trang (mục 2):** ở dòng Trang, bấm **Thêm đăng ký**, chỉ tick đúng 3 trường `messages`, `messaging_postbacks`, `feed`, bấm **Confirm**. Không tick hết: các trường thừa gửi về sự kiện Javis không xử lý.

Xong quay lại thẻ Messenger, bấm **Kiểm tra** ở Trang đó.

---

## Lỗi hay gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Facebook báo "URL bị chặn" khi đăng nhập | Chưa dán Địa chỉ quay về vào Facebook Login | Làm Phần 2.2, dán đúng từng ký tự |
| Facebook báo "Invalid Scopes" kèm tên quyền | App chưa thêm quyền đó | Làm Phần 1, thêm đủ quyền rồi đăng nhập lại |
| Javis báo "App ID hoặc App secret không đúng" | Chép nhầm, hoặc lấy App secret của app khác | Chép lại cả hai ở Cài đặt ứng dụng, Thông tin cơ bản |
| Javis báo tài khoản không quản lý Fanpage nào | Lúc đăng nhập chưa tick Trang | Đăng nhập Facebook lại, bấm Chỉnh sửa cài đặt, tick đúng Trang |
| Đã nối nhưng khách nhắn bot im | Chưa gắn bot, hoặc app còn ở chế độ phát triển | Làm Phần 4 và Phần 5 |
| Javis báo chưa có quyền đăng bài | Trang nối trước bản 0.438.0, hoặc chưa thêm quyền `pages_manage_posts` | Thêm quyền ở Phần 1.2, rồi Đăng nhập Facebook lại trên thẻ Messenger |
| Tin nhắn chạy nhưng bình luận không vào | Thiếu quyền bình luận, hoặc ô Bình luận Fanpage đang Tắt | Thêm quyền ở Phần 1.2, đăng nhập lại; đổi ô Bình luận Fanpage |
| Bình luận vào Hộp thư nhưng bot không trả lời | Ô Bình luận Fanpage đang ở "Hiện ở Hộp thư" | Đổi sang "Bot tự trả lời công khai" nếu muốn bot trả lời |
| Bảng kiểm tra báo webhook đỏ | Javis chưa khai được webhook | Bấm Sửa tự động; vẫn đỏ thì làm tay theo mục ngay trên |
