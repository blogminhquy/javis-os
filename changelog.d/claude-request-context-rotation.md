---
bump: patch
title: Avoid unnecessary Claude thread rotation
---
## vi
### Sửa lỗi
- Hội thoại Claude ít bị mở luồng mới không cần thiết khi một lượt dùng nhiều công cụ, giúp giữ ngữ cảnh và tiến trình ấm.

## en
### Fixed
- Claude conversations no longer open new threads unnecessarily when a turn uses many tools, helping keep context and the process warm.
