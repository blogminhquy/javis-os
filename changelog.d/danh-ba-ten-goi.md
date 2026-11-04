---
bump: minor
title: Plan names for ChatGPT and Grok come from a catalog updated without a release
---
## vi
### Thêm mới
- **Tên gói ChatGPT và Grok tự cập nhật.** CLI của OpenAI chỉ gửi mã gói, và mã không khớp tên đang bán (mã "prolite" là gói 100 đô). Nay Javis tra tên trong danh bạ tên gói đặt ở kho javis-store, tải về 6 giờ một lần, chạy ngầm, không làm chậm trang nào. Nhà cung cấp đổi tên thì chỉ cần sửa danh bạ, mọi máy thấy tên mới mà không cần bản cập nhật. Claude vẫn ưu tiên tên lấy thẳng từ Anthropic; mã chưa có trong danh bạ thì Javis viết gọn mã như trước.

## en
### Added
- **ChatGPT and Grok plan names update on their own.** OpenAI's CLI sends only a plan code, and the code does not match the name on sale (the code "prolite" is the $100 plan). Javis now looks the name up in a plan-name catalog kept in the javis-store repo, fetched every 6 hours in the background without slowing any page. When a vendor renames a plan, only the catalog changes and every machine shows the new name without an update. Claude still prefers the name Anthropic itself sends; a code missing from the catalog is tidied as before.
