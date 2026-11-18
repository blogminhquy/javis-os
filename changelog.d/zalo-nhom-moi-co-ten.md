---
bump: patch
title: Zalo groups joined after start-up show their name
---
## vi
### Sửa lỗi
- **Nhóm Zalo mới vào cũng có tên.** Bộ Zalo (javis-zalo 1.12.0) trước chỉ nạp tên nhóm một lần lúc khởi động, nên nhóm nick vào sau đó hiện thành "Nhóm …" kèm đuôi id cho tới lần khởi động lại. Giờ tin đầu tiên từ nhóm lạ sẽ kèm tra tên nhóm, và nhóm đổi tên cũng được cập nhật.

## en
### Fixed
- **New Zalo groups get their name.** The Zalo layer (javis-zalo 1.12.0) only loaded group names once at start-up, so a group the account joined later showed as "Group …" with the end of its id until a restart. The first message from an unknown group now looks its name up, and a renamed group is updated too.
