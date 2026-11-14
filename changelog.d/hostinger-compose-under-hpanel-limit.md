---
bump: patch
title: Hostinger compose fits hPanel's editor again
---
## vi
### Sửa lỗi
- **Sửa compose trong hPanel rồi bấm Deploy không còn bị chặn.** Bản 0.557.1 làm file Hostinger dài 33.167 ký tự, quá trần 32.768 của hPanel. File giờ còn khoảng 28.400 ký tự, phần bảo vệ cập nhật vẫn chạy y như cũ.

## en
### Fixed
- **Editing the compose in hPanel and pressing Deploy works again.** Version 0.557.1 made the Hostinger file 33,167 characters, over hPanel's 32,768 limit. It is now about 28,400 characters, and the update guard runs exactly as before.
