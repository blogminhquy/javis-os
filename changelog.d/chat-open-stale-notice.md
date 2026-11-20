---
bump: patch
title: Chats no longer show an old copy silently, and one bad message no longer cuts a chat short
---
## vi
### Sửa lỗi
- **Mở lại hội thoại không còn lặng lẽ hiện bản cũ.** Máy chủ trả lời chậm hoặc lỗi thì khung chat báo rõ đang hiện bản lưu trên máy, kèm nút Thử lại, thay vì để tin cũ nằm đó như thể đã mới nhất.
- **Hội thoại tải mãi không mở được nay có lời báo.** Sau vài giây chờ, Javis nói cuộc trò chuyện đang tải lâu và cho bấm Thử lại.
- **Một tin hiển thị lỗi không còn làm mất các tin sau nó.** Tin đó hiện dạng chữ thường, các tin còn lại vẫn đủ, và lỗi được ghi vào trang Sức khoẻ để dễ tìm nguyên nhân.

## en
### Fixed
- **Reopening a chat no longer shows an old copy silently.** When the server is slow or fails, the chat says it is showing the copy kept on this device, with a Retry button, instead of passing the old messages off as current.
- **A chat that never finishes loading now says so.** After a few seconds Javis says the chat is taking long and offers Retry.
- **One message that fails to draw no longer hides the ones after it.** It shows as plain text, the rest of the chat is complete, and the error is logged on the Health page.
