---
bump: minor
title: Keep Telegram replies and background notifications in their topics
---
## vi
### Thêm mới
- Telegram giữ câu trả lời, ảnh và tệp trong topic đang nhắn. Mỗi topic có phiên trò chuyện riêng.
- Nhắc hẹn và công việc mới giữ topic đã giao việc. Dùng `/topic <group>` trong topic để chọn nơi nhận thông báo mặc định của từng nhóm; `/topic off <group>` để bỏ gán.
### Sửa lỗi
- Topic bị đóng hoặc không gửi được sẽ không làm nội dung rơi sang General. Kiểm tra quyền gửi theo nhóm chứa topic.

## en
### Added
- Telegram keeps replies, images and files in the originating topic, with separate conversation sessions per topic.
- New reminders and jobs retain their originating topic. Use `/topic <group>` inside a topic to set group notification defaults, or `/topic off <group>` to clear them.
### Fixed
- Closed or unavailable topics no longer cause content to fall back to General. Recipient authorization checks the parent chat.
