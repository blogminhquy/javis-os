---
bump: patch
title: Codex turns see the MCP servers added straight to Codex
---
## vi
### Sửa lỗi
- **Chat bằng Codex không còn bỏ sót MCP anh tự thêm vào Codex.** Các MCP khai trong `~/.codex/config.toml` (ví dụ Composio, Notion gắn thẳng vào Codex) vốn gọi được, nhưng ô tìm tool và danh sách kết nối của Javis không nhắc tới, nên model trả lời là chưa có tool. Giờ cả hai đều nêu tên chúng và chỉ cách gọi thẳng, giống connector của tài khoản Claude.

## en
### Fixed
- **Codex chats no longer miss MCP servers you added straight to Codex.** Servers in `~/.codex/config.toml` (Composio or Notion added to Codex directly) could always be called, but Javis' tool search and connection list never named them, so the model said there was no tool. Both now name them and say how to call them directly, like the Claude account connectors.
