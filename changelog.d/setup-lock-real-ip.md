---
bump: patch
title: A lost password no longer opens the account form to strangers, and the security log shows the real visitor
---
## vi
### Bảo mật
- **Mất mật khẩu không còn mở cửa cho người lạ tạo tài khoản.** Máy đã từng có chủ mà mật khẩu biến mất thì trang tạo tài khoản bị khoá khi mở từ xa, chỉ mở trên chính máy chạy Javis, hoặc trong 24 giờ sau khi chạy `python tools/reset_auth.py`. Lần thử bị chặn có cảnh báo trong nhật ký bảo mật.
- **Có `JAVIS_ADMIN_PASSWORD` thì tài khoản tự về lại ngay** khi mật khẩu bị mất, không phải đợi khởi động lại. Tắt đăng nhập có chủ ý thì vẫn giữ nguyên đến lần khởi động sau.
- **Lưu cài đặt không còn xoá được mật khẩu của chủ,** trừ đúng nút tắt đăng nhập và công cụ đặt lại. Lần lưu nào định xoá sẽ bị chặn và có cảnh báo.
- **Nhật ký bảo mật ghi IP thật của người truy cập** qua Cloudflare và proxy, không còn ghi IP của Cloudflare. Khoá đăng nhập sai nhiều lần cũng tính theo từng người thật, nên một người dò mật khẩu không khoá luôn cả chủ.
- Test chạy trên máy đang dùng không còn đụng vào cài đặt, thư mục não hay mật khẩu thật.

## en
### Security
- **A lost password no longer lets a stranger create an account.** On a machine that had an owner, a missing password locks the account form for remote visitors. It opens only on the machine running Javis, or for 24 hours after `python tools/reset_auth.py`. A blocked try shows up as an alert in the security log.
- **With `JAVIS_ADMIN_PASSWORD` set, the account comes back at once** when the password goes missing, without a restart. Turning sign-in off on purpose still holds until the next start.
- **Saving settings can no longer erase the owner's password,** except through the sign-in off switch and the reset tool. A save that tries is blocked and raises an alert.
- **The security log records the visitor's real IP** behind Cloudflare and proxies, not Cloudflare's. The wrong-password lockout also counts per real visitor, so someone guessing passwords no longer locks the owner out too.
- Tests run on a machine in use no longer touch its real settings, brain folders or password.
