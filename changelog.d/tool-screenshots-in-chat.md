---
bump: patch
title: Screenshots taken by a tool now show in the chat
---
## vi
### Sửa lỗi
- **Ảnh chụp màn hình của Playwright hiện ngay trong khung chat.** Trước đây khi Javis chụp màn hình một trang bằng Playwright, ảnh bị đổi thành một chuỗi ký tự dài gửi cho model, nên bạn không thấy gì trong khung chat. Giờ ảnh được lưu vào bộ não ở `attachments/tool-images/` và Javis nhúng nó vào câu trả lời để bạn xem trước. Ảnh do công cụ khác trả về (biểu đồ, thiết kế) cũng được xử lý giống vậy.

## en
### Fixed
- **Playwright screenshots show right in the chat.** When Javis took a screenshot of a page with Playwright, the image reached the model as a long string of characters and nothing appeared in the chat. The image is now saved in the brain under `attachments/tool-images/` and Javis embeds it in its reply so you can preview it. Images returned by other tools (charts, designs) are handled the same way.
