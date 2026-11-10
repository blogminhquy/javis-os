---
bump: patch
title: Chatbots move to the next ChatGPT account when one runs out of usage
---
## vi
### Sửa lỗi
- **Chatbot dùng gói ChatGPT nay tự chuyển tài khoản khi hết lượt.** Trước đây bot riêng luôn gọi bằng tài khoản 1, bỏ qua thứ tự tài khoản ở trang Models, nên tài khoản 1 hết lượt là bot báo lỗi 429 dù tài khoản khác còn dùng được.
- Bot chỉ đổi tài khoản khi chưa nói chữ nào và chưa gọi công cụ nào, nên khách không nhận tin trùng.

## en
### Fixed
- **Chatbots on a ChatGPT plan now move to the next account when one runs out.** A dedicated bot always called with account 1 and ignored the account order on the Models page, so it failed with a 429 while another account still had usage.
- A bot only switches accounts before it has said anything or called any tool, so customers never get a duplicate message.
