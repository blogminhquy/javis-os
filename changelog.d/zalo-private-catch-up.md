---
bump: patch
title: Missing private Zalo messages are caught up from the history
---
## vi
### Sửa lỗi
- **Tin Zalo cá nhân không còn bị hụt trong Hộp thư.** Có lúc một cuộc chat riêng dừng ở một tin, trong khi điện thoại vẫn nhắn tiếp cả hai chiều. Cứ khoảng 1,5 phút Javis tự so Hộp thư với kho lịch sử Zalo, thiếu tin nào thì bù tin đó, kể cả tin anh chị tự gõ trên điện thoại. Tin bù hiện chưa đọc, không giao cho bot trả lời muộn, không trùng với câu bot đã gửi, và không đè dòng tin cuối của cuộc chat.

## en
### Fixed
- **Private Zalo chats no longer have holes in the inbox.** A private chat could stop at one message while the phone kept going both ways. About every 1.5 minutes Javis now compares the inbox with the Zalo history and writes what is missing, including messages typed on the phone. Recovered messages show as unread, are not handed to the bot for a late reply, do not duplicate what the bot already sent, and never replace the chat's last message.
