---
bump: patch
title: Qualified lazy tool calls never fall back to another account
---
## vi
### Sửa lỗi
- **Gọi tool kèm tên nguồn không còn tự nhảy sang tài khoản khác.** Khi gọi một tool có kèm nguồn đã tắt hoặc bị ẩn, Javis sẽ báo lỗi kèm gợi ý tên đúng thay vì tự động chạy sang tài khoản khác trùng tên tool; gọi tên ngắn không kèm nguồn vẫn tự khớp như cũ.

## en
### Fixed
- **Qualified tool calls no longer fall back to a different account.** Calling a tool with an explicit source prefix that is unavailable now returns an error with suggested names instead of silently running a same-named tool on another account; bare tool names without a prefix still auto-resolve as before.
