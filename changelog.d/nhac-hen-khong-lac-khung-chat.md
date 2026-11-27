---
bump: patch
title: Background reminders no longer land in an unrelated chat
---
## vi
### Sửa lỗi
- **Lịch do việc nền tạo không còn chen vào cuộc trò chuyện chẳng liên quan.** Trước đây, khi một luồng việc nền (ví dụ xử lý đơn POSCake) tạo lịch nhắc trong lúc anh đang chat chuyện khác, khung chat đó hiện các dòng "Đã tạo lịch · Hoàn tác", rồi tới giờ lại nhận cả thẻ "Nhắc hẹn". Giờ dòng "Đã tạo lịch" chỉ ghi những gì chính cuộc trò chuyện đó tạo, còn kết quả của lịch việc nền về hộp thư và Javis Core thay vì khung chat đang mở.
- **Lịch tới giờ đã chạy hoặc bị tạm dừng không còn hiện thành "Đã gỡ lịch".** Chỉ lịch mà cuộc trò chuyện huỷ mới có dòng đó.

## en
### Fixed
- **Schedules made by background work no longer show up in an unrelated chat.** Before, when a background flow (for example a POSCake order flow) created a reminder while you were chatting about something else, that chat got "Created schedule · Undo" lines and later the "Reminder" cards too. Now the "Created schedule" line lists only what that chat itself made, and a background job's reminder reports to the inbox and Javis Core instead of whichever chat is open.
- **A schedule that fired or was paused no longer shows as "Removed schedule".** Only a schedule the chat cancelled gets that line.
