---
bump: patch
title: Preserve lazy tool arguments on compatible gateways
---
## vi
### Sửa lỗi
- Công cụ được tìm qua Hub có thêm cách nhận tham số bằng chuỗi JSON, tránh mất các trường dữ liệu trên một số cổng tương thích. Tham số sai định dạng bị từ chối trước khi gọi công cụ; quyền truy cập vẫn giữ nguyên.

## en
### Fixed
- Lazy Hub tools accept JSON-encoded arguments so compatible gateways can preserve dynamic fields. Invalid arguments are rejected before dispatch, with existing permission checks preserved.
