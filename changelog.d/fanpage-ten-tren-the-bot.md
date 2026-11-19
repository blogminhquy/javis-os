---
bump: patch
title: Bot cards show the Facebook Page name instead of its numeric ID
---
## vi
### Sửa lỗi
- **Thẻ bot hiện tên Fanpage thay vì Page ID dạng số.** Trang gắn bằng cách dán token trước đây chỉ lưu ID nên chip kênh hiện một dãy số, khó biết là Trang nào. Nay mỗi lần bot khởi động, Javis lưu tên thật của Trang và chip hiện tên đó. Nhãn bạn tự đặt (tên viết tắt) vẫn được ưu tiên, còn ID xem được khi rê chuột vào chip.

## en
### Fixed
- **Bot cards show the Facebook Page name instead of its numeric ID.** A Page added by pasting its token only stored the ID, so the channel chip showed a string of digits. Each time the bot starts, Javis now keeps the Page's real name and the chip shows it. A label you set yourself (a short name) still wins, and the ID shows when you hover the chip.
