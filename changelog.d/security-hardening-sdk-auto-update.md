---
bump: minor
title: Security hardening, the Claude Agent SDK updates itself, fewer disk syncs per chat turn
---
## vi
### Thêm mới
- **Claude Agent SDK tự cập nhật.** Cùng công tắc "Tự cập nhật Claude Code mỗi ngày" ở trang Models nay giữ luôn gói Claude Agent SDK ở bản mới nhất trong dòng của nó. Javis chỉ lấy bản đã ra ít nhất ba ngày, chạy thử trước khi giữ, lỗi thì tự lùi về bản cũ. Bản mới dùng từ lần khởi động lại kế tiếp. Bản Docker vẫn nhận theo ảnh Javis mới.

### Bảo mật
- **Siết khung chat, trung tâm công cụ và việc chạy nền.** Chữ trong tin nhắn không còn chen được mã vào trang điều khiển. Trung tâm công cụ chỉ trả lời chính máy đang chạy Javis. Việc chạy ở mức Ghi nháp chỉ ghi được file thường trong bộ não.
- **Chatbot trả lời khách dưới mức Toàn quyền không còn giao được việc cho AI chạy sau.** Nó vẫn tạo được lời nhắc chỉ nhắc bằng chữ. Cần bot tự giao việc thì nâng bot lên Toàn quyền.
- **Bộ não nhập từ tệp về luôn ở trạng thái nghỉ.** Vòng lặp, plugin và nhắc việc đều tắt dù tệp viết kiểu nào; cấu hình chạy lệnh của các engine không được nhập theo. Thư viện đọc PDF lên bản đã vá.

### Cải thiện
- **Chat nhẹ đĩa hơn, và một kết nối hỏng không còn kéo chậm mọi lượt.** Mỗi lượt chat bớt hàng chục lần ép ghi đĩa (đỡ rõ trên VPS). Nguồn dữ liệu đứng hình hai lần liền thì Javis trả lời ngay bằng danh sách công cụ đang có và dò lại ở nền.

## en
### Added
- **The Claude Agent SDK updates itself.** The "Update Claude Code automatically every day" switch on the Models page now also keeps the Claude Agent SDK package on the newest release of its series. Javis only takes a release at least three days old, checks it before keeping it and puts the old one back if the check fails. The new version is used from the next restart. The Docker build still gets it with each Javis image.

### Security
- **Tighter chat rendering, tool hub and background runs.** Text in a message can no longer slip code into the dashboard. The tool hub only answers the machine Javis runs on. A run at the Draft level only writes ordinary files inside the brain.
- **A customer chatbot below Full access can no longer queue work for the AI to run later.** It can still create a reminder that only says its text. Raise the bot to Full access if it should queue work itself.
- **A brain imported from a file always arrives at rest.** Loops, plugins and reminders are off however the file spells them, and engine settings that run commands are not imported. The PDF library moves to a patched release.

### Improved
- **Chat is lighter on the disk, and one broken connection no longer slows every turn.** Each chat turn forces far fewer disk syncs (most visible on a VPS). When a data source hangs twice in a row, Javis answers at once with the tools it has and retries in the background.
