---
bump: patch
title: Three more spots that froze the whole app for one to three seconds now run in the background
---
## vi
### Cải thiện
- **Mở màn mạng nơ-ron không còn làm cả app đứng.** Bộ theo dõi file của đồ thị được dựng trên luồng riêng, nên bộ não nhiều thư mục không còn khiến mọi thao tác khác chờ tới 2 giây mỗi lần mở.
- **Mọi kết nối ra ngoài dùng chung một bộ chứng chỉ bảo mật**, được nạp một lần trên luồng nền lúc khởi động. Trước đây mỗi lần gọi ra ngoài (tin cộng đồng, Telegram, Zalo, model...) đều nạp lại cả bộ, có lần làm app đứng gần 2 giây.
- **Đọc lịch sử Zalo cá nhân chạy nền.** Sau mỗi lượt đọc tin, phần dò lại tin bị sót trong file lịch sử không còn chặn các thao tác khác.

## en
### Improved
- **Opening the neural graph no longer freezes the whole app.** The graph's file watcher is built on its own thread, so a brain with many folders no longer makes everything else wait up to 2 seconds each time the screen opens.
- **Every outgoing connection shares one set of security certificates**, loaded once on a background thread at start-up. Before, each outgoing call (community news, Telegram, Zalo, models...) loaded the whole set again, once freezing the app for almost 2 seconds.
- **Reading the personal Zalo history runs in the background.** After each read, looking for missed messages in the history file no longer blocks anything else.
