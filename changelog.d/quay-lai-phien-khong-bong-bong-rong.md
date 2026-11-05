---
bump: patch
title: No empty answer bubble when coming back to a chat that is still running
---
## vi
### Sửa lỗi
- **Quay lại khung chat đang chạy không còn bong bóng rỗng.** Javis đang làm mà bạn sang khung chat khác rồi quay lại, trước đây phía trên dòng tiến trình mọc ra một bong bóng trả lời trống. Giờ chỉ còn các bước đã chạy và dòng tiến trình, bong bóng hiện ra khi Javis bắt đầu viết.

## en
### Fixed
- **No empty bubble when coming back to a running chat.** If you left a chat while Javis was working and came back, an empty answer bubble showed above the progress line. Now you see the steps so far and the progress line, and the bubble appears once Javis starts writing.
