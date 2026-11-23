---
bump: patch
title: Tool search finds apps behind Composio and Claude account connectors
---
## vi
### Sửa lỗi
- **Tìm tool không còn bỏ sót app nằm sau Composio.** Composio chỉ hiện vài tool chung (tìm, chạy, nối tài khoản), còn hàng trăm tool của Gmail, Notion, Slack, GitHub... nằm ẩn phía sau. Trước đây hỏi "gmail" thì Javis trả về Resend, hỏi "gửi tin slack" thì ra Zalo, rồi kết luận là chưa nối app. Giờ Javis đọc danh sách app bạn đã nối trong Composio, nhắc tên app nào thì đưa cổng Composio lên đầu kèm hướng dẫn gọi hai bước, và hỏi theo việc ("đọc email mới nhất") cũng được gợi ý app đã nối.
- **Connector gắn tài khoản Claude được tìm thấy theo việc, không chỉ theo tên.** "Đọc email mới nhất" giờ chỉ tới connector Gmail, "lịch hẹn tuần này" tới Google Calendar, và một connector Composio trên tài khoản Claude khớp khi bạn nhắc Notion, Slack, GitHub...

## en
### Fixed
- **Tool search no longer misses apps behind Composio.** Composio shows only a few shared tools (search, run, connect an account) while hundreds of Gmail, Notion, Slack, GitHub... tools sit hidden behind them. Asking for "gmail" used to return Resend and "send a slack message" returned Zalo, so the model said the app was not connected. Javis now reads the apps you connected in Composio, puts the Composio gateway first with a two-step guide when you name one, and suggests a connected app when you only describe the job ("read my latest email").
- **Claude account connectors are found by the job, not only by name.** "Read my latest email" now points to the Gmail connector, "appointments this week" to Google Calendar, and a Composio connector on the Claude account matches when you mention Notion, Slack, GitHub...
