---
bump: minor
title: Zalo OA bot steps back when staff reply by hand, and setup no longer gets stuck
---
## vi
### Thêm mới
- **Bot Zalo OA nhường khi nhân viên trả lời tay.** Nhân viên nhắn cho khách từ trang quản lý OA thì bot im với riêng khách đó trong số phút nhường của bot (mặc định 30), tin nhân viên vào Hộp thư, hết giờ bot tự trả lời lại. Cần bật các sự kiện `oa_send_*` ở trang Webhook của app Zalo.

### Sửa lỗi
- **Lưu được webhook Zalo OA lần đầu.** Zalo chỉ hiện OA Secret Key sau khi webhook lưu xong, nên khi chưa có kênh OA nào Javis trả 200 (và bỏ tin) thay vì 401.
- **Mã xác thực tên miền Zalo dán thiếu đuôi .html vẫn đọc đúng.**
- Tin của một OA khác dùng chung app không bao giờ được giao cho bot của OA này.

## en
### Added
- **The Zalo OA bot steps back when staff reply by hand.** When staff message a customer from the OA admin page, the bot goes quiet for that customer for the bot's yield minutes (30 by default), the staff message lands in the inbox, and the bot answers again afterwards. Turn on the `oa_send_*` events on the Zalo app's Webhook page.

### Fixed
- **The Zalo OA webhook saves the first time.** Zalo shows the OA Secret Key only after the webhook saves, so with no OA channel yet Javis answers 200 (and drops the event) instead of 401.
- **A Zalo domain verification code pasted without .html is read correctly.**
- Events of another OA on the same app are never handed to this OA's bot.
