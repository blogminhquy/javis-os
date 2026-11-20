---
bump: patch
title: Installs without write access send a bug report instead of editing Javis's code
---
## vi
### Sửa lỗi
- **Nhờ Javis tự sửa mã nguồn Javis không còn đỏ lỗi "không có quyền ghi vào blogminhquy/javis-os" ở máy người dùng.** Trước đây mọi máy đều tải repo gốc về, sửa cả lượt rồi mới hỏng ở bước đẩy. Giờ máy không có quyền ghi thì Javis không tải, không sửa, mà viết sẵn một báo lỗi kèm hướng sửa và đưa link mở trang tạo Issue cho nhà phát triển. Bạn đọc lại, bấm Submit là gửi, không cần token hay quyền gì thêm.

## en
### Fixed
- **Asking Javis to fix Javis's own code no longer ends in "cannot write to blogminhquy/javis-os" on a user's install.** Every install used to clone the official repo, edit it for a whole turn and only fail at the push. Now an install without write access clones and edits nothing: Javis writes the bug report and suggested fix and hands you a link to a prefilled issue for the developer. Read it, press Submit, no token or extra access needed.
