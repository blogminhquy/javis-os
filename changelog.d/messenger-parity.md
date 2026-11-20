---
bump: minor
title: Messenger bots see which ad a customer came from, watch customer videos and read stickers
---
## vi
### Cải thiện
- **Bot Messenger biết khách tới từ quảng cáo nào.** Khách bấm quảng cáo "Gửi tin nhắn", link m.me có mã, hay khung chat trên website: bot thấy tên quảng cáo hoặc mã link, kể cả khi khách mở lại một cuộc chat cũ từ quảng cáo rồi mới gõ.
- **Bot xem được video khách gửi** (cắt vài khung hình, nghe cả lời nói nếu có key chuyển giọng nói), thay vì chỉ nhận một đường link không mở được.
- **Sticker và nút thích (👍) được hiểu đúng là cảm xúc**, bot không còn tải về rồi tả lại như một bức ảnh. Trên Instagram, khách trả lời story hay nhắc tài khoản trong story thì bot biết.
- **Messenger giới hạn tần suất hoặc tạm lỗi gửi thì bot chờ rồi gửi lại**, không mất câu trả lời.

## en
### Improved
- **Messenger bots know which ad a customer came from.** A click-to-Messenger ad, an m.me link with a ref, or the chat box on a website: the bot sees the ad title or the link's ref, even when the customer reopens an old chat from an ad and types afterwards.
- **The bot watches videos customers send** (a few frames, plus the speech when a speech-to-text key is set) instead of only receiving a link it cannot open.
- **Stickers and the like button (👍) are understood as reactions**, no longer downloaded and described as a photo. On Instagram, the bot knows when a customer replies to the account's story or mentions it in theirs.
- **When Messenger rate limits or has a temporary send failure, the bot waits and sends again** instead of losing the answer.
