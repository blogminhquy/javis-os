---
bump: minor
title: Chats and pages open instantly from what this browser already saw
---
## vi
### Cải thiện
- **Mở lại hội thoại hiện ngay, kể cả sau khi tải lại trang.** Javis giữ phần cuối của 50 cuộc gần nhất ngay trong trình duyệt, vẽ ngay từ đó rồi mới hỏi máy chủ bản mới. Đo qua mạng chậm: từ khoảng 0,3 giây xuống còn 0,03-0,04 giây.
- **Cuộc vừa dạy Javis không còn phải tải lại từ đầu.** Rời một cuộc đang có tin mới thì Javis lấy sẵn bản mới ở nền, Javis trả lời xong ở cuộc khác cũng vậy. Các cuộc đầu danh sách được tải trước khi máy rảnh, kể cả trên điện thoại.
- **Quay lại các trang Kỹ năng, Kết nối, Kênh, Cài đặt, Models, Tự học, Plugin, Webhook hiện ngay.** Trang vẽ ngay dữ liệu lần trước rồi tự cập nhật nếu có gì đổi, trừ khi đã có thao tác bấm hay gõ trên trang. Đo qua mạng chậm: từ 0,3-0,7 giây xuống 0,02-0,1 giây.
- Đăng xuất là xoá các hội thoại đã giữ trong trình duyệt.

## en
### Improved
- **Going back to a chat shows it at once, even after reloading the page.** Javis keeps the last part of the 50 most recent chats in this browser, draws from it, then asks the server for the newest copy. Measured over a slow link: from about 0.3 s down to 0.03-0.04 s.
- **The chat you are teaching Javis in no longer loads from scratch.** Leaving a chat with new messages fetches its new copy in the background, and so does a reply that finishes in another chat. The first chats of the list are loaded ahead when the device is idle, phones included.
- **The Skills, Connections, Channels, Settings, Models, Self-learning, Plugins and Webhooks pages show at once on a return visit.** A page draws the data of the last visit, then updates itself if anything changed, unless you already clicked or typed on it. Measured over a slow link: from 0.3-0.7 s down to 0.02-0.1 s.
- Signing out clears the chats kept in the browser.
