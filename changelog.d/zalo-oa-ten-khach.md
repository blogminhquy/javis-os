---
bump: patch
title: Zalo OA and Messenger chats show the customer's name
---
## vi
### Sửa lỗi
- **Hội thoại Zalo OA trong Hộp thư hiện tên khách, không còn chỉ là mã số.** Trước đây chỉ cần một lần hỏi tên Zalo bị từ chối là Javis nhớ tên rỗng tới khi khởi động lại. Giờ Javis thử lại sau 10 phút, lấy tên từ lịch sử tin nhắn của OA khi Zalo không cho đọc hồ sơ khách, và tự điền tên cho các hội thoại cũ lúc bot khởi động. Tên chủ đã tự đặt thì giữ nguyên.
- **Cuộc chat do Page hoặc OA mở trước (tin trả lời tự động, tin chào, tin từ quảng cáo) hiện tên khách, không còn là dãy số.** Áp dụng cho Messenger và Zalo OA. Các cuộc cũ đang hiện dãy số được tự điền tên khi bot khởi động.

## en
### Fixed
- **Zalo OA chats in the Inbox show the customer's name, not a bare id.** One refused name lookup used to leave the name empty until a restart. Javis now retries after 10 minutes, reads the name from the OA's message history when Zalo refuses the profile, and names older chats when the bot starts. A name the owner set is kept.
- **Chats the Page or the OA opened first (auto replies, greetings, ad messages) show the customer's name, not a long number.** On Messenger and Zalo OA. Older chats shown as a number are named when the bot starts.
