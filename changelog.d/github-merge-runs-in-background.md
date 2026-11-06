---
bump: patch
title: Merge keeps running after the GitHub panel is closed
---
## vi
### Sửa lỗi
- **Bấm Merge rồi đóng bảng, PR vẫn được merge.** Trước đây đóng bảng chi tiết GitHub (hay đóng tab) ngay sau khi bấm Merge là lệnh merge bị huỷ giữa chừng. Giờ Javis merge tiếp ở nền và báo kết quả vào khung chat.
- Mở lại bảng khi đang merge sẽ thấy "Đang merge...", không hiện nút Merge lần nữa nên không merge trùng.

## en
### Fixed
- **Press Merge, close the panel, and the PR still merges.** Closing the GitHub detail panel (or the tab) right after pressing Merge used to cancel the merge halfway. Javis now finishes it in the background and posts the result in the chat.
- Reopening the panel during a merge shows "Merging..." instead of the Merge button, so it never merges twice.
