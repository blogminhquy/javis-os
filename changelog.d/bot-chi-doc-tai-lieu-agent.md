---
bump: minor
title: Bots read only their Agent's documents
---
## vi
### Bảo mật
- **Chatbot chỉ đọc tài liệu ghim ở mục Tài liệu của Agent nó dùng**, cộng thư mục `rieng-theo-nhom/` và Google Docs gắn từ Agent. Trước đây bot coi mọi ghi chú trong brain là tài liệu, nên bot chạy trên brain chính có thể trích ghi chú riêng của chủ cho khách.
- **Cần làm sau khi cập nhật:** mở Agent của từng bot, ghim các file bảng giá, chính sách, hướng dẫn mà bot cần đọc. Bot chưa ghim file nào sẽ trả lời theo vai trò của Agent, không có tài liệu để tra.

## en
### Security
- **A bot reads only the documents in its Agent's Documents section**, plus the `rieng-theo-nhom/` folder and the Google files linked from the Agent. Before, every note of the brain counted as a document, so a bot running on the owner's main brain could quote private notes to customers.
- **To do after updating:** open each bot's Agent and add the price lists, policies and guides the bot should read. A bot with no listed file answers from its Agent's role, with no document to look up.
