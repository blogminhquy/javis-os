---
bump: patch
title: Folder red dot waits until a running chat has finished
---
## vi
### Sửa lỗi
- **Chấm đỏ ở thư mục hội thoại chỉ hiện khi chat đã xong mà chưa đọc.** Chat còn đang chạy hiện vòng xoay chứ không làm sáng chấm đỏ ở thư mục, ở dòng "Chưa xếp nhóm", ở chính dòng chat và ở menu bên trái. Chat đang mở trên màn hình cũng không bị tính. Lượt chạy xong mà chưa được xem thì chấm đỏ mới hiện.

## en
### Fixed
- **The chat folder's red dot shows only for a chat that has finished and is unread.** A chat still working shows its spinner and no longer lights the folder, the "Ungrouped" row, its own row or the side menu. The chat open on screen is not counted either. The dot appears once a run ends and you have not looked at it.
