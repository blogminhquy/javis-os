---
bump: patch
title: Background jobs that need you ask instead of retrying in silence
---
## vi
### Sửa lỗi
- **Việc nền cần bạn thì hỏi bạn, không lặng lẽ chạy lại.** Bước quy trình kiểm mãi không đạt, hay quy trình đang chờ bạn duyệt, giờ thành một câu hỏi ở trang Nhiệm vụ và trên chuông. Bạn trả lời là việc chạy tiếp.
- **Nhắc hẹn và loop tạo trong chat với trợ lý chạy bằng đúng model và mức suy nghĩ của trợ lý đó.** Lượt kiểm chứng của loop vẫn dùng model việc nền. Cảm ơn @tunganh0990 (#1847).
- **ChatGPT biết các mức suy nghĩ ngay sau khi Javis khởi động lại**, không phải đợi mở trang Models.
- **Javis trên Windows không ngốn CPU khi cổng nhận kết nối lỗi liên tục.** Mỗi lần lỗi Javis đợi một chút rồi mới thử lại.

## en
### Fixed
- **Background jobs that need you now ask you instead of retrying in silence.** A workflow step that keeps failing its check, or a workflow waiting for your approval, becomes a question on the Tasks page and in the bell. Answer it and the job carries on.
- **Reminders and loops made in an assistant's chat run on that assistant's own model and thinking level.** A loop's check still runs on the background model. Thanks to @tunganh0990 (#1847).
- **ChatGPT knows its thinking levels right after Javis restarts**, without waiting for the Models page.
- **Javis on Windows no longer burns CPU when its port keeps failing to accept connections.** After each failure it waits a moment before trying again.
