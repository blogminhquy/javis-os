---
bump: patch
title: Block team plan step when assignment directive is malformed
---
## vi
### Sửa lỗi
- **Việc nhóm không còn tự đóng xanh khi trưởng nhóm ghi lỗi thẻ giao việc.** Nếu kế hoạch làm việc có thẻ giao việc thiếu dấu đóng hoặc lỗi cú pháp, việc sẽ dừng báo lỗi rõ thay vì chốt hoàn thành giả khi chưa ai làm.

## en
### Fixed
- **Team jobs no longer falsely mark as done when an assignment directive is malformed.** When a plan contains a broken or unclosed assignment block, the job stops with a clear error instead of finishing with zero work steps.
