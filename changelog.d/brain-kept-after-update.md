---
bump: patch
title: The dashboard stays on your brain after an update, so teams no longer vanish
---
## vi
### Sửa lỗi
- **Cập nhật xong không còn "mất" nhóm.** Trang mở lại đúng lúc máy chủ đang khởi động thì Javis lặng lẽ chuyển sang Brain Default, nên trang Nhóm hiện nhóm của brain khác và nhóm mới tạo cũng rơi vào đó. Nay Javis luôn mở đúng brain anh chị đã chọn, và tự thử lại tới khi lấy được danh sách brain.
- Dữ liệu nhóm chưa từng bị xoá: nhóm nào "biến mất" trước đây vẫn nằm ở brain còn lại, chọn brain đó ở ô chọn brain là thấy.

## en
### Fixed
- **Updating no longer "loses" teams.** When the page reopened while the server was still starting, Javis silently switched to Brain Default, so the Teams page listed another brain's teams and new teams were created there. Javis now always opens the brain you picked and keeps retrying until the brain list loads.
- No team data was ever deleted: a team that "vanished" before is in the other brain, pick that brain in the brain selector to see it.
