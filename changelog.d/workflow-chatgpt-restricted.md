---
bump: minor
title: Restricted background workflow steps run on ChatGPT when the agent is set to ChatGPT
---
## vi
### Thêm mới
- **Agent chọn ChatGPT giờ chạy đúng bằng ChatGPT trong workflow nền giới hạn công cụ.** Trước đây các bước đó luôn chạy bằng Claude Code dù anh chị chọn ChatGPT. Bước chỉ được gọi đúng danh sách công cụ của nó, giữ mức quyền của việc, không có lệnh máy, web hay tác tử con.
- Máy chưa cài Codex thì bước đó vẫn chạy bằng Claude Code như trước, không báo lỗi.

## en
### Added
- **An agent set to ChatGPT now really runs on ChatGPT in restricted background workflows.** Those steps always ran on Claude Code, whatever you picked. The step can call only its own tool list, at the job's permission level, with no shell, web or sub-agents.
- Without Codex installed the step still runs on Claude Code as before, with no error.
