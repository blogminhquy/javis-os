---
bump: patch
title: Workflow agents without their own model run on the main model
---
## vi
### Sửa lỗi
- **Agent trong quy trình chưa chọn model riêng giờ chạy bằng model chính.** Trước đây bước đó luôn chạy bằng Claude, dù trang Models đang chọn não khác. Agent đã chọn model riêng vẫn giữ nguyên lựa chọn đó.

## en
### Fixed
- **Workflow agents with no model of their own now run on the main model.** Before, such a step always ran on Claude whatever brain was picked on the Models page. An agent with its own model keeps it.
