---
bump: patch
title: Customer chatbots stay silent when the Claude plan hits its monthly spend limit
---
## vi
### Sửa lỗi
- **Bot không còn gửi câu "You've hit your monthly spend limit" cho khách.** Khi gói Claude hết cả hạn mức chi thêm theo tháng, Claude Code in ra một câu mới mà Javis chưa nhận ra, nên bot Zalo dán nguyên câu tiếng Anh đó vào tin trả lời khách. Nay câu này được coi là lượt hỏng như mọi câu báo hết lượt khác: khách không nhận gì, chủ được báo ở chuông thông báo. Khung chat, việc Kanban và workflow cũng nhận ra nó là hết lượt gói, kèm giờ mở lại.
- **Câu báo hết lượt có dấu nháy cong (You’ve) cũng được nhận ra** như dấu nháy thường.

## en
### Fixed
- **Bots no longer send "You've hit your monthly spend limit" to customers.** Once the Claude plan's monthly extra-usage cap was spent too, Claude Code printed a new notice Javis did not recognise, so a Zalo bot pasted that English line into its reply to a customer. It now counts as a failed turn like every other plan-limit notice: the customer receives nothing and the owner is told in the notification bell. Chat, Kanban jobs and workflows also read it as the plan running out, with the reset time.
- **Plan-limit notices with a curly apostrophe (You’ve) are recognised** like the straight one.
