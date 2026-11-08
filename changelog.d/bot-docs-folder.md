---
bump: minor
title: A chatbot can be limited to one documents folder of its brain
---
## vi
### Thêm mới
- **Bot trả lời khách giờ đọc được đúng một thư mục tài liệu.** Ở form bot, mục Nâng cao có ô "Thư mục tài liệu bot được đọc", ví dụ `bot-sale/HN/tai-lieu`. Bot chỉ tra, đọc và gửi ảnh từ thư mục đó cùng các thư mục con, nên nhiều bot chạy chung một brain mà mỗi bot chỉ biết phần của mình, không thấy báo cáo nội bộ hay tài liệu của bot khác. Để trống thì bot đọc cả brain như trước.
- Thư mục ghi sai, không có thật hoặc trỏ ra ngoài brain thì bot không đọc tài liệu nào, chứ không mở rộng ra cả brain. File Agent và trí nhớ của bot vẫn nằm ở brain như cũ.

## en
### Added
- **A customer-facing bot can read just one documents folder.** The bot form's Advanced section has a "Documents folder the bot may read" field, e.g. `sales/branch-1/docs`. The bot searches, reads and sends images only from that folder and its subfolders, so several bots can share one brain while each knows only its own part, with no internal reports or other bots' documents. Leave it blank and the bot reads the whole brain as before.
- A wrong or missing folder, or one pointing outside the brain, gives the bot no documents at all; it never widens to the whole brain. The bot's Agent file and memory stay in the brain as before.
