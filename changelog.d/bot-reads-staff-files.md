---
bump: minor
title: Bots read the files staff and customers send on Zalo OA and Fanpage
---
## vi
### Thêm mới
- **Bot đọc được file nhân viên gửi cho khách trên Zalo OA và Fanpage.** Báo giá PDF, Word, Excel hay ảnh nhân viên gửi từ app OA hoặc hộp thư Trang giờ hiện trong Hộp thư (nhãn Nhân viên), và bot biết nội dung để trả lời khi khách hỏi lại. Ảnh được một bộ não đã kết nối có mắt đọc hộ.
- **Bot đọc được file PDF, Word, Excel khách gửi**, không chỉ biết là "có file" như trước.

### Cải thiện
- **Cần bật thêm một lần:** Zalo OA bật sự kiện `oa_send_text`, `oa_send_image`, `oa_send_file` ở mục Webhook của app. Fanpage bấm **Sửa tự động** ở bảng kiểm tra để Javis bật `message_echoes`.

## en
### Added
- **Bots read the files staff send customers on Zalo OA and Fanpage.** A PDF, Word or Excel quote, or a photo, sent from the OA app or the Page inbox now shows in the Inbox (labelled Staff) and the bot knows what it says when the customer asks about it. Photos are read by a connected brain that can see.
- **Bots read the PDF, Word and Excel files customers send**, instead of only knowing "there is a file".

### Improved
- **One step to turn it on:** for Zalo OA, enable the `oa_send_text`, `oa_send_image` and `oa_send_file` events in the app's Webhook section. For a Fanpage, click **Repair** on the checklist so Javis turns on `message_echoes`.
