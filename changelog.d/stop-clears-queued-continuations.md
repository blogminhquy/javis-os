---
bump: patch
title: Prevent stopped turns from launching queued follow-up work
---
## vi
### Sửa lỗi
- **Bấm Dừng nay hủy sạch mọi lượt nối tiếp đang chờ.** Khi người dùng dừng một lượt đang chạy, các tin nhắn gõ chen, lịch chạy lại do hạn mức và lời dặn làm tiếp sau khi xong việc nền đều được xóa để không tự bật lượt mới ngoài ý muốn.

## en
### Fixed
- **Stopping a turn now clears all queued continuations.** When a user stops an active turn, queued mid-turn messages, scheduled quota resumes, and pending background follow-up instructions are discarded instead of starting an unwanted follow-up turn.
