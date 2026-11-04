---
bump: minor
title: Version numbers are assigned after merge, parallel PRs stop colliding
---
## vi
### Cải thiện
- **Số phiên bản giờ do máy tự đánh sau khi merge.** Mỗi bản sửa chỉ ghi nhật ký vào một file riêng, nên làm nhiều bản sửa cùng lúc không còn giành số của nhau và không phải đánh số lại.
- Mỗi lần merge vẫn ra một số phiên bản mới như cũ, kèm nhật ký tiếng Việt và tiếng Anh, rồi bản cập nhật được phát hành ngay sau đó.

## en
### Improved
- **Version numbers are now assigned automatically after merge.** Each fix writes its notes to its own file, so several fixes in parallel no longer grab each other's number or need renumbering.
- Every merge still ships a new version with Vietnamese and English notes, and the update is published right after.
