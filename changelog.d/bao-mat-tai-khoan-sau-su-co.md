---
bump: minor
title: Security tab with sign-in history, outside-edit detection and alerts
---
## vi
### Bảo mật
- **Tab Bảo mật mới trong trang Tài khoản.** Xem 2FA, thiết bị đang đăng nhập (IP, trình duyệt, lần hoạt động cuối) và lịch sử đăng nhập đúng, sai, mọi lần đổi tài khoản. Đăng xuất từng thiết bị hoặc mọi thiết bị khác mà không cần đổi mật khẩu.
- **Báo ngay khi tài khoản có biến.** Đổi tên, đổi mật khẩu, bật tắt 2FA, đăng nhập từ mạng lạ: chuông và Telegram của chủ báo liền. File cài đặt bị sửa từ ngoài Javis thì mọi thiết bị bị đăng xuất và có cảnh báo đỏ.
- **Trợ lý AI không còn đụng được file bí mật** (cài đặt, khoá mã hoá, phiên đăng nhập), ở mọi mức quyền. Gỡ 2FA khi bị khoá chỉ cần thêm `JAVIS_RESET_2FA=1` rồi Redeploy.
- **Hostinger: cổng 7777 tự đóng ra ngoài khi đã có tên miền HTTPS**, chỉ còn đường vào có mã hoá.

## en
### Security
- **New Security tab on the Account page.** See 2FA, the devices signed in (IP, browser, last activity) and the history of successful and failed sign-ins and every account change. Sign out one device or all others without changing the password.
- **Instant alerts on account changes.** Username, password or 2FA changes and sign-ins from a new network reach the owner's bell and Telegram right away. If the settings file is edited outside Javis, every device is signed out and a red warning shows.
- **The AI assistant can no longer touch secret files** (settings, encryption key, sessions) at any permission level. To remove 2FA when locked out, add `JAVIS_RESET_2FA=1` and redeploy.
- **Hostinger: port 7777 closes to the Internet once an HTTPS domain is set**, leaving only the encrypted way in.
