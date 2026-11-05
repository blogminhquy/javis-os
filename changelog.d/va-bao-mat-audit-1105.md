---
bump: patch
title: Security fixes from the November 5 audit
---
## vi
### Bảo mật
- **Chatbot và việc nền dưới mức Toàn quyền không còn ghi được chỗ chứa mã chạy.** Thư mục plugins/, Javis/ (loop, script), .git, .claude và cấu hình engine chỉ chủ ở mức Toàn quyền mới ghi được. Chatbot trả lời khách thì không ghi được ở mọi mức.
- **Việc hẹn giờ không vượt mức của người tạo.** Nhắc hẹn hay việc Kanban do một lượt chạy mức "auto" hoặc "suggest" tạo ra giờ chạy đúng mức đó, không còn mặc định Toàn quyền. Lượt dưới Toàn quyền cũng không sửa được việc đã lên lịch.
- **File HTML, SVG, XML mở từ brain chạy trong hộp cách ly.** Giống link chia sẻ, script trong file đó không còn dùng được phiên đăng nhập của chủ. PDF và ảnh vẫn hiện như cũ.
- **Thêm kết nối MCP cần Toàn quyền và chatbot khách không thấy tool này.**
- **Đường miễn đăng nhập cho công cụ trên máy (/reminders) từ chối request từ trang web**, kể cả trang đổi tên miền về 127.0.0.1.
- **Thư mục .grok/ (chứa mã hub) không còn vào git và bản sao lưu GitHub.** Brain đã lỡ commit thì được gỡ khỏi git ở lần sao lưu sau. Nếu bạn từng dùng Grok Build và có sao lưu, nên đổi mã hub: xoá file `.hub_token` trong thư mục dữ liệu Javis rồi khởi động lại.

## en
### Security
- **Chatbots and background work below Full access can no longer write where code runs.** plugins/, Javis/ (loops, scripts), .git, .claude and engine config can only be written by the owner at Full access. A customer chatbot cannot write there at any level.
- **Scheduled work no longer outranks whoever created it.** A reminder or Kanban job created by an "auto" or "suggest" run now runs at that level instead of Full access by default. A run below Full access can no longer edit an existing scheduled job.
- **HTML, SVG and XML files opened from a brain run in a sandbox.** As with share links, their script can no longer use the owner's login. PDFs and images show as before.
- **Adding an MCP connection needs Full access, and customer chatbots no longer see that tool.**
- **The login-free path for tools on the machine (/reminders) refuses requests from web pages**, including a page that rebinds its domain to 127.0.0.1.
- **The .grok/ folder (it holds the hub key) no longer goes into git or the GitHub backup.** A brain that committed it has it untracked at the next backup. If you used Grok Build with backup on, rotate the hub key: delete `.hub_token` in the Javis data folder and restart.
