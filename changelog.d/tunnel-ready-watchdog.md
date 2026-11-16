---
bump: patch
title: The quick tunnel restarts itself when it loses its connection, and Messenger follows the new link
---
## vi
### Sửa lỗi
- **Đường hầm Cloudflare tự khởi động lại khi mất kết nối.** Trước đây máy ngủ dậy thì cloudflared vẫn chạy nhưng không còn nối tới Cloudflare, link chết cho tới khi tắt tay. Giờ Javis kiểm tra vài giây một lần và tự bật lại sau khoảng 1,5 phút hỏng.
- **Messenger tự theo link nhanh mới.** Sau khi đường hầm nhanh đổi địa chỉ, Javis tự khai lại webhook của app Meta (cả Instagram nếu có) sang link mới, khách nhắn tin không bị rơi.

## en
### Fixed
- **The Cloudflare tunnel restarts itself when it loses its connection.** After the computer woke from sleep, cloudflared could keep running without a connection to Cloudflare, and the link stayed dead until someone stopped it by hand. Javis now checks every few seconds and restarts it after about 1.5 minutes of trouble.
- **Messenger follows the new quick link.** When the quick tunnel changes address, Javis re-registers the Meta app's webhook (Instagram too) on the new link, so customer messages keep arriving.
