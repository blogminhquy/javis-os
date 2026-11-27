---
bump: minor
title: Assistants keep their own chat model and get a model that fits when created
---
## vi
### Thêm mới
- **Mỗi trợ lý nhớ model anh chọn khi chat.** Đổi model ở khung chat với một trợ lý là trợ lý đó ghim luôn model ấy cho chat: mở chat mới hay quay lại chat cũ với trợ lý đều chạy model vừa chọn. Việc nền của trợ lý (nhắc hẹn, loop, Kanban, team, quy trình, bot) vẫn chạy model trong cài đặt. Bảng chọn model có dòng "Theo model trong cài đặt của trợ lý" để gỡ ghim.
- **Trợ lý mới tự được chọn model hợp việc.** Trợ lý tạo trong chat, cài từ Store, tạo ở trang Cộng sự hay trong nhóm chat mà để "Mặc định" thì Javis chọn trên thẻ đầu tiên trong Thứ tự dùng: việc nặng như code, dữ liệu, tài chính dùng model mạnh (Opus); marketing, bán hàng, chăm sóc khách dùng model vừa (Sonnet); dịch, ghi chú, nhắc lịch dùng model nhẹ (Haiku). Dòng báo dưới câu trả lời ghi rõ model đã chọn, đổi lại lúc nào cũng được.

## en
### Added
- **Each assistant remembers the model you pick in its chat.** Changing the model in a chat with an assistant pins it for chatting with that assistant: new chats and old ones with it run that model. Its background work (reminders, loops, Kanban, team turns, workflows, bots) keeps the model in its settings. The model list has a "Follow the model set on the assistant" row to clear the pin.
- **A new assistant gets a model that fits its work.** An assistant made in chat, installed from the Store, created on the Partners page or in a team chat and left on "Default" gets one from the first card of your usage order: a strong model (Opus) for code, data and finance, a balanced one (Sonnet) for marketing, sales and customer care, a light one (Haiku) for translation, notes and reminders. The line under the answer names the model, and you can change it any time.
