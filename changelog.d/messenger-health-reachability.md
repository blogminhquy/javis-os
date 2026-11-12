---
bump: patch
title: Messenger check detects an unreachable webhook and a stale quick-tunnel address
---
## vi
### Sửa lỗi
- **Kiểm tra Messenger phát hiện được webhook không truy cập được.** Trước đây mọi dòng đều báo ổn trong khi đường HTTPS đã chết, nên bot không trả lời mà không rõ vì sao.
- **Link nhanh đổi địa chỉ thì Sửa tự động trỏ lại đúng địa chỉ đang chạy**, giữ nguyên đường dẫn nhận tin, và chỉ lưu sau khi Meta xác minh thành công.

## en
### Fixed
- **The Messenger check now detects a webhook that cannot be reached.** Every line used to say fine while the HTTPS address was dead, so the bot stayed silent with no visible reason.
- **When the quick tunnel gets a new address, automatic repair points the webhook at the running one**, keeps the receiver path, and saves it only after Meta verifies it.
