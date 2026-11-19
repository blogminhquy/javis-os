---
bump: minor
title: Javis draft follows the owner's order and the bot learns from replies the owner confirmed
---
## vi
### Thêm mới
- **Bot học từ câu bạn xác nhận.** Trên bản nháp ở Hộp thư có ô tick "Bot học câu này", bật sẵn. Gửi một câu có lệnh của bạn, hoặc câu bạn đã tự sửa, thì câu đó được ghi vào tài liệu của Agent (file `tri-thuc-chatbot/<tên-agent>.md`). Lần sau khách khác hỏi chuyện tương tự, bot trả lời theo đúng câu bạn đã xác nhận. Chuyện riêng của một khách thì bỏ tick.

### Sửa lỗi
- **Nút soạn trả lời khách làm đúng lệnh của chủ.** Gõ "lịch đã xác nhận 20h ngày 21 và 22" rồi bấm soạn, câu trả lời báo đúng lịch đó, không còn viết "em chưa có lịch xác nhận" chỉ vì tài liệu chưa có hay trước đó bot từng nói "đang kiểm tra". Lệnh của chủ là lời mới nhất, đứng trên tài liệu và lịch sử cuộc chat, không kèm danh sách câu cấm nào. Bấm Viết lại cũng theo lệnh đó.

### Cải thiện
- **"A.I. soạn" đổi tên thành "Javis soạn"** ở nút trong ô nhập, chế độ trên đầu cuộc chat và các dòng của bản nháp.

## en
### Added
- **The bot learns from replies you confirm.** The draft box in the Inbox has a "Bot learns this" tick, on by default. Sending a reply that carries your order, or one you rewrote, saves it to the Agent's documents (file `tri-thuc-chatbot/<agent>.md`). Next time another customer asks the same thing, the bot answers the way you confirmed. Untick it for something about one customer only.

### Fixed
- **The reply draft button follows the owner's order.** Type "schedule confirmed 8pm on the 21st and 22nd" and press draft: the reply gives that schedule instead of "I have no confirmed schedule yet" just because no document had it or the bot earlier said it was checking. The owner's order is the newest word, above the documents and the chat history, with no list of banned phrases. Rewrite follows it too.

### Improved
- **"AI draft" is now "Javis draft"** on the composer button, the mode above the chat and the lines of the draft.
