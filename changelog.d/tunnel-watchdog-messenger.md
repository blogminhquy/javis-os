---
bump: patch
title: Quick tunnel restarts itself when it drops, Messenger follows the new link
---
## vi
### Sửa lỗi
- **Messenger không còn im lặng hàng giờ khi đường hầm nhanh rớt.** Đường hầm Cloudflare nhanh có lúc mất kết nối mà tiến trình vẫn chạy, link trycloudflare.com chết và Meta gửi tin vào chỗ không ai nghe. Javis giờ kiểm tra đường hầm mỗi 20 giây, tự khởi động lại khi mất kết nối quá 90 giây, rồi tự trỏ webhook Facebook và Instagram sang link mới. Không cần bấm Sửa tự động nữa. Webhook đặt trên tên miền riêng không bị đụng tới.

## en
### Fixed
- **Messenger no longer goes silent for hours when the quick tunnel drops.** A Cloudflare quick tunnel could lose its connection while the process kept running, so the trycloudflare.com link died and Meta sent messages nowhere. Javis now checks the tunnel every 20 seconds, restarts it after 90 seconds without a connection, then points the Facebook and Instagram webhooks at the new link by itself. No Repair click needed. A webhook on your own domain is never touched.
