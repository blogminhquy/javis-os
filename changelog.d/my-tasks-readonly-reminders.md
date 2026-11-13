---
bump: patch
title: Read My Tasks safely from read-only scheduled reminders
---
## vi
### Sửa lỗi
- **Nhắc hẹn APEC ở chế độ Chỉ đọc đọc được trạng thái Việc của tôi.** Chỉ thao tác xem danh sách được mở ở quyền read-only; mọi thao tác thêm, sửa, xóa, đánh dấu và bỏ qua vẫn cần quyền ghi. Lịch nhắc tự động không cần nâng lên Toàn quyền.

## en
### Fixed
- **Read-only scheduled reminders can inspect My Tasks.** Only the list action is allowed in read-only mode; create, update, delete, check, uncheck, and skip still require write permission. Reminders do not need elevated privileges.
