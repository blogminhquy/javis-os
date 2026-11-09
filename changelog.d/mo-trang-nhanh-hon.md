---
bump: minor
title: Faster first page load and Partners page
---
## vi
### Cải thiện
- **Mở app nhanh hơn rõ rệt.** Khoảng 110 file giao diện lúc khởi động giờ đi chung một gói. Trên đường mạng có độ trễ 150ms, danh sách Cộng sự hiện sau khoảng 2 giây thay vì gần 5 giây.
- **Khởi động lại hay cập nhật xong không còn bị khựng ở lần mở đầu.** Bản nén gọn được lưu lại trên đĩa nên máy chủ không phải làm lại từ đầu, chỉ file nào vừa đổi mới phải nén lại.
- **Trang Cộng sự không còn đứng chờ cả loạt.** Các lệnh đọc danh sách, trạng thái Cộng hưởng và việc nền giờ chạy ở luồng phụ, không chặn các lệnh khác.

## en
### Improved
- **The app opens noticeably faster.** The ~110 interface files loaded at startup now travel as one bundle. With 150 ms of network delay the Partners list shows after about 2 seconds instead of nearly 5.
- **No stall on the first page after a restart or an update.** Minified files are kept on disk, so the server does not redo them from scratch; only files that just changed are minified again.
- **The Partners page no longer waits in a queue.** The reads for the list, the Resonance status and background work now run off the main loop and stop holding up other requests.
