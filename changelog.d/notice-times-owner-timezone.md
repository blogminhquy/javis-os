---
bump: patch
title: Notice times follow the timezone in Settings, not the server clock
---
## vi
### Sửa lỗi
- **Giờ trong thông báo đã khớp múi giờ trong Cài đặt.** Trên VPS, cảnh báo bảo mật và thẻ "Thông báo hệ thống" trong Javis Core từng in giờ máy chủ (UTC), lệch 7 tiếng với giờ Việt Nam. Nay chúng theo múi giờ anh chị đã chọn.
- Cùng lỗi đó được sửa ở dòng "mở lại lúc" khi ChatGPT Live hết lượt, giờ đồng bộ sao lưu, lần cuối Threads gửi bình luận, và giờ sự kiện webhook Javis đọc được.

## en
### Fixed
- **Notice times now match the timezone in Settings.** On a VPS, security alerts and the "System notice" card in Javis Core printed the server's clock (UTC), seven hours off Vietnam time. They now follow the timezone you picked.
- The same fix covers the "back at" time when ChatGPT Live runs out, the backup sync time, the last Threads reply, and the webhook event time Javis reads.
