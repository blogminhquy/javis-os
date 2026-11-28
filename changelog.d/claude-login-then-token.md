---
bump: minor
title: Connect Claude signs in fully first, then adds the token as the backup
---
## vi
### Cải thiện
- **Kết nối Claude giờ làm 2 bước liền nhau.** Bước 1 đăng nhập claude.ai đầy đủ, nên Gmail, Lịch, Drive... đã thêm trên claude.ai chạy được ngay. Bước 2 tự hiện ra để lấy token dài hạn làm dự phòng, lúc này claude.ai đã đăng nhập sẵn nên chỉ cần bấm Authorize.
- **Bỏ qua bước 2 vẫn được nhắc.** Thẻ hiện dòng vàng "Chưa có token dự phòng" kèm nút lấy token, và chuông nhắc một lần, để phiên đăng nhập hết hạn không làm bot và việc nền dừng.
- Mac và Windows giữ cách cũ: token là đường vào duy nhất.

## en
### Improved
- **Connect Claude now does two steps in a row.** Step 1 is the full claude.ai sign-in, so the Gmail, Calendar, Drive... added on claude.ai work right away. Step 2 follows on its own to get the long-lived token as the backup; claude.ai is already signed in by then, so it is one click on Authorize.
- **Skipping step 2 still gets a reminder.** The card shows an amber "No backup token yet" line with a button for the token, and the bell reminds once, so a sign-in running out never stops bots and background work.
- Mac and Windows keep the old way: the token is the one way in.
