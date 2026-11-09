---
bump: minor
title: Zalo bot shows typing in groups once it decides to reply
---
## vi
### Thêm mới
- **Bot Zalo cá nhân hiện "đang soạn tin..." trong nhóm.** Chỉ bật sau khi bot đã quyết định trả lời (được gọi tên, hoặc bộ phán xử chọn lên tiếng) và giữ tới lúc gửi xong, nên nhóm không còn im 20-30 giây rồi mới thấy bot nói. Tin bot đọc rồi im thì không hiện gì.
- **Nút bật/tắt trên trang Chatbot** cho từng bot, mặc định bật.

### Sửa lỗi
- **"Đang soạn tin" ở chat riêng không còn tắt cả tiếng.** Trước đây chỉ một cuộc chat bị Zalo từ chối, hoặc MCP khởi động lại, là dấu này tắt ở mọi cuộc chat của nick suốt một giờ. Giờ chỉ tắt cho đúng lượt đó, và dấu được giữ tới khi tin đã gửi đi.

## en
### Added
- **Personal Zalo bots show "typing..." in groups.** It starts only after the bot has decided to answer (it was called, or the judge chose to speak up) and lasts until the reply is sent, so a group no longer sits in silence for 20-30 seconds. A message the bot leaves alone shows nothing.
- **An on/off switch on the Chatbot page** for each bot, on by default.

### Fixed
- **Private-chat "typing..." no longer goes quiet for an hour.** One chat that Zalo refused, or an MCP restart, used to switch it off in every chat of the account for an hour. Now only that turn loses it, and it lasts until the message has gone out.
