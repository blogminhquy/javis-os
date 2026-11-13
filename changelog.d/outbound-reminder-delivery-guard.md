---
bump: patch
title: Never confuse group-message actions with owner notifications
---
## vi
### Sửa lỗi
- **Lịch gửi Zalo không còn báo hoàn thành khi chỉ dán chỉ dẫn vào chat.** Chặn cấu hình nhầm `notify_only` và quyền không đủ đối với lệnh gửi tin ra nhóm; các lịch đã lưu sai kiểu sẽ báo lỗi rõ ràng, không lộ prompt nội bộ và không nhận trạng thái hoàn thành giả. Lệnh nhắc người dùng thông thường vẫn hoạt động.

## en
### Fixed
- **Scheduled group messages cannot silently become owner notifications.** Reject outbound-send prompts misconfigured as `notify_only` or without full task permission. Legacy misconfigured notifications fail explicitly instead of echoing internal instructions as successful delivery. Ordinary owner reminders remain unchanged.
