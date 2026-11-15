---
bump: patch
title: Secure Zernio account routing and preserve pending inbox messages
---
## vi
### Sửa lỗi
- Tin nhắn Zernio về đúng tài khoản và chatbot, vẫn nằm trong hộp thư khi nhân viên tiếp quản hoặc bot im lặng.
- Gom tin sau 5 giây từ tin cuối, khôi phục sau khởi động lại và bỏ giới hạn 5 câu vĩnh viễn.
### Bảo mật
- Xác minh tài khoản qua REST, kiểm tra chữ ký webhook và khóa adapter theo tài khoản. Không trả bí mật trong metadata.

## en
### Fixed
- Zernio messages reach the assigned account and chatbot and remain in the inbox during takeover or bot silence.
- Batch messages five seconds after the last arrival, recover after restart and remove the permanent five-reply cap.
### Security
- Verify accounts through REST, validate webhook signatures and scope adapter tokens to an account. Keep secrets out of metadata.
