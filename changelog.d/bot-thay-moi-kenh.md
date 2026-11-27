---
bump: patch
title: The bot form lists every connected channel, whatever brain is open
---
## vi
### Sửa lỗi
- **Sửa bot thấy đủ mọi kênh đã nối.** Phần chọn kênh khi tạo hoặc sửa chatbot trước đây chỉ hiện kênh của brain đang mở, nên Fanpage hay bot nối ở brain khác không chọn được. Giờ brain nào cũng thấy mọi kênh; kênh đang có bot khác trực vẫn hiện mờ kèm tên bot và brain. Tick một kênh của brain khác vào bot thì kênh đó chuyển sang brain của bot, để hộp thư của brain đó thấy các cuộc chat bot đang trả lời.

## en
### Fixed
- **The bot form shows every connected channel.** Picking channels when creating or editing a chatbot used to list only the open brain's channels, so a Page or bot connected in another brain could not be picked. Every brain now lists every channel; a channel another bot already answers still shows greyed out with that bot and its brain. Ticking another brain's channel into a bot moves the channel to the bot's brain, so that brain's inbox shows the chats the bot answers.
