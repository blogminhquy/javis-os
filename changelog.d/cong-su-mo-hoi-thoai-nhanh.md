---
bump: patch
title: Partners page opens a new or past conversation faster
---
## vi
### Cải thiện
- **Bấm "Hội thoại mới" ở trang Cộng sự là khung chat trống ngay.** Trước đây phải chờ hai chuyến mạng nối nhau và cột phải dựng lại từ đầu; nay còn một chuyến, số lượt gọi máy chủ giảm từ 18 xuống 7.
- **Chuyển giữa các hội thoại trong Lịch sử nhẹ hơn hẳn.** Danh sách chỉ đổi dòng đang chọn, không tải lại cả danh sách, tin chưa đọc, việc nền và hòm thư mỗi lần bấm (từ khoảng 14 lượt gọi xuống 5).

## en
### Improved
- **New conversation on the Partners page clears the chat at once.** It used to wait for two network round trips in a row and rebuild the right column; now it takes one, and server calls drop from 18 to 7.
- **Switching chats in History is much lighter.** The list only moves its highlight instead of reloading the list, unread counts, background jobs and the inbox on every click (about 14 calls down to 5).
