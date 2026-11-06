---
bump: minor
title: Dictation shows the words in the chat box and the main brain rewrites them before they are sent
---
## vi
### Cải thiện
- **Ghi âm thành chữ lại hiện chữ ngay trong ô chat** khi đang nói trên máy tính, như bản cũ, không còn bong bóng mờ phía trên. Điện thoại vẫn hiện chữ khi ghi xong.
- **Nói xong là câu được viết lại cho đúng ngữ cảnh.** Bấm dừng, Enter hay Gửi thì chính mô hình chính (gói thuê bao hay API key) đọc vài tin nhắn gần nhất rồi viết lại cả câu, sửa mọi chỗ máy nghe nhầm, không chỉ vài từ như "Travis OS" thành "Javis OS". Gửi ngay thì câu đã viết lại mới là câu được gửi.
- Lỗi mạng hay mô hình chậm quá 25 giây thì giữ câu nghe được, không mất chữ. Tai Groq hay OpenAI giờ luôn giữ tên Javis trong từ mồi dù có nhiều kết nối.

## en
### Improved
- **Dictation shows the words right in the chat box** again while you speak on a computer, like before, with no faded bubble above. Phones still show the text when the recording ends.
- **What you said is rewritten in context before it is used.** On stop, Enter or Send, your main model (subscription or API key) reads the last few messages and rewrites the whole sentence, fixing every mishearing, not just a few words like "Travis OS" into "Javis OS". Sending right away sends the rewritten sentence.
- A network error or a model slower than 25 seconds keeps the words as heard, nothing is lost. The Groq or OpenAI ear now always keeps the Javis name in its hint, even with many connections.
