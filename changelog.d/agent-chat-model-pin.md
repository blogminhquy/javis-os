---
bump: minor
title: Each assistant keeps its own chat model
---
## vi
### Thêm mới
- **Mỗi trợ lý nhớ model anh chọn khi chat.** Đổi model ở khung chat với một trợ lý là trợ lý đó ghim luôn model ấy cho chat: mở chat mới hay quay lại chat cũ với trợ lý đều chạy model vừa chọn, không phải chọn lại.
- **Việc nền của trợ lý không đổi theo.** Nhắc hẹn, loop, việc Kanban, lượt trong team, bước quy trình và bot vẫn chạy model trong cài đặt trợ lý. Cửa sổ chat nào anh đã tự chọn model riêng thì giữ nguyên.
- **Quay về model trong cài đặt bằng một chạm.** Trong bảng chọn model có dòng "Theo model trong cài đặt của trợ lý" để gỡ ghim chat của trợ lý.

## en
### Added
- **Each assistant remembers the model you pick in its chat.** Changing the model in a chat with an assistant pins it for chatting with that assistant: new chats and old ones with it run that model, no need to pick again.
- **The assistant's background work stays as it is.** Reminders, loops, Kanban jobs, team turns, workflow steps and bots keep the model in the assistant's settings. A chat window where you picked a model of its own keeps it.
- **Back to the assistant's settings in one tap.** The model list has a "Follow the model set on the assistant" row that clears the assistant's chat pin.
