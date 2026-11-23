---
bump: patch
title: Faster start, more warm chat turns, a smaller start-up bundle
---
## vi
### Cải thiện
- **Javis khởi động lại nhanh hơn khoảng 13 giây.** Bản cài bằng Docker đã biên dịch sẵn mã, nên sau mỗi lần cập nhật không còn phải chờ lâu mới dùng được.
- **Lượt chat ngay sau khi Javis gom gọn một cuộc dài không còn phải chờ khởi động lại từ đầu.** Javis mở sẵn phiên mới ngay khi biết lượt kế sẽ cần. Tắt bằng `JAVIS_WARM_NEW_THREAD=0`.
- **Mở dashboard nhẹ hơn.** Mã của trang Cộng sự, trình sửa Skill và thẻ Messenger chỉ tải khi mở tới các trang đó, bớt khoảng 10% mã phải chạy lúc mở. Ba con số đếm ở màn chính cũng thôi tải trọn danh sách agent.
- **Javis ghi lại vì sao một lượt chat phải chờ lâu** (cuộc mới, vừa gom gọn, để yên quá lâu, đổi cấu hình), để lần sau sửa đúng chỗ chậm.

## en
### Improved
- **Javis restarts about 13 seconds faster.** The Docker image now ships its code precompiled, so an update no longer leaves you waiting before you can use it.
- **The chat turn right after Javis trims a long conversation no longer starts from cold.** Javis opens the new session ahead of time as soon as it knows the next turn needs one. Switch it off with `JAVIS_WARM_NEW_THREAD=0`.
- **The dashboard opens lighter.** The code for the Partners page, the Skill editor and the Messenger card loads only when you open those pages, about 10% less code to run at start. The three counters on the home screen also stop downloading the whole agent list.
- **Javis now records why a chat turn had to wait** (new chat, just trimmed, idle too long, settings changed), so the next fix lands on the real slow spot.
