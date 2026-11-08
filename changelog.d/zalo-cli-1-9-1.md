---
bump: patch
title: Zalo messages after a short connection drop reach the inbox and the bot live
---
## vi
### Sửa lỗi
- **Tin Zalo không còn lọt khỏi Hộp thư sau mỗi lần rớt mạng ngắn.** Javis dùng javis-zalo 1.9.1. Trước đây khi kết nối Zalo rớt dưới 5 giây rồi tự nối lại, tin nhắn trong lúc đó chỉ vào kho lịch sử, không tới Hộp thư và bot. Giờ chúng tới ngay như tin thường. Một tin lỗi cũng không còn kéo mất các tin đi cùng lô với nó.

## en
### Fixed
- **Zalo messages no longer slip past the inbox after a short connection drop.** Javis uses javis-zalo 1.9.1. When the Zalo connection dropped for under 5 seconds and came back on its own, the messages in between only reached the history, not the inbox or the bot. They now arrive live like any other message. One faulty message also no longer takes the rest of its batch down with it.
