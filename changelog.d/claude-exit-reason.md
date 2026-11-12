---
bump: patch
title: A Claude Code turn that dies at startup says why
---
## vi
### Sửa lỗi
- **Lỗi "SDK engine: ProcessError... Check stderr output for details" giờ nói rõ lý do.** Khi Claude Code thoát trước khi trả lời, khung chat hiện đúng câu nó in ra thay vì một dòng không biết làm gì tiếp.
- **Ba ca hay gặp có luôn cách xử lý:** Javis chạy bằng tài khoản root, cấu hình nguồn dữ liệu (MCP) hỏng, và Claude Code trên máy quá cũ.

## en
### Fixed
- **The "SDK engine: ProcessError... Check stderr output for details" error now gives the reason.** When Claude Code exits before answering, the chat shows what it printed instead of a line nobody can act on.
- **Three common cases come with the fix:** Javis running as root, a broken data source (MCP) configuration, and an outdated Claude Code on the machine.
