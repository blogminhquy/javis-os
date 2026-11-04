---
bump: patch
title: Scheduled jobs on Codex can hand work to a Team again
---
## vi
### Sửa lỗi
- **Lịch nền chạy bằng ChatGPT (Codex) giao được việc cho Nhóm.** Trước đây một nhắc hẹn hay việc Kanban có bộ não nền là Codex gọi `javis_team` mà không mang danh tính lượt, nên bị chặn với câu "lượt không có danh tính" và nhóm không bao giờ dậy làm việc. Giờ lượt nền mang khoá lượt tới hub như lúc chat, nên nhóm nhận việc đúng giờ.

## en
### Fixed
- **Scheduled jobs running on ChatGPT (Codex) can hand work to a Team.** A reminder or Kanban job whose background brain was Codex called `javis_team` without the turn identity, so it was refused with "the turn has no identity" and the team never started. The background turn now carries the turn key to the hub, as a chat turn does, so the team picks up the job on time.
