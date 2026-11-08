---
bump: patch
title: Zalo catch-up only works when the history actually changes
---
## vi
### Cải thiện
- **Bù tin Zalo cá nhân không còn chạy theo lịch.** Javis chỉ để ý khi file lịch sử Zalo thật sự có tin mới, rồi chỉ xét đúng những tin đó. Ngày không có tin nào thì gần như không tốn gì (một lần xem kích thước file sau mỗi lượt đọc), không gọi Zalo, không quét các cuộc chat đã im.

## en
### Improved
- **Private Zalo catch-up no longer runs on a schedule.** Javis only reacts when the Zalo history file actually gets new messages, and only looks at those. A day without messages costs almost nothing (one file size check after each read), with no Zalo call and no scan of quiet chats.
