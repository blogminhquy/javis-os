---
bump: patch
title: A Team that has worked a lot no longer makes pages lose their connection
---
## vi
### Sửa lỗi
- **Dùng Team nhiều không còn làm rớt kết nối tới máy chủ.** Team càng chạy nhiều lượt thì mỗi lần mở team Javis càng lâu mới cộng xong mức dùng của nó: team vài nghìn lượt mất cả phút, trang chờ quá 30 giây thì báo mất kết nối rồi gọi lại, và cả máy chủ đứng theo. Giờ việc này nhanh hơn khoảng 100 lần và không bao giờ chạy chồng lên nhau.
- **Mỗi lần gọi model không còn làm máy chủ khựng.** Sổ mức dùng từng giữ một dòng cho mỗi lần Team gọi model suốt 30 ngày và bị ghi lại toàn bộ sau mỗi lần gọi, nên file phình tới hàng chục MB, chat thường cũng chậm theo. Javis tự dọn file này lúc khởi động, số liệu mức dùng giữ nguyên.

## en
### Fixed
- **Heavy Team use no longer drops the connection to the server.** The more turns a team had run, the longer Javis took to add up its usage every time the team was opened: a team of a few thousand turns took a minute, the page gave up after 30 seconds and asked again, and the whole server stalled. It is now about 100 times faster and never runs twice at once.
- **A model call no longer makes the server pause.** The usage ledger kept one line for every Team model call for 30 days and was rewritten in full after each call, so the file grew to tens of megabytes and ordinary chat slowed down too. Javis cleans the file when it starts; your usage figures stay the same.
