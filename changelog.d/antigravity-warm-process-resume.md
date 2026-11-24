---
bump: minor
title: Antigravity keeps its process warm and resumes the conversation
---
## vi
### Cải thiện
- **Antigravity trả lời nhanh như Claude và ChatGPT từ lượt thứ hai.** Mỗi cuộc chat giữ một tiến trình Antigravity chạy sẵn và nối tiếp đúng mạch hội thoại, nên lượt sau không phải khởi động lại, không phải đọc lại toàn bộ luật và lịch sử: chữ đầu về sau khoảng 2 đến 3 giây thay vì 10 giây trở lên.
- **Antigravity nhớ trọn cuộc chat dài,** kể cả file đã đọc và lệnh đã chạy ở các lượt trước, thay vì chỉ thấy 45.000 ký tự lịch sử gần nhất.
- Trên Windows, câu hỏi dài không còn phải đi vòng qua file ngữ cảnh. Nếu Antigravity làm mất mạch, Javis tự gửi lại đủ ngữ cảnh ngay trong lượt đó; đặt `JAVIS_AGY_RESUME=0` để quay về cách cũ.

## en
### Improved
- **Antigravity answers as fast as Claude and ChatGPT from the second turn on.** Each chat keeps an Antigravity process running and resumes its own conversation, so later turns neither restart it nor reread all the rules and history: the first word arrives after about 2 to 3 seconds instead of 10 or more.
- **Antigravity remembers the whole of a long chat,** files it read and commands it ran included, instead of only the last 45,000 characters of history.
- On Windows a long question no longer detours through a context file. If Antigravity loses the thread, Javis sends the full context again within the same turn; set `JAVIS_AGY_RESUME=0` to go back to the old way.
