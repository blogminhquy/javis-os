---
bump: patch
title: Javis opens in about a second and stays light when left alone
---
## vi
### Cải thiện
- **Mở Javis nhanh hơn rõ rệt.** Màn "Đang khởi động Javis…" trước đây luôn đứng đủ 4 giây trên máy có hơn một trang cuộc chat, dù dữ liệu đã về sau khoảng 1 giây. Giờ dữ liệu về là app hiện ngay. Đồ thị bộ não cũng không còn được dựng ngầm khi bạn mở thẳng vào Trò chuyện hay Cộng sự.
- **Để yên thì Javis gần như không tốn máy.** Vành của linh vật, nền sao và đồ thị không còn bắt trình duyệt làm việc 60 lần mỗi giây khi không có gì thay đổi, nên cuộn và gõ mượt hơn, máy đỡ nóng.

### Sửa lỗi
- **Dùng lâu không còn ì dần.** Mỗi lần mở trang Trò chuyện, trình duyệt giữ lại cả trang cũ trong bộ nhớ, đổi trang càng nhiều máy càng nặng. Giờ trang cũ được dọn sạch.
- **Màn Đồ thị hết khựng.** Đồ thị nhớ chỗ các chấm đã nằm nên lần mở sau hiện ngay, không tính lại từ đầu (bộ não 2.600 ghi chú: quãng đứng hình dài nhất từ hơn 1 giây xuống khoảng 0,2 giây). Chấm vừa rê qua cũng không còn sáng mãi và vẽ liên tục sau khi chuột đã rời đi.

## en
### Improved
- **Javis opens much faster.** The "Starting Javis…" screen used to stay for a full 4 seconds on any machine with more than one page of chats, although the data was there after about 1 second. Now the app shows as soon as the data arrives. The brain graph is also no longer built in the background when you open straight into Chat or Partners.
- **Left alone, Javis costs almost nothing.** The mascot's ring, the starfield and the graph no longer make the browser work 60 times a second when nothing changes, so scrolling and typing are smoother and the device runs cooler.

### Fixed
- **No more slowing down over a long session.** Every visit to the Chat page left the whole previous page in memory, so the more you switched pages the heavier it got. The old page is now released.
- **The Graph screen no longer stutters.** The graph remembers where its dots came to rest, so the next opening shows at once instead of working it all out again (a brain of 2,600 notes: the longest freeze went from over 1 second to about 0.2). A dot you pointed at also no longer stays lit and keeps the graph drawing after the pointer has left.
