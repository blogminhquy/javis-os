---
bump: minor
title: Allow restricting MCP connections or tools to live owner turns
---
## vi
### Bảo mật
- **Hỗ trợ giới hạn kết nối hoặc từng tool MCP chỉ cho lượt chat trực tiếp của chủ máy.** Các kết nối đặt `owner_only` hoặc `owner_only_tools` được ẩn khỏi bot khách hàng, lượt nhóm và việc nền ở cả cache tìm kiếm lẫn kiểm tra lúc gọi, tránh lộ dữ liệu vận hành nội bộ qua kênh ngoài.

## en
### Security
- **MCP connections and individual tools can now be scoped to live owner turns.** Marking a connection `owner_only` or listing sensitive names in `owner_only_tools` keeps those tools hidden and blocked from customer bots, background jobs, and team turns across discovery caches and call guards.
