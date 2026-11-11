---
bump: patch
title: Zalo direct mentions survive a Javis restart
---
## vi
### Sửa lỗi
- **Tag bot Zalo trong nhóm không còn bị nhầm là tag người khác sau khi Javis khởi động lại.** Lưu Zalo ID đã xác minh từ tin do chính tài khoản gửi, dùng lại khi khởi động lại và từ chối ID không khớp.

## en
### Fixed
- **Zalo group @mentions keep targeting the bot after a Javis restart.** Retain an account ID verified from its own outgoing group messages, restore it after restart, and fail closed on conflicting identities.
