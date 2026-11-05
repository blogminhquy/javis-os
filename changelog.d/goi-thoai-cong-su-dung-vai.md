---
bump: patch
title: A voice call with a partner speaks as that partner
---
## vi
### Sửa lỗi
- **Gọi thoại với cộng sự nay đúng là cộng sự đó.** Trước đây bấm gọi trong khung chat của một cộng sự thì giọng nói vẫn là Javis chung, không biết tên, vai hay hướng dẫn của cộng sự, hỏi "em là ai" còn đáp "em là ChatGPT". Nay cuộc gọi mang tên, vai, file hướng dẫn và bộ nhớ của cộng sự.
- **Việc giao trong cuộc gọi do chính cộng sự làm.** Câu cần tra dữ liệu hay hành động chạy bằng prompt và model của cộng sự, kết quả về đúng khung chat của cộng sự.
- **Chat gõ chữ với cộng sự cũng biết mình là ai.** Cộng sự hiểu mình là cộng sự trong Javis của chủ, không tự nhận là ChatGPT hay Claude, chỉ nói tên model khi được hỏi rõ.

## en
### Fixed
- **A voice call with a partner is that partner now.** A call started in a partner's chat used to speak as plain Javis, with no name, role or instructions from the partner, and asked "who are you" it said it was ChatGPT. The call now carries the partner's name, role, instructions file and memory.
- **Work asked for during the call is done by the partner itself.** A request that needs data or an action runs with the partner's prompt and model, and the result lands in the partner's chat.
- **Typed chats with a partner know who they are too.** The partner knows it is a partner inside the owner's Javis, never claims to be ChatGPT or Claude, and names its model only when asked.
