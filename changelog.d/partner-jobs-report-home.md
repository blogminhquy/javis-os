---
bump: patch
title: Scheduled jobs made in a partner chat report back to it and run as that assistant
---
## vi
### Sửa lỗi
- **Việc hẹn giờ tạo trong chat Cộng sự báo về đúng chat đó.** Trước đây nhắc hẹn và việc định kỳ giao từ chat với một trợ lý không biết mình đến từ đâu, nên cả kết quả lẫn lỗi đều rơi về Javis Core. Giờ Javis tự gắn khung chat đang hỏi.
- **Tới giờ, việc chạy bằng đúng vai trợ lý đã nhận nó.** Việc đăng bài hẹn từ chat với trợ lý Đăng bài giờ dùng vai trò, quy trình, bộ nhớ và luật chủ dặn của trợ lý đó, không chạy như Javis chung nữa. Trang Nhiệm vụ cũng xếp việc đó dưới tên trợ lý.
- **Sự cố báo về nơi đã giao việc.** Việc nền hỏng thì Javis Core vẫn xét và thử lại như cũ, nhưng tin "Sự cố cần bạn" giờ hiện ở khung chat đã giao việc. Việc không gắn khung chat nào thì vẫn về Javis Core.
- Việc đã tạo trước bản này vẫn chạy như cũ. Muốn có cách mới thì nhờ trợ lý tạo lại việc đó.

## en
### Fixed
- **Scheduled jobs made in a partner chat report back to that chat.** A reminder or recurring job set up in a chat with an assistant did not know where it came from, so its results and its errors all landed in Javis Core. Javis now attaches the chat that asked.
- **At its time, the job runs as the assistant that took it.** An auto-post job set up with a Posting assistant now uses that assistant's role, procedure, memory and owner rules instead of running as plain Javis. The Tasks page files it under that assistant too.
- **Incidents report where the job was given.** When a background job breaks, Javis Core still triages and retries it as before, but the "Incident needs you" message now shows in the chat that gave the job. A job tied to no chat still reports to Javis Core.
- Jobs made before this version keep running as before. Ask the assistant to create the job again to get the new behavior.
