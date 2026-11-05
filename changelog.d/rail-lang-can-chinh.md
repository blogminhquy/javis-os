---
bump: patch
title: Chat label no longer shows as page.chat.label after an update; tidier sidebar language picker
---
## vi
### Sửa lỗi
- **Mục Trò chuyện trên đầu thanh bên không còn hiện `page.chat.label`.** Ngay sau khi cập nhật, lúc máy chủ còn đang khởi động, từ điển về chậm và mục này giữ nguyên khoá thô. Giờ mọi mục trên thanh bên tự đổi chữ khi từ điển về.
- **Ô chọn ngôn ngữ ở chân thanh bên trái hết dính vào hàng phiên bản.** Ô và hàng phiên bản giờ chung một đường kẻ, cách nhau đều, ô cao bằng nút thu/mở và chữ to hơn chút cho dễ đọc. Khi chỉ có một ngôn ngữ, ô trống không còn hiện ra.

## en
### Fixed
- **The Chat entry at the top of the sidebar no longer shows `page.chat.label`.** Right after an update, while the server was still starting, the dictionary arrived late and this entry kept the raw key. Every sidebar entry now redraws its text when the dictionary arrives.
- **The language picker in the sidebar foot no longer sticks to the version row.** The picker and the version row now share one divider with even spacing, the picker matches the collapse button's height and its text is a little larger. With only one language the empty picker no longer shows.
