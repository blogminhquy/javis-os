---
bump: patch
title: Guard Tasks poll and Skills panel against missing DOM
---
## vi
### Sửa lỗi
- **Hết lỗi console khi rời trang Việc và trang Kỹ năng.** Bộ tự làm mới của trang Việc không còn chạy tiếp sau khi trang đã đóng, và trang Kỹ năng không còn lỗi khi khung hiển thị chưa có trên màn hình.

## en
### Fixed
- **No more console errors after leaving the Tasks page or when the Skills panel is missing.** The Tasks auto-refresh stops cleanly once its page is closed, and the Skills panel exits early when its container is absent.
