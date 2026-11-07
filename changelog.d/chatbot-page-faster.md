---
bump: patch
title: Chatbot page loads faster on a big inbox
---
## vi
### Cải thiện
- **Trang Chatbot mở nhanh hơn hẳn khi hòm thư đã nhiều tin.** Các con số "tin hôm nay" ở Hội thoại và trên thẻ bot trước đây phải đọc lại toàn bộ tin nhắn mỗi 5 giây, nay chỉ đọc đúng khoảng thời gian cần.
- **Tab Thống kê tính nhanh hơn và nhớ kết quả.** Kỳ trước để so sánh được giữ 10 phút, chuyển tab qua lại không phải tính lại từ đầu.
- **Hội thoại tải danh sách cùng lúc với danh sách kênh**, không còn đợi xong cái này mới hỏi cái kia. Lúc trang đang tính, các trang khác của Javis không bị đứng theo.

## en
### Improved
- **The Chatbot page opens much faster on a busy inbox.** The "messages today" counts on Conversations and on each bot card used to read every stored message every 5 seconds; now they read only the time range they need.
- **The Stats tab counts faster and remembers.** The earlier period it compares against is kept for 10 minutes, so switching tabs does not count everything again.
- **Conversations asks for the list and the channels at the same time** instead of one after the other. While the page counts, the rest of Javis no longer freezes.
