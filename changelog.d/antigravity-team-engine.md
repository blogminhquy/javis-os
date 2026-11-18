---
bump: minor
title: Antigravity CLI support in team chat and gated team jobs
---
## vi
### Thêm mới
- **Cộng sự dùng Antigravity nay tham gia họp nhóm và làm việc nhóm bình thường.** Các lượt thảo luận nhóm chạy ở chế độ chỉ chữ với thư mục làm việc trống và móc chặn công cụ theo từng lượt, không cần đổi model của cộng sự sang nhà cung cấp khác.
- **Hỗ trợ duyệt công cụ ngoài phạm vi cho Antigravity trong việc nhóm ở mức 'cần duyệt'.** Mọi hành động của Antigravity đi qua cổng kiểm tra trước khi chạy, tạm dừng xin phép chủ nhóm đối với hành động ngoài thư mục làm việc và chỉ cho chạy một lần sau khi được duyệt.

## en
### Added
- **Assistants configured with Antigravity can now participate in team chats and gated team work.** Discussion turns run strictly text-only inside an isolated per-turn working folder and HOME with tool-denying hooks, without switching the assistant to another provider.
- **Approval-gated tool execution for Antigravity in team jobs.** Antigravity actions pass through the team approval gate before running, pausing for one-shot owner approval on actions outside the workspace.
