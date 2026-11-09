---
bump: patch
title: Background work and bot document search no longer freeze the app
---
## vi
### Sửa lỗi
- **Chatbot tra tài liệu không còn làm cả app đứng vài giây.** Bot chỉ duyệt các thư mục có thể chứa tài liệu thay vì liệt kê cả brain, và việc tìm chạy ở luồng phụ.
- **Danh mục kết nối và gói cài thêm không còn bị kiểm tra lại ổ đĩa ở mọi lần gọi.** Kết quả được nhớ 2 giây và làm mới ngay khi cài, gỡ gói hay gỡ kết nối.
- **Trang Cộng sự không còn chờ khoá dữ liệu Cộng hưởng.** Lượt học tự động, nhắc việc và webhook dùng chung một kho đã mở thay vì mở lại mỗi lần, và dựng prompt ở luồng phụ.

## en
### Fixed
- **A bot looking up documents no longer freezes the app for seconds.** It walks only folders that can hold documents instead of listing the whole brain, on a worker thread.
- **The connection catalog and installed packs are no longer re-checked on disk at every call.** The result is trusted for 2 seconds and refreshed at once when a pack or a connection is installed or removed.
- **The Partners page no longer waits on the Resonance data lock.** Auto learning, reminders and webhooks share one opened store instead of opening it again each time, and build their prompts on a worker thread.
