---
bump: minor
title: Work in flight carries on by itself after an update or a restart
---
## vi
### Cải thiện
- **Cập nhật xong, việc đang dở tự chạy tiếp.** Việc team bị cắt giữa chừng tự làm tiếp đúng bước đang dở, câu team đang trả lời tự trả lời lại; không còn phải bấm "Làm tiếp" hay "Thử lại".
- **Câu chat đang trả lời dở cũng được trả lời lại** khi trang mở lại sau khi máy chủ khởi động, cho cả chat chính lẫn chat với cộng sự.
- **Việc nền quay lại hàng đợi ngay** thay vì chờ 90 giây, và lần bị cắt không còn bị tính là một lần thử hỏng.
- **Không làm trùng việc ra ngoài.** Bước nào đã kịp gửi tin, đăng bài hay tạo đơn trước khi máy chủ dừng thì Javis dừng lại báo bạn, không tự làm lại. Lượt workflow bị cắt không còn treo "đang chạy" mãi.

## en
### Improved
- **After an update, work in flight carries on by itself.** A team job cut in the middle continues with the step it was on, and a team reply that was being written is written again; no more pressing "Continue" or "Retry".
- **A chat answer cut short is answered again** when the page comes back after the server restarts, in the main chat and in chats with an assistant.
- **Background jobs go back to the queue at once** instead of waiting 90 seconds, and the cut no longer counts as a failed attempt.
- **Nothing outside happens twice.** A step that had already sent a message, posted or created an order before the server stopped makes Javis stop and tell you instead of doing it again. A workflow run cut short no longer says "running" for ever.
