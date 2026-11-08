---
bump: minor
title: Each app start, page and chat switch reads everything it needs in one round trip
---
## vi
### Cải thiện
- **Mở app, vào trang, đổi hội thoại giờ hỏi máy chủ một chuyến thay vì nhiều đợt nối tiếp.** Javis học xem mỗi lúc như vậy cần đọc những gì, lần sau gửi gộp tất cả trong một lượt, máy chủ trả từng phần ngay khi xong. Đo qua mạng chậm: mở app từ 3,5 giây còn 2,6 giây, số lượt hỏi từ 47 còn 22; đổi hội thoại từ 5 lượt hỏi còn 1.
- Phần nào máy chủ không gộp được thì trang tự hỏi riêng như cũ, nên không có gì bị thiếu.

## en
### Improved
- **Opening the app, a page or a chat now asks the server in one trip instead of several waves.** Javis learns what each of these moments reads, then sends it all together next time, and the server streams each answer back as soon as it is ready. Measured over a slow link: app start from 3.5 s to 2.6 s and from 47 requests to 22; a chat switch from 5 requests to 1.
- Anything the server leaves out of a batch is simply asked for on its own, as before, so nothing goes missing.
