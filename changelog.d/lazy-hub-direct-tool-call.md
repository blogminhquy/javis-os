---
bump: patch
title: Hidden hub tools answer when called by name
---
## vi
### Sửa lỗi
- **Gọi `javis_team` không còn báo "không tồn tại" khi hub bật chế độ lazy.** Khi có nhiều công cụ, hub giấu bớt sau ô tìm kiếm, nhưng trợ lý quen gọi thẳng tên nên bị báo lỗi. Giờ gọi thẳng tên vẫn chạy đúng công cụ, vẫn qua cùng lớp quyền. Lối tắt huỷ lịch nhắc cũng chạy lại được khi lazy bật.

## en
### Fixed
- **Calling `javis_team` no longer says "does not exist" when the hub runs in lazy mode.** With many tools the hub hides most behind its search tool, but assistants call them by name and got an error. A call by name now reaches the right tool, through the same permission layer. The quick reminder cancel works again in lazy mode too.
