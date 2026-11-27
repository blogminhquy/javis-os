---
bump: minor
title: Google Workspace through Google's own MCP servers, one sign-in for nine services
---
## vi
### Thêm mới
- **Thẻ Google Workspace chính chủ Google.** Gmail, Lịch, Drive, Docs, Sheets, Slides, Tasks, Chat và Danh bạ đi qua server MCP chính thức của Google (phát hành chính thức 24/11/2026, cùng nền với Google Workspace CLI), chỉ một lần đăng nhập. Đăng nhập ngay trong dashboard nên chạy được cả trên VPS, không cần máy có màn hình như thẻ cũ. Tạo OAuth client khoảng 3 phút bằng trang Personal mode của Google: tự bật API, không phải làm màn hình đồng ý hay xác minh app.
- **Google hỏi trước khi làm việc nhạy cảm.** Gửi thư ra ngoài, chia sẻ, bỏ vào thùng rác: Google dừng lại hỏi, Javis đưa câu hỏi kèm bản xem trước cho bạn trong khung chat, bạn đồng ý thì việc mới chạy. Javis không bao giờ tự trả lời thay bạn.

### Cải thiện
- **Trang Kết nối gọn hơn:** bỏ ô gom nhóm "Google" phải bấm vào chọn dịch vụ. Giờ chỉ một thẻ Google Workspace bấm là nối; Sheets, Keep và các dịch vụ Google khác đứng riêng như mọi thẻ khác.
- Thẻ Google Workspace cũ (bản cộng đồng workspace-mcp), Google Tasks, Gmail và Google Calendar riêng không còn hiện để thêm mới. Kết nối đã có vẫn chạy y nguyên.

### Bảo mật
- **Thẻ Gmail: gửi thư thật giờ cần mức Toàn quyền.** Google vừa thêm vào server Gmail các tool gửi, trả lời, chuyển tiếp, bỏ thùng rác và đánh dấu spam. Trước bản này, kết nối Gmail ở mức Ghi nháp gửi được thư thật, và mức Chỉ đọc đánh dấu spam được.

## en
### Added
- **Google Workspace card through Google's own servers.** Gmail, Calendar, Drive, Docs, Sheets, Slides, Tasks, Chat and Contacts go through Google's official MCP servers (generally available on 2026-11-24, the same backend as the Google Workspace CLI), with one sign-in. You sign in inside the dashboard, so it works on a VPS too, without the screen the old card needed. Making the OAuth client takes about 3 minutes with Google's Personal mode page: it enables the APIs, with no consent screen or app verification to do.
- **Google asks before sensitive actions.** Sending mail outside, sharing, moving to trash: Google stops and asks, Javis shows you the question and Google's preview in the chat, and the action runs only if you agree. Javis never answers for you.

### Improved
- **Tidier Connections page:** the "Google" group card that opened a service picker is gone. One Google Workspace card connects in one click; Sheets, Keep and the other Google services are cards of their own like any other.
- The old Google Workspace card (community workspace-mcp), Google Tasks, and the single Gmail and Google Calendar cards are no longer offered for new connections. Connections already made keep running unchanged.

### Security
- **Gmail card: sending real mail now needs Full access.** Google added send, reply, forward, trash and spam tools to its Gmail server. Before this release a Gmail connection at Draft could send real mail, and one at Read-only could mark spam.
