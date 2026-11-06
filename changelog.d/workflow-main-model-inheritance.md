---
bump: patch
title: Native workflows inherit the selected main model and agent reasoning
---
## vi
### Sửa lỗi
- Quy trình tương tác dùng model chính khi trợ lý không ghim model, giữ model riêng đã ghim và truyền mức suy luận của từng trợ lý. Nhà cung cấp không khả dụng báo lỗi thay vì âm thầm đổi đường chạy; giới hạn công cụ của quy trình nền được giữ nguyên.

## en
### Fixed
- Interactive workflows inherit the main model for unpinned agents, preserve explicit model pins, and apply each agent's reasoning level. Unavailable providers fail explicitly rather than silently rerouting; background workflow tool isolation is unchanged.
