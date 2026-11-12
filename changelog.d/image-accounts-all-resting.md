---
bump: patch
title: Image generation still tries a ChatGPT account when all of them are resting
---
## vi
### Sửa lỗi
- **Tạo ảnh ChatGPT không báo "không có tài khoản" khi mọi tài khoản đang nghỉ vì hết lượt chat.** Javis vẫn thử tài khoản đang bật đầu tiên, như trước khi có xoay tài khoản. Tài khoản đã tắt thì vẫn không được dùng.

## en
### Fixed
- **ChatGPT image generation no longer says "no account" while every account rests after a chat limit.** Javis still tries the first switched-on account, as it did before account rotation. Switched-off accounts stay unused.
