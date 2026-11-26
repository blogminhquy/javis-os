---
bump: patch
title: NotebookLM stays signed in instead of dropping out after a few hours
---
## vi
### Sửa lỗi
- **NotebookLM không còn mất đăng nhập sau vài giờ.** Phiên bạn dán giờ được lưu vào file riêng của kết nối, chỉ máy bạn đọc được, nên cookie Google đổi định kỳ được giữ lại. Kết nối đang có tự chuyển sang cách này ở lần chạy tới, không cần dán lại.

## en
### Fixed
- **NotebookLM no longer signs out after a few hours.** The session you paste is now kept in the connection's own file, readable only by your account, so the cookies Google rotates are saved. Existing connections switch over on their next start, with no need to paste again.
