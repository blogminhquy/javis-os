---
bump: patch
title: Team steps on ChatGPT (Codex) run when Codex has its own MCP servers
---
## vi
### Sửa lỗi
- **Nhóm ở quyền "cần duyệt" chạy được trên ChatGPT (Codex) dù máy có MCP riêng của Codex.** Trước đây chỉ cần `~/.codex/config.toml` có một MCP ngoài Javis (ví dụ `node_repl`) là mọi bước Làm bị từ chối và bảo đổi sang Claude Code. Giờ Javis tắt riêng các MCP đó cho đúng lượt chạy, file cấu hình của bạn giữ nguyên, giống cách workflow vẫn làm.
- **Lượt chỉ chữ của nhóm trên Codex hết báo "code-mode host is disabled".** Codex bản mới vẫn đưa model công cụ chạy mã dù đã tắt phần host, model gọi rồi báo lên nhóm là chưa đọc được cấu hình. Giờ lượt chỉ chữ tắt hẳn code mode.

## en
### Fixed
- **Teams that need approvals run on ChatGPT (Codex) even when Codex has MCP servers of its own.** One server outside Javis in `~/.codex/config.toml` (such as `node_repl`) used to refuse every Work step and send the owner to Claude Code. Javis now switches those servers off for that run only and leaves your config file as it is, as workflows already did.
- **Text-only team turns on Codex no longer report "code-mode host is disabled".** Newer Codex still offered the model its run-code tool with only the host off, so the model called it and told the team it could not read the config. Text-only turns now switch code mode off entirely.
