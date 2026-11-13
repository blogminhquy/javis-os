---
bump: patch
title: The Tasks and Partners pages open without a hitch and stay still when nothing changes
---
## vi
### Cải thiện
- **Trang Nhiệm vụ mở mượt hơn hẳn.** Trước đây mỗi lần mở, trang vẽ lại toàn bộ danh sách hai lần và dựng cả bản máy tính lẫn bản điện thoại. Giờ chỉ vẽ một lần, đúng bản đang hiện. Với 170 việc trên máy chậm: quãng đứng hình từ 0,45 giây xuống khoảng 0,1 giây, trên điện thoại gần như không còn.
- **Trang Cộng sự mở nhanh hơn.** Danh sách trợ lý trước đây bị vẽ lại năm lần mỗi lần mở trang, nay chỉ một lần, nên rê chuột và cuộn không còn bị giật lúc trang vừa hiện.
- **Gõ tìm việc không còn trễ chữ.** Danh sách lọc theo sau khi bạn ngừng gõ một nhịp ngắn, thay vì vẽ lại sau từng chữ.

### Sửa lỗi
- **Đang xem trang Nhiệm vụ không còn bị khựng định kỳ.** Cứ 30 giây (5 giây khi có việc đang chạy) trang lại vẽ lại toàn bộ danh sách dù không có gì mới, làm màn hình đứng một nhịp và mất chỗ đang rê chuột. Giờ không có gì đổi thì không vẽ lại.

## en
### Improved
- **The Tasks page opens much more smoothly.** It used to draw the whole list twice on every opening and build both the wide and the phone layout. Now it draws once, and only the layout on screen. With 170 tasks on a slow machine: the freeze went from 0.45 seconds to about 0.1, and is all but gone on a phone.
- **The Partners page opens faster.** The list of assistants used to be drawn five times on each opening, now once, so hovering and scrolling no longer stutter right after the page appears.
- **Typing in the task search no longer lags.** The list follows a short moment after you stop typing instead of being redrawn after every letter.

### Fixed
- **The Tasks page no longer hitches every so often while you look at it.** Every 30 seconds (5 while a task was running) it redrew the whole list even when nothing was new, freezing the screen for a beat and dropping the row under the pointer. Now nothing is redrawn when nothing changed.
