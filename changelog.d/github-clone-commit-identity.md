---
bump: patch
title: Conflict fixes work on servers that have no git identity
---
## vi
### Sửa lỗi
- **Vòng sửa xung đột chạy được trên máy chưa khai tên và email cho git.** Trên máy chủ mới hoặc trong Docker, lệnh gộp nhánh của AI dừng ngay với lỗi `empty ident name`. Giờ mỗi repo gắn vào chat có sẵn danh tính, là tài khoản GitHub anh đã kết nối.
- **Commit do AI tự tạo trong repo đó giờ đứng tên giống commit của Javis.** Nếu anh đã tự khai tên và email riêng cho repo thì Javis giữ nguyên.

## en
### Fixed
- **The conflict fix round works on a machine where git has no name and email.** On a fresh server or in Docker, the AI's merge command stopped at once with `empty ident name`. Each repo attached to a chat now has an identity of its own, the GitHub account you connected.
- **Commits the AI makes itself in that repo now carry the same author as Javis's commits.** A name and email you set for the repo yourself are kept.
