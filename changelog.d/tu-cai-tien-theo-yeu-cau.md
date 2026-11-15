---
bump: minor
title: On your request, Javis and its assistants improve themselves, the brain and Javis's own code, with undo
---
## vi
### Thêm mới
- **Bảo cải tiến là làm được, có hoàn tác.** Nói "cải tiến chính em" hay "sửa lại skill này", trợ lý tự sửa vai trò, hướng dẫn, skill, model của nó, trợ lý khác, skill, workflow, vòng lặp, bộ nhớ. Mỗi lần sửa có mã và sao lưu, nói "hoàn tác #12" là về bản cũ.
- **Javis sửa được chính mã nguồn của nó.** Khi GitHub đã kết nối với repo javis-os, trợ lý tự gắn repo vào chat, sửa trên nhánh riêng; Javis tự kiểm, mở PR và merge khi CI xanh.
- **Tự cập nhật lên bản vừa phát hành.** Bảo "cập nhật đi", Javis chờ lượt chat xong rồi chạy đúng quy trình của nút Cập nhật, bản mới lỗi thì tự lùi.

### Cải thiện
- **Chỉ bạn ra lệnh mới sửa được.** Lượt tự thức của Auto và bot nói với khách chỉ được đề xuất. Các câu dặn cũ mâu thuẫn trong prompt đã được thay cho khớp.

## en
### Added
- **Ask for an improvement and it happens, with undo.** Say "improve yourself" or "rework this skill": the assistant changes its own role, instructions, skills and model, other assistants, skills, workflows, loops and memory. Every change gets an id and a backup; "undo #12" puts it back.
- **Javis can change its own source code.** With GitHub connected to the javis-os repo, the assistant attaches the repo to the chat and works on its own branch; Javis checks, opens a PR and merges on green CI.
- **It updates itself to the release.** Say "update now": Javis waits for the chat turn to end, runs exactly what the Update button runs, and rolls back if the new version breaks.

### Improved
- **Only you can order it.** Auto's own wake-ups and customer-facing bots may only suggest. Old prompt lines that contradicted this now match.
