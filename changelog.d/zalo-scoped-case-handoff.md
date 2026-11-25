---
bump: minor
title: Scoped Zalo pricing and confirmed case handoff
---
## vi
### Thêm mới
- Bot Zalo cá nhân có thể xin giá và bàn giao hồ sơ đã chốt tới người phụ trách được chủ cấu hình, kèm ảnh khách chọn từ cùng cuộc chat và xác nhận lại cho khách sau khi gửi thành công.
### Sửa lỗi
- Trích dẫn tin nhắn Zalo giữ đúng đích trả lời, kể cả khi nội dung có đường dẫn. Các lần gọi lại luồng bàn giao không gửi trùng những phần đã có biên nhận.
## en
### Added
- Personal Zalo bots can request pricing and hand confirmed cases to an owner-configured staff contact, including selected customer images from the same chat and a customer acknowledgement after delivery.
### Fixed
- Zalo quotes preserve their reply target for messages containing links. Retrying a handoff does not resend stages with recorded receipts.
