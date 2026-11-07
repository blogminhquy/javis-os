---
bump: patch
title: Antigravity CLI turns no longer stop at 15 minutes
---
## vi
### Sửa lỗi
- **Antigravity CLI không còn tự dừng ở phút thứ 15.** Việc nặng, nhiều bước giờ chạy tới khi xong, giống Claude Code và Codex. Nút Dừng vẫn cắt được bất cứ lúc nào.
- Muốn đặt lại trần thì dùng biến môi trường `JAVIS_AGY_TIMEOUT` (giây). Mức chỉ đọc vẫn giữ lưới 15 phút vì nó không tự duyệt tool.

## en
### Fixed
- **Antigravity CLI no longer stops at minute 15.** Heavy, many-step work now runs until done, like Claude Code and Codex. The Stop button still ends a turn at any moment.
- To set a cap again, use the `JAVIS_AGY_TIMEOUT` environment variable (seconds). The read-only mode keeps a 15-minute net because it does not auto-approve tools.
