---
bump: patch
title: Javis on Windows no longer drops offline after a dropped connection
---
## vi
### Sửa lỗi
- **Javis trên Windows không còn tự "mất kết nối" phải khởi động lại.** Trước đây một kết nối bị rớt giữa chừng, hay gặp lúc máy vừa thức dậy, làm máy chủ ngừng nhận kết nối mới dù vẫn đang chạy.
- **Bớt khựng khi dùng Grok.** Bước hỏi phiên bản Grok không còn làm cả ứng dụng đứng hình vài giây.
- **Giữ lại 5 file log gần nhất** khi khởi động lại trên Windows, để còn dấu vết khi cần tìm lỗi.

## en
### Fixed
- **Javis on Windows no longer goes offline until restarted.** A connection dropped at the wrong moment, common right after the PC wakes up, used to make the server stop taking new connections while it kept running.
- **Fewer freezes with Grok.** Checking the Grok version no longer stalls the whole app for a few seconds.
- **The last 5 log files are kept** across restarts on Windows, so there is a trail when something goes wrong.
