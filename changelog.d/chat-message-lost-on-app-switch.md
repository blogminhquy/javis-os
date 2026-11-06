---
bump: patch
title: Messages sent right before switching apps on a phone are no longer lost
---
## vi
### Sửa lỗi
- **Gõ xong bấm Enter rồi vuốt sang app khác trên điện thoại, câu hỏi không còn biến mất.** Trước đây điện thoại có lúc để kết nối chết ngầm, câu hỏi không tới máy chủ nên quay lại thì cả đoạn mất sạch, Lịch sử cũng không có. Nay máy chủ xác nhận từng câu đã nhận, câu nào chưa được xác nhận thì Javis tự gửi lại khi nối lại, và không bao giờ chạy trùng hai lần.

## en
### Fixed
- **A message sent right before swiping to another app on a phone no longer vanishes.** The phone sometimes let the connection die silently, so the message never reached the server and the whole exchange was gone on return, History included. The server now confirms every message it receives, Javis resends any unconfirmed one after reconnecting, and a resend never runs twice.
