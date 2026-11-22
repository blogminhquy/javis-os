---
bump: patch
title: Bots never post a model's sign-in error to customers
---
## vi
### Sửa lỗi
- **Bot không còn gửi câu lỗi đăng nhập của model vào nhóm khách.** Khi Claude Code hết phiên, nó in câu "Failed to authenticate: this login reached its time limit..." như một câu trả lời, và bot gửi nguyên câu đó vào nhóm Telegram. Nay mọi câu báo mất đăng nhập (Claude Code, ChatGPT, Grok, Antigravity) đều bị chặn ở mọi kênh: khách không nhận gì, lượt đó tự chạy bằng model khác đã kết nối nếu có, còn chuông thông báo của chủ nói rõ cần vào trang Models đăng nhập lại.
- **Kênh Telegram của chủ báo mất đăng nhập bằng câu dễ hiểu.** Thay cho câu tiếng Anh bảo gõ lệnh trong terminal, chủ đọc "model mất đăng nhập, vào trang Models đăng nhập lại", giống khung chat web.

## en
### Fixed
- **Bots no longer post a model's sign-in error into a customer group.** When Claude Code's sign-in ran out it printed "Failed to authenticate: this login reached its time limit..." as an answer, and a bot sent it to a Telegram group as is. Every lost sign-in sentence (Claude Code, ChatGPT, Grok, Antigravity) is now stopped on every channel: the customer gets nothing, the turn runs on another connected model when there is one, and the owner's bell says to sign in again on the Models page.
- **The owner's Telegram says a lost sign-in in plain words.** Instead of the CLI's advice to run a terminal command, the owner reads that the model lost its sign-in and to sign in again on the Models page, as on the web chat.
