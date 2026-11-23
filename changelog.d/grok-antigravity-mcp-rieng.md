---
bump: patch
title: Grok Build and Antigravity turns see the MCP servers added straight to them
---
## vi
### Sửa lỗi
- **Chat bằng Grok Build hay Antigravity không còn bỏ sót MCP anh tự thêm vào hai CLI đó.** Các MCP khai trong `~/.grok/config.toml` hoặc `~/.gemini/config/mcp_config.json` (ví dụ Composio, Notion gắn thẳng vào CLI) vốn gọi được, nhưng ô tìm tool và danh sách kết nối của Javis không nhắc tới, nên model trả lời là chưa có tool. Giờ cả hai đều nêu tên chúng và nói rõ là gọi thẳng, giống Codex và connector của tài khoản Claude.

## en
### Fixed
- **Grok Build and Antigravity chats no longer miss MCP servers you added straight to those CLIs.** Servers in `~/.grok/config.toml` or `~/.gemini/config/mcp_config.json` (Composio or Notion added to the CLI directly) could always be called, but Javis' tool search and connection list never named them, so the model said there was no tool. Both now name them and say to call them directly, like Codex and the Claude account connectors.
