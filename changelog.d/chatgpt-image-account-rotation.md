---
bump: patch
title: ChatGPT image generation uses the next account after a quota limit
---
## vi
### Sửa lỗi
- **Tạo ảnh ChatGPT không mắc kẹt ở tài khoản hết lượt.** Khi tài khoản đang dùng báo lỗi hạn mức, Javis thử tài khoản ChatGPT đã đăng nhập tiếp theo theo thứ tự trong Models. Lỗi khác không tự gửi lại yêu cầu tạo ảnh và tài khoản bị tắt không được sử dụng.

## en
### Fixed
- **ChatGPT image generation can use another signed-in account after quota exhaustion.** On a confirmed quota error, Javis retries on the next enabled account in Models order. Other errors do not trigger a retry, and disabled accounts remain unused.
