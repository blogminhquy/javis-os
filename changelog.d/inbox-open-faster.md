---
bump: patch
title: Opening a chat in the bot inbox responds at once
---
## vi
### Cải thiện
- **Bấm sang một hội thoại là thấy ngay.** Hộp thư Chatbot không còn khựng khi chuyển giữa các cuộc chat dài. Cuộc đã mở trước đó hiện lại tức thì rồi chỉ tải phần tin mới; cuộc mới mở hiện dòng Đang tải ngay lúc bấm.
- Mở một cuộc chat giờ chỉ cần một lần hỏi máy chủ thay vì hai, và danh sách bên trái chỉ vẽ lại đúng những dòng có thay đổi. Trên máy yếu, thời gian từ lúc bấm tới lúc khung chat phản hồi giảm từ khoảng nửa giây xuống dưới 0,05 giây.
- Vẫn chỉ tải 40 tin gần nhất, kéo lên mới tải thêm tin cũ như trước.

## en
### Improved
- **Tapping a chat responds at once.** The Chatbot inbox no longer stalls when you switch between long chats. A chat you opened before shows again instantly and only fetches what is new; a chat opened for the first time shows a loading line the moment you tap.
- Opening a chat now takes one request to the server instead of two, and the list on the left redraws only the rows that changed. On a slow device, the time from a tap to the chat responding drops from about half a second to under 0.05 seconds.
- It still loads only the 40 latest messages, and scrolling up loads older ones as before.
