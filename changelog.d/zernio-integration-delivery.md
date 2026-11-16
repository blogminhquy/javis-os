---
bump: patch
title: Keep Zernio inbox and delivery state accurate
---
## vi
### Sửa lỗi
- Tin nhắn vẫn tới hộp thư khi bridge cũ còn trạng thái tiếp quản hoặc giới hạn. Batch đang chuyển được phục hồi sau khởi động lại.
- Bot Zernio hiển thị đúng trạng thái hoạt động; hộp thư chỉ ghi câu trả lời sau khi nhà cung cấp nhận gửi.

- Form Zernio ẩn đúng ô token cũ và xuống dòng URL webhook trên màn hình hẹp.

## en
### Fixed
- Messages reach the inbox despite legacy bridge takeover or cap state. In-flight batches recover after restart.
- Zernio bots report their running status correctly and record replies only after provider acceptance.
- The Zernio form hides legacy token fields and wraps webhook URLs on narrow screens.
