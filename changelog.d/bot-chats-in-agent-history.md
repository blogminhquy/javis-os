---
bump: patch
title: Bot chats show in their partner's history whatever spelling the bot's brain has
---
## vi
### Sửa lỗi
- **Hội thoại của bot Telegram (và mọi kênh bot khác) hiện lại trong lịch sử của cộng sự nối với bot.** Bot nào được lưu brain theo một cách viết khác của cùng brain đó (đường dẫn đầy đủ từ bản cũ, có dấu `/` ở cuối, hay thư mục brain đã dời chỗ) vẫn trả lời bình thường, nhưng cuộc chat của nó không bao giờ lên cột Lịch sử của cộng sự. Giờ Javis so theo brain mà hội thoại thực sự được lưu, và tên cộng sự có dấu tiếng Việt cũng khớp dù file tạo trên macOS.

## en
### Fixed
- **Telegram bot chats (and every other bot channel) show again in the history of the partner the bot uses.** A bot whose record held another spelling of the same brain (a full path from an older version, a trailing slash, or a brain folder that moved) answered as usual, but its chats never reached the partner's History column. Javis now matches the brain the chats are actually stored in, and a partner name with Vietnamese accents matches even when its file was made on macOS.
