---
bump: minor
title: Javis Gate picks the model and effort, and rings the owner when sent work finishes
---
## vi
### Thêm mới
- **ChatGPT và Claude đổi được model và effort ngay trong câu lệnh gửi qua Javis Gate.** Bảo ChatGPT "bảo Javis làm việc này bằng Opus, effort cao" là xong: model được ghim cho hội thoại đó như khi bạn chọn trên thanh model (chip hiện đúng, đổi lại lúc nào cũng được), còn effort chỉ áp cho đúng tin đó, không đổi cài đặt chung. Công cụ mới `javis_chat_models` cho AI bên ngoài xem Javis có những model nào.
- **Việc ChatGPT giao xong mà nó đã thôi chờ thì chuông Javis báo về điện thoại**, kèm câu trả lời và câu cần nhắn sang ChatGPT ("xem kết quả Javis"). ChatGPT và Claude chưa cho máy ngoài đánh thức một cuộc chat, nên đây là đường ngắn nhất: nhắn một câu, công cụ mới `javis_chat_updates` trả mọi kết quả chưa đọc, kể cả ở một cuộc chat mới bên ChatGPT.

### Cải thiện
- **ChatGPT chờ Javis lâu hơn trong cùng một lượt trả lời** (tới khoảng 10 phút) thay vì bỏ cuộc sau nửa phút, và biết Javis đã làm bao lâu.

## en
### Added
- **ChatGPT and Claude can set the model and effort inside the command they send through Javis Gate.** Tell ChatGPT "have Javis do this on Opus at high effort": the model is pinned on that chat as if you picked it in the model bar (the chip shows it, change it back any time), and the effort counts for that one message only, nothing in your settings changes. A new `javis_chat_models` tool lets the outside AI see which models Javis has.
- **When work ChatGPT sent finishes after it stopped waiting, the Javis bell rings your phone**, with the answer and the sentence to send ChatGPT ("check Javis results"). ChatGPT and Claude do not let outside servers wake a chat yet, so this is the shortest path: one message, and the new `javis_chat_updates` tool hands over every unread result, even in a new ChatGPT chat.

### Improved
- **ChatGPT waits longer for Javis within the same reply** (up to about 10 minutes) instead of giving up after half a minute, and knows how long Javis has been working.
