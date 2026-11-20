---
bump: minor
title: Slack bots answer in the right thread, remember old threads and show channel names
---
## vi
### Cải thiện
- **Bot Slack trả lời đúng thread.** Trước đây, đang trả lời câu hỏi ở thread này mà có người nhắn ở thread khác cùng kênh thì câu trả lời có thể rơi nhầm sang thread kia. Giờ mỗi câu trả lời luôn về đúng thread của câu hỏi.
- **Khách nhắn tiếp trong thread cũ vẫn được trả lời sau khi Javis khởi động lại**, không bị coi là người khác nói chuyện với nhau.
- **Hộp thư hiện tên kênh Slack** (ví dụ #sales), và bot báo ngay khi được thêm vào hoặc bị gỡ khỏi một kênh, giống Telegram. Chữ khách gõ như `a < b`, `@Kim`, đường link giờ tới Javis đúng như khách gõ.
- **Slack đang giới hạn tần suất thì bot chờ rồi gửi lại**, không mất nửa câu trả lời. App tạo theo hướng dẫn cũ vẫn chạy; muốn có tên kênh thì dán lại manifest mới và cài lại app (docs/29-slack-whatsapp.md).

## en
### Improved
- **Slack bots answer in the right thread.** Before, if someone wrote in another thread of the same channel while the bot was answering, the answer could land in that other thread. Every answer now goes back to the thread of its question.
- **Customers continuing an old thread are still answered after Javis restarts**, instead of being treated as people talking to each other.
- **The inbox shows Slack channel names** (for example #sales), and the bot reports being added to or removed from a channel, like Telegram. Text such as `a < b`, `@Kim` and links now reaches Javis exactly as typed.
- **When Slack rate limits, the bot waits and sends again** instead of losing the rest of the answer. Apps made from the older guide keep working; for channel names, paste the new manifest and reinstall the app (docs/en/29-slack-whatsapp.md).
