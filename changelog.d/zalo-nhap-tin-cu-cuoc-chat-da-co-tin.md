---
bump: patch
title: Importing old Zalo messages now fills chats that already have messages
---
## vi
### Sửa lỗi
- **Nút "Nhập tin cũ" của Zalo nhập được thật.** Trước đây cuộc chat nào đã có dù chỉ một tin trong Hộp thư đều bị bỏ qua, nên tài khoản đã bật Ghi hội thoại bấm nhập gần như không được gì. Giờ cuộc chat đã có tin nhận thêm các tin cũ hơn tin đầu tiên của nó, xếp lên trên đúng thứ tự thời gian.
- Tin cũ vừa nhập không nhảy xuống cuối khung chat đang mở, không làm bot hiểu nhầm là tin mới, và nhóm vẫn chỉ giữ các tin gần nhất như cũ.

## en
### Fixed
- **Zalo's "Import old messages" button actually imports.** Any chat with even one message in the Inbox used to be skipped, so on an account already recording conversations the import added almost nothing. A chat that has messages now gets the ones older than its first message, placed above it in time order.
- Imported old messages do not land at the bottom of an open chat, the bot does not take them for new messages, and groups still keep only their latest messages.
