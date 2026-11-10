---
bump: minor
title: Personal Zalo messages reach Javis the moment they arrive, with no timer
---
## vi
### Cải thiện
- **Zalo cá nhân: có tin là Javis đọc ngay, không còn quét 20 giây một lần.** Trước đây Javis hỏi Zalo đều đặn cả ngày kể cả khi không có tin nào, và tin trong nhóm phải chờ tới 20 giây bot mới thấy. Giờ tin tới lúc nào Javis đọc lúc đó; ngày không có tin thì không đọc lần nào.
- Không có tin thì Javis không chạy nhịp nào cho Zalo. Tiến trình Zalo bị tắt thì Javis dựng lại ngay và đọc bù. Máy chưa lên bản Zalo mới vẫn chạy theo nhịp cũ, không mất tin.

## en
### Improved
- **Personal Zalo: a message is read the moment it arrives, no more scan every 20 seconds.** Javis used to ask Zalo all day even when nothing came in, and a group message waited up to 20 seconds before a bot saw it. A message is now read when it arrives; on a day with no message nothing is read.
- With no message Javis runs no timer for Zalo at all. When the Zalo process stops, Javis restarts it at once and catches up. A machine still on the older Zalo version keeps the timer and loses nothing.
