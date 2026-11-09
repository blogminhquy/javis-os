---
bump: minor
title: Connecting GitHub installs git first when the machine has none
---
## vi
### Thêm mới
- **Bấm Kết nối GitHub, Javis kiểm tra máy có git chưa, thiếu thì tự cài rồi mới mở bước đăng nhập.** Windows cài bằng winget hoặc bộ cài chính thức của Git (không cần quyền quản trị), Mac dùng Homebrew hoặc công cụ của Apple, Linux dùng trình quản lý gói khi Javis có quyền.
- **Thẻ GitHub đã kết nối mà máy thiếu git có thêm nút Cài git.** Cài không được thì Javis hiện đúng lệnh để cài tay, nút Thử lại và nút Bỏ qua.

### Sửa lỗi
- **Git vừa cài xong được nhận ngay, không phải khởi động lại Javis.** Trước đây máy chủ chạy từ trước khi có git vẫn báo "chưa cài git".

## en
### Added
- **Connecting GitHub checks for git first and installs it when it is missing, then opens the sign-in step.** Windows uses winget or the official Git installer (no admin rights), Mac uses Homebrew or Apple's tools, Linux uses the package manager when Javis is allowed to.
- **A connected GitHub card on a machine without git gets an Install git button.** If the install fails, Javis shows the exact command to run by hand, Try again and Skip.

### Fixed
- **A git installed while Javis runs is picked up right away, no restart needed.** A server started before git was installed used to keep saying "git is not installed".
