---
bump: minor
title: Bots remember 30 messages of a private chat, and keep them across a restart
---
## vi
### Sửa lỗi
- **Bot không còn quên khách sau mỗi lần cập nhật.** Trước đây lịch sử chat riêng của bot chỉ nằm trong bộ nhớ tạm, nên Javis khởi động lại là bot gặp khách cũ như người lạ. Giờ bot đọc lại cuộc chat từ Hộp thư, gồm cả câu bạn tự trả lời tay.

### Cải thiện
- **Bot xem lại 30 tin gần nhất của chat riêng thay vì 20.** Áp cho mọi kênh bot (Zalo Bot, Zalo cá nhân, Telegram, Messenger...). Cuộc chat có tin rất dài thì bot bớt từ tin cũ nhất. Nhóm vẫn xem 30 tin trước tin đang hỏi như cũ.

## en
### Fixed
- **Bots no longer forget a customer after every update.** A bot kept the history of a private chat in temporary memory only, so a restart of Javis made it meet a returning customer as a stranger. It now reads the chat back from the inbox, including what you answered by hand.

### Improved
- **Bots look back over the last 30 messages of a private chat instead of 20.** On every bot channel (Zalo Bot, personal Zalo, Telegram, Messenger...). In a chat with very long messages the bot drops the oldest ones. Groups still see the 30 messages before the one being asked.
