---
bump: patch
title: New Claude Code chats read the prompt cache again at token-saving levels
---
## vi
### Sửa lỗi
- **Mở phiên chat mới với Claude Code không còn ghi lại toàn bộ cache khi bật tiết kiệm token.** Trước đây một dòng giờ đổi theo từng phút, cùng phần ký ức chọn theo câu hỏi, nằm trong phần prompt được cache, nên mỗi phiên mới phải ghi lại khoảng 25 nghìn token. Nay phần đó đi kèm tin nhắn đầu của phiên, còn prompt giữ nguyên giữa các phiên.

## en
### Fixed
- **A new Claude Code chat no longer rewrites the whole prompt cache at token-saving levels.** A clock that changed every minute, and the memories picked for each question, sat inside the cached part of the prompt, so every new chat rewrote about 25 thousand tokens. They now travel with the first message of the chat, and the prompt stays the same between chats.
