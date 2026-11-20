---
bump: patch
title: Link cards on personal Zalo reach the bot and keep their link
---
## vi
### Sửa lỗi
- **Bot Zalo cá nhân đọc được tin dạng thẻ link.** Trước đây một link người khác gửi (Zalo hiện thành thẻ có tiêu đề và ảnh) bị xếp vào loại "khác" nên bot bỏ qua, kể cả khi người gửi tag bot. Giờ thẻ link được đọc như tin chữ, gồm tiêu đề, mô tả và địa chỉ link.
- **Hộp thư giữ lại địa chỉ link.** Tin thẻ link không còn chỉ hiện dòng mô tả của trang mà có cả link để bấm.

## en
### Fixed
- **The personal Zalo bot reads link cards.** A link someone sent (shown by Zalo as a card with a title and a picture) was filed as "other", so the bot skipped it, even when the sender tagged the bot. A link card is now read as a text message with its title, description and link.
- **The inbox keeps the link.** A link card no longer shows only the page's description: the link itself is there too.
