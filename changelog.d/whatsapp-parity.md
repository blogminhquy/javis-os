---
bump: minor
title: WhatsApp bots read catalog orders, contacts and ad clicks, and stop showing typing when paused
---
## vi
### Cải thiện
- **Bot WhatsApp đọc được đơn đặt hàng từ catalog.** Trước đây khách bấm gửi giỏ hàng thì bot bỏ qua cả đơn. Giờ bot thấy từng sản phẩm, số lượng, tổng tiền và lời nhắn kèm theo. Danh bạ khách gửi, biểu mẫu WhatsApp Flow, tên và địa chỉ của vị trí cũng tới được bot.
- **Bot biết khách tới từ quảng cáo nào** (quảng cáo bấm vào nhắn WhatsApp) và khách đang hỏi sản phẩm nào trong catalog, để trả lời đúng ý.
- **Bot đang tạm dừng hoặc bạn đang tiếp quản thì khách không còn thấy "đang soạn tin..." rồi im luôn.** Dòng đó chỉ hiện khi bot thật sự trả lời.
- **WhatsApp giới hạn tần suất thì bot chờ rồi gửi lại**, video gửi đi xem được ngay trong chat, ảnh quá cỡ tự gửi thành tài liệu thay vì báo lỗi.

## en
### Improved
- **WhatsApp bots read catalog orders.** Before, when a customer sent their cart the bot ignored the whole order. It now sees each product, the quantity, the total and the note. Shared contacts, WhatsApp Flow forms, and a location's name and address also reach the bot.
- **The bot knows which ad the customer came from** (click-to-WhatsApp ads) and which catalog product they are asking about, so it can answer to the point.
- **A paused bot, or one you have taken over, no longer shows the customer "typing..." and then says nothing.** The indicator only appears when the bot is really answering.
- **When WhatsApp rate limits, the bot waits and sends again**, videos go out playable in the chat, and an image too large for WhatsApp goes as a document instead of failing.
