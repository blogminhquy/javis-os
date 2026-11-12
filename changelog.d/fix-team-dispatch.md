---
bump: patch
title: Fix Team model routing and gated MCP isolation
---

## vi

### Sửa lỗi

- Team không còn chặn oan Codex chỉ vì máy có MCP riêng, đồng thời vẫn tắt các MCP đó trong bước cần duyệt.
- Model Codex cũ không còn được gửi thẳng tới tài khoản ChatGPT nếu đã có model hợp lệ trong catalog.
- File Markdown Team gửi mở thẳng trong trình sửa để đọc và duyệt.
- File Markdown trong thẻ xin duyệt, nghiệm thu, cơ hội và thông báo hệ thống cũng mở ngay trong trình sửa.
- Link Markdown trong trang Team có handler riêng nên không phụ thuộc vào cầu nối click của trang chat.
- Đường dẫn tuyệt đối do agent gửi được rút về đường dẫn tương đối của brain trước khi mở.

## en

### Fixed

- Team no longer rejects Codex just because the machine has personal MCP servers, while still disabling them for gated steps.
- Stale Codex model ids are no longer sent to a ChatGPT account when a valid catalog model is available.
- Markdown files sent in Team open directly in the editor for review.
- Markdown files in approval, acceptance, opportunity, and system cards also open directly in the editor.
- Markdown links on the Team page have a dedicated handler instead of relying on the main chat click bridge.
- Absolute paths sent by an agent are reduced to the current brain's relative path before opening.
