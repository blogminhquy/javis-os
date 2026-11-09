---
bump: minor
title: Bots read only their Agent's documents, and background work stops freezing the app
---
## vi
### Bảo mật
- **Chatbot chỉ đọc tài liệu ghim ở mục Tài liệu của Agent nó dùng**, cộng thư mục `rieng-theo-nhom/` và Google Docs gắn từ Agent. Trước đây bot coi mọi ghi chú trong brain là tài liệu, nên có thể trích ghi chú riêng của chủ cho khách.
- **Cần làm sau khi cập nhật:** mở Agent của từng bot và ghim các file bảng giá, chính sách, hướng dẫn mà bot cần đọc. Bot chưa ghim file nào chỉ trả lời theo vai trò của Agent.

### Sửa lỗi
- **Chatbot tra tài liệu, lượt học tự động và nhắc việc không còn làm cả app đứng vài giây.** Các việc này giờ chạy ở luồng phụ và không còn quét cả brain.
- **Trang Cộng sự không còn chờ khoá dữ liệu Cộng hưởng**, và danh mục kết nối không còn kiểm tra lại ổ đĩa ở mọi lần gọi.

## en
### Security
- **A bot reads only the documents in its Agent's Documents section**, plus the `rieng-theo-nhom/` folder and the Google files linked from the Agent. Before, every note of the brain counted as a document, so a bot could quote the owner's private notes to customers.
- **To do after updating:** open each bot's Agent and add the price lists, policies and guides the bot should read. A bot with no listed file answers from its Agent's role only.

### Fixed
- **Bot document lookups, auto learning and reminders no longer freeze the app for seconds.** They run on worker threads and no longer walk the whole brain.
- **The Partners page no longer waits on the Resonance data lock**, and the connection catalog is no longer re-checked on disk at every call.
