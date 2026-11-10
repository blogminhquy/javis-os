---
bump: patch
title: Workflow steps run at the reasoning level their assistant set
---
## vi
### Sửa lỗi
- **Bước quy trình nay chạy đúng mức suy luận của trợ lý.** Trước đây mức suy luận đặt cho một trợ lý chỉ có tác dụng khi chat và trong nhóm; bước quy trình, kể cả việc Kanban giao theo quy trình, luôn chạy ở mức mặc định của model. Trợ lý chưa đặt mức thì bước vẫn chạy như cũ.

## en
### Fixed
- **A workflow step now runs at its assistant's reasoning level.** The level set on an assistant only applied to its chat and team turns; a workflow step, including a Kanban job routed to a workflow, always ran at the model's default. A step whose assistant set no level runs as before.
