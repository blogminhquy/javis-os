---
bump: minor
title: One bot can serve up to 100 Facebook Pages
---
## vi
### Cải thiện
- **Một bot trực được tới 100 Fanpage.** Messenger và Instagram nhận tin qua webhook nên mỗi Trang gần như không tốn gì thêm. Shop nhiều Fanpage giờ dùng một bot, dạy một lần. Các kênh khác (Zalo, Telegram...) vẫn tối đa 20 tài khoản mỗi bot.
### Sửa lỗi
- **Chọn quá giới hạn không còn mất Trang âm thầm.** Trước đây tích hơn 20 tài khoản thì bot chỉ giữ 20, số còn lại bị bỏ mà không báo. Giờ Javis từ chối và nói rõ kênh nào đang quá, bot giữ nguyên như cũ.

## en
### Improved
- **One bot can serve up to 100 Facebook Pages.** Messenger and Instagram arrive by webhook, so each Page costs almost nothing extra. A shop with many Pages now uses one bot, trained once. Other channels (Zalo, Telegram...) still allow 20 accounts per bot.
### Fixed
- **Going over the limit no longer drops Pages silently.** Before, ticking more than 20 accounts kept only 20 and quietly dropped the rest. Now Javis refuses, names the channel that is over, and leaves the bot as it was.
