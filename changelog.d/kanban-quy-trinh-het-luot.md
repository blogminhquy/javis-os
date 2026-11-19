---
bump: patch
title: Workflow jobs on the board wait for the plan to reset instead of giving up
---
## vi
### Sửa lỗi
- **Việc chạy quy trình trên trang Nhiệm vụ biết đợi gói mở lại.** Trước đây bước nào vấp gói thuê bao hết lượt là việc thử lại ngay, đốt hết 3 lần thử trong vài giây rồi kẹt. Giờ việc tự hẹn chạy lại đúng giờ gói mở và không tính vào số lần thử.

## en
### Fixed
- **Workflow jobs on the Tasks page wait for the plan to reset.** A step that hit an exhausted subscription used to retry at once, spend all three attempts in seconds and get stuck. The job now waits until the plan resets, and the wait does not count as an attempt.
