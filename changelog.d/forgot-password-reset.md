---
bump: minor
title: Forgot-password shortcut on the Account page, reset script for Mac
---
## vi
### Thêm mới
- **Trang Tài khoản có dòng "Quên mật khẩu hiện tại?"** ngay dưới nút Đổi mật khẩu. Trên Windows và Mac, bấm vào là Javis mở thư mục cài đặt và chọn sẵn file reset, chỉ cần bấm đúp. Trên VPS, Docker, Hostinger thì hiện các bước đặt lại.
- **Mac có file `reset-auth.command`** làm đúng việc của `reset-auth.bat` trên Windows: xoá mật khẩu cũ để đặt lại từ đầu.

### Sửa lỗi
- **File reset không còn mở lại bộ cài đặt lần đầu** (model, kênh, khoá API giữ nguyên), và trên Mac mật khẩu cũ không còn tự quay lại ở lần khởi động sau.

## en
### Added
- **The Account page has a "Forgot your current password?" line** right under Change password. On Windows and Mac it opens the install folder with the reset file selected, so a double-click is all it takes. On a VPS, Docker or Hostinger it shows the reset steps.
- **Mac gets `reset-auth.command`**, doing what `reset-auth.bat` does on Windows: clear the old password so you can set a new one.

### Fixed
- **The reset file no longer reopens the first-run wizard** (models, channels and API keys stay), and on a Mac the old password no longer comes back at the next start.
