---
bump: patch
title: The graph screen and MCP tool lists no longer freeze the app every few minutes
---
## vi
### Cải thiện
- **Mở lại màn mạng nơ-ron, mở thêm tab hay điện thoại vừa kết nối lại không còn làm cả app khựng.** Cả app dùng chung một bộ theo dõi file cho mỗi thư mục, dựng một lần rồi giữ thêm 15 phút sau khi đóng màn đồ thị. Trước đây mỗi lần mở là dựng lại từ đầu, có lần làm mọi thao tác khác chờ gần 3 giây.
- **Danh sách công cụ của các kết nối MCP được nhớ 10 phút** thay vì hỏi lại mọi máy chủ mỗi phút, nên app bớt hẳn những lần khựng một hai giây khi đang chat. Nút Kiểm tra và vòng kiểm tra sức khoẻ vẫn hỏi thẳng máy chủ, và kết nối nào báo đổi công cụ thì được hỏi lại ngay.

## en
### Improved
- **Reopening the neural graph, opening another tab or a phone reconnecting no longer freezes the whole app.** The app shares one file watcher per folder, built once and kept for 15 minutes after the graph screen closes. Before, each opening built it again, once making everything else wait almost 3 seconds.
- **The tool list of each MCP connection is remembered for 10 minutes** instead of asking every server again each minute, so far fewer one or two second freezes while chatting. The Test button and the health check still ask the server directly, and a connection that announces new tools is asked again at once.
