---
bump: patch
title: Antigravity no longer loses the question when the context is long
---
## vi
### Sửa lỗi
- **Antigravity không còn mất câu hỏi khi ngữ cảnh quá dài.** Cộng sự có bộ nhớ lớn (vài chục KB) chạy bằng Antigravity từng trả lời "yêu cầu bị cắt mất, gửi lại giúp em" dù câu hỏi rất ngắn, vì `agy` cắt phần cuối tin nhắn đầu, đúng chỗ câu hỏi nằm. Nay tin nhắn dài thì câu hỏi mới nhất được chép thêm lên đầu, nên cắt kiểu gì model vẫn thấy và trả lời luôn.

## en
### Fixed
- **Antigravity no longer loses the question when the context is long.** An assistant with a large memory (tens of KB) on Antigravity used to reply "your request was cut off, please resend it" to a short question, because `agy` cuts the end of the first message, exactly where the question sits. A long first message now also carries the latest question at the top, so the model sees it and answers whatever gets cut.
