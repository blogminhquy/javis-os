---
bump: minor
title: Chatbots send product photos from the POS, and the Meta insights login explains the missing permission
---
## vi
### Thêm mới
- **Bot chatbot gửi được ảnh sản phẩm lấy từ POS hoặc công cụ nguồn hàng.** Khách xin ảnh thì bot tra sản phẩm trong công cụ đã nối, rồi gửi ảnh mà công cụ đó trả về. Không có nguồn nào có ảnh thì bot nói thẳng là chưa gửi được ảnh, không hứa gửi sau. Bot chỉ gửi link ảnh do chính công cụ hoặc tài liệu của nó đưa ra, không bao giờ tải link khách tự gõ.

### Sửa lỗi
- **Tick "Đọc số liệu bài viết" ở Kết nối Meta không còn bị lỗi khó hiểu.** Facebook báo "Invalid Scopes: read_insights" khi app Meta chưa thêm quyền này. Nút (i) nay chỉ đúng từng bước thêm quyền trong app Meta, và Javis nhắc ngay dưới nút Đăng nhập khi gặp lỗi đó.

## en
### Added
- **Chatbots send product photos from the POS or another product tool.** When a customer asks for a picture, the bot looks the product up in a connected tool and sends the photo that tool returns. When no source has one, it says plainly it cannot send a picture right now, without promising one later. A bot sends only image links its own tools or documents gave it, never a link the customer typed.

### Fixed
- **Ticking "Read post insights" on the Meta card no longer ends in an unexplained error.** Facebook shows "Invalid Scopes: read_insights" when the Meta app has not added that permission. Its (i) now gives the exact steps to add it in the Meta app, and Javis points to them under the login button.
