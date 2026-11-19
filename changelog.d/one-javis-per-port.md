---
bump: patch
title: A stray second Javis can no longer hold the port and keep the real one restarting
---
## vi
### Sửa lỗi
- **Javis không còn bị kẹt cảnh mất kết nối vì một bản chạy thừa giữ cổng.** Trên Mac, bản launchd quản lý giờ tự tắt bản Javis chạy lạc rồi tiếp quản; bản thừa khác thì thoát ngay, không chạy phần khởi động.
- **Cập nhật trên Mac luôn đổi ca qua launchd**, kể cả khi lệnh kiểm tra của launchd lỗi, nên không còn sinh ra bản chạy ngoài launchd.

## en
### Fixed
- **Javis no longer gets stuck dropping connections because a stray copy holds its port.** On a Mac the copy launchd manages now stops a stray Javis and takes over; any other extra copy exits at once, before its startup runs.
- **Updates on a Mac always restart through launchd**, even when the launchd check fails, so they no longer leave a copy running outside launchd.
