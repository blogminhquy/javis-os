---
bump: patch
title: Javis draft follows the owner's order instead of hedging
---
## vi
### Sửa lỗi
- **Nút soạn trả lời khách làm đúng lệnh của chủ.** Gõ "lịch đã xác nhận 20h ngày 21 và 22" rồi bấm soạn, câu trả lời báo đúng lịch đó cho khách, không còn viết "em chưa có lịch xác nhận" chỉ vì tài liệu chưa có hay trước đó bot từng nói "đang kiểm tra". Lệnh của chủ giờ được coi là thông tin đã xác nhận, đứng trên tài liệu và lịch sử cuộc chat. Bấm Viết lại cũng theo lệnh đó.

### Cải thiện
- **"A.I. soạn" đổi tên thành "Javis soạn"** ở nút trong ô nhập, chế độ trên đầu cuộc chat và dòng trên bản nháp.

## en
### Fixed
- **The reply draft button follows the owner's order.** Type "schedule confirmed 8pm on the 21st and 22nd" and press draft: the reply gives the customer that schedule instead of "I have no confirmed schedule yet" just because no document had it or the bot earlier said it was checking. The owner's order now counts as confirmed information, above the documents and the chat history. Rewrite follows it too.

### Improved
- **"AI draft" is now "Javis draft"** on the composer button, the mode above the chat and the line over the draft.
