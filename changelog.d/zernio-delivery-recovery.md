---
bump: patch
title: Preserve Zernio delivery failures and retry safely after restart
---
## vi
### Sửa lỗi
- Lô trả lời Zernio hết hạn hoặc bị từ chối được giữ để đối soát và chuyển hội thoại cho nhân viên. Tin mới tiếp tục vào hộp thư.
- Lỗi tạm thời chờ tăng dần, tôn trọng Retry-After và giữ câu trả lời cùng khóa gửi khi khởi động lại.

## en
### Fixed
- Expired or rejected Zernio replies are retained for reconciliation and handed to staff. New messages continue reaching the inbox.
- Temporary failures use increasing delays, respect Retry-After and preserve replies and delivery keys across restarts.
