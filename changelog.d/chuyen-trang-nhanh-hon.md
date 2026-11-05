---
bump: minor
title: Chats, Tasks and Teams open at once when switching
---
## vi
### Cải thiện
- **Chuyển qua lại giữa các cuộc chat hiện ngay.** Cuộc đã mở gần đây vẽ lại tức thì rồi tự cập nhật ngầm; rê chuột hay chạm vào một cuộc trong danh sách là nó bắt đầu tải trước khi bấm. Dựng một cuộc chat (kể cả lúc F5) cũng nhanh hơn nhiều lần vì không còn cuộn theo từng tin. Ở trang Cộng sự, bấm một trợ lý mở luôn cuộc gần nhất thay vì chờ hai lượt hỏi máy chủ nối đuôi.
- **Trang Nhiệm vụ và trang Nhóm quay lại là thấy ngay** nội dung lần trước, không còn màn "Đang tải" trống. Nhóm đã mở gần đây cũng hiện tin ngay khi chuyển qua lại.
- **Hết cảnh lúc nhanh lúc chậm 1-2 giây khi Javis đang bận.** Đọc lịch sử chat không còn xếp hàng sau các lượt ghi, các lượt đọc nặng của trang Nhiệm vụ không còn chặn máy chủ, và mở một nhóm không phải tính lại thống kê mỗi lần.
- Code của từng trang tải song song và ưu tiên Nhiệm vụ, Nhóm; rê chuột vào mục menu là trang đó bắt đầu tải.

## en
### Improved
- **Switching between chats is instant.** A chat opened recently draws at once and refreshes behind; pointing at or touching a chat in the list starts loading it before the click. Building a chat (F5 included) is also several times faster, as it no longer scrolls after every message. On the Partners page, picking an assistant opens its latest chat right away instead of waiting on two server calls in a row.
- **The Tasks and Teams pages show their last content at once** when you come back, with no blank "Loading" screen. Teams opened recently also show their messages at once when you switch.
- **No more "sometimes instant, sometimes 1-2 seconds" while Javis is busy.** Reading chat history no longer queues behind writes, the heavy Tasks page reads no longer stall the server, and opening a team no longer recomputes its usage every time.
- Each page's code downloads in parallel, with Tasks and Teams first; pointing at a menu item starts loading that page.
