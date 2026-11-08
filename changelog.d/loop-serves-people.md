---
bump: patch
title: Chat turns, Kanban jobs and heavy page reads no longer hold up other clicks
---
## vi
### Cải thiện
- **Lúc Javis đang trả lời hay đang chạy việc Kanban, các cú bấm khác không còn phải xếp hàng chờ.** Việc đọc ghi lịch sử hội thoại trong mỗi lượt chat (kể cả đọc lại cả cuộc dài để gửi cho model) và mọi lần ghi của việc Kanban giờ chạy ở luồng phụ, không chiếm luồng phục vụ giao diện nữa.
- **Các trang đọc nhiều (Tệp tin, bộ nhớ, sao lưu, tự học, nhắc hẹn, vòng lặp, nhóm hội thoại, tài sản trong chat...) không còn làm cả máy chủ khựng khi brain lớn.** Số chỗ làm việc nặng trên luồng chính giảm từ 347 xuống 218, Kanban về 0.
- Một test mới chặn không cho con số đó tăng trở lại.

## en
### Improved
- **While Javis answers or runs a Kanban job, other clicks no longer wait in line.** Reading and writing the chat history during each turn (including reading back a long chat to send to the model) and every write of a Kanban job now run on worker threads, off the loop that serves the interface.
- **Read-heavy pages (Files, memory, backup, self-learning, reminders, loops, chat groups, chat assets...) no longer stall the whole server on a large brain.** Blocking calls on the main loop went from 347 down to 218, Kanban to 0.
- A new test stops that number from growing again.
