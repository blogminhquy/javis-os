---
bump: patch
title: Each chat window and assistant keeps its own model and reasoning level
---
## vi
### Sửa lỗi
- **Mỗi cửa sổ chat giữ model và mức suy nghĩ riêng.** Đổi ở cửa sổ này không còn kéo cửa sổ khác, trang Models hay file của trợ lý đổi theo. Chat riêng với trợ lý chạy theo mức của chính cửa sổ đó, chưa chọn thì theo cài đặt của trợ lý.
- **Chọn model trong khung chat không còn đảo Thứ tự dùng.** Trước đây thẻ vừa chọn tự nhảy lên đầu thành model chính. Giờ thứ tự chỉ đổi ở trang Models, và việc chỉ chuyển xuống thẻ dự phòng bên dưới khi thẻ trên hết lượt.
- **Khi một thẻ hết lượt, thẻ chạy thay dùng đúng mức suy nghĩ đã đặt cho nó** ở trang Models, trong chat, chat trợ lý, team và chatbot.
- **Trợ lý làm việc tự động giữ đúng mức suy nghĩ của mình.** Lượt team trên ChatGPT, Grok Build, Antigravity trước đây bỏ qua mức này; bước workflow chạy model API trước đây tắt hẳn suy nghĩ; chatbot trước đây theo mức của thẻ model thay vì của trợ lý.
- **Tài liệu Messenger:** nói đúng dấu hiệu app Meta chưa có quyền nâng cao (chỉ thấy tin Nhân viên, tên khách là dãy số), kèm mẫu hồ sơ xét duyệt `pages_messaging`.

## en
### Fixed
- **Each chat window keeps its own model and reasoning level.** Changing one no longer moves other windows, the Models page or the assistant's file. A chat with an assistant runs at that window's own level, else the assistant's setting.
- **Picking a model in the composer no longer reorders the usage order.** The picked card used to jump to the top as the main model. The order now changes only on the Models page, and work only moves down to a fallback card when the one above is out of quota.
- **When a card is out of quota, the card standing in runs at the level set for it** on the Models page, in chats, assistant chats, teams and chatbots.
- **Assistants working on their own keep their reasoning level.** Team turns on ChatGPT, Grok Build and Antigravity ignored it, workflow steps on API models ran with reasoning off, and chatbots followed the model card's level instead of the assistant's.
- **Messenger docs:** describe the sign of a Meta app without Advanced Access (only Staff messages, customer names as numbers) and add an App Review template for `pages_messaging`.
