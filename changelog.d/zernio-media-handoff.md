---
bump: patch
title: Hand unsupported Zernio media to staff without guessing
---
## vi
### Sửa lỗi
- Tin có ảnh, album hoặc tệp chưa được hỗ trợ được chuyển cho nhân viên, giữ nguyên chữ và tệp trong hộp thư. AI không tự trả lời như đã đọc ảnh.
- Trạng thái bàn giao được giữ khi khởi động lại; webhook lặp không tạo thêm sự cố.

## en
### Fixed
- Images, albums and unsupported attachments are handed to staff with their text and attachments preserved in the inbox. AI does not reply as if it had read the images.
- Handoffs survive restarts, and repeated webhooks do not create duplicate issues.
