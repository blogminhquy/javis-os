---
bump: patch
title: Opening a long team no longer re-reads its whole history, and the start-up screen hands over sooner
---
## vi
### Sửa lỗi
- **Mở một Team đã chat nhiều giờ không còn làm cả app chậm lại.** Từ bản 0.518.0, mỗi lần mở Team trên màn hình rộng là tab Thông tin tự mở, và máy chủ đọc lại toàn bộ tin nhắn của nhóm để dò file và link. Nhóm càng dài càng chậm, và trong lúc đó tải tin nhắn, chuyển nhóm, gửi tin đều phải chờ. Giờ máy chủ nhớ kết quả, lần sau chỉ đọc tin mới. Đo với nhóm 3.000 tin: từ 1,5 giây mỗi lần mở còn 0,003 giây.
- Mục Tài liệu của một cuộc trò chuyện dài cũng nhanh theo, vì dùng chung cách đọc này.
### Cải thiện
- **Màn "Đang khởi động Javis…" nhường chỗ cho app nhanh hơn.** Dữ liệu trang đầu về xong là màn này tắt gần như ngay.
- **Máy tải dữ liệu chậm không còn bị che tới 12 giây.** Trang đầu đã mở mà danh sách còn tải thì sau 4 giây app hiện ra, phần nào chưa xong tự hiện dòng "Đang tải" của nó như mọi trang khác.

## en
### Fixed
- **Opening a team with hours of chat no longer slows the whole app.** Since 0.518.0, opening a team on a wide screen also opened its Info tab, and the server read every message of the team again to look for files and links. The longer the team, the slower, and meanwhile loading messages, switching teams and sending all had to wait. The server now keeps the result and reads only new messages. Measured on a team with 3,000 messages: from 1.5 seconds per open to 0.003 seconds.
- The Documents list of a long conversation is faster too, since it reads the same way.
### Improved
- **The "Starting Javis…" screen hands over to the app sooner.** Once the first page has its data the screen goes almost at once.
- **A machine that loads data slowly is no longer covered for up to 12 seconds.** When the first page is open but a list is still loading, the app shows after 4 seconds and the unfinished part keeps its own "Loading" line, as on every other page.
