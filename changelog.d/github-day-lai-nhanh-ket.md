---
bump: patch
title: Push again works on a GitHub job stuck on a taken branch name
---
## vi
### Sửa lỗi
- **Nút "Đẩy lại" và dấu chấm than ở thẻ GitHub không còn kẹt mãi.** Việc đã lỡ lưu một tên nhánh bị trùng trên GitHub (từ trước bản sửa trước) vẫn cứ đẩy vào đúng tên đó, nên lần thử lại nào cũng báo "có commit mà máy này không có". Giờ khi chưa đẩy lên được lần nào, Javis chọn lại tên nhánh còn trống (hoặc theo nhánh đang mở ở máy), đẩy lên và mở PR, dấu chấm than tự tắt.

## en
### Fixed
- **"Push again" and the warning mark on the GitHub card no longer stay stuck.** A job that had stored a branch name already taken on GitHub (from before the previous fix) kept pushing to that same name, so every retry said "has commits this machine lacks". Now, while nothing has been pushed yet, Javis picks a free branch name again (or follows the branch checked out on this machine), pushes, opens the PR, and the warning clears.
