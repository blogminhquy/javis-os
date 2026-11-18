---
bump: minor
title: Background jobs on an API key carry a short rule set
---
## vi
### Cải thiện
- **Việc chạy nền trên bộ não dùng khóa API gửi ít token hơn khoảng 60%.** Việc Kanban, việc lặp và nhắc hẹn có làm việc mang bộ luật việc nền ngắn thay cho toàn bộ bộ luật chat, ở mỗi lần gọi công cụ. Mọi luật về hành động được giữ nguyên: làm đúng việc trong mức quyền, không bịa số, báo kết quả về đúng người giao, không hứa suông, không tự tạo thêm việc, plugin mới luôn tắt. Thử bằng model thật trên 7 loại việc nền mẫu, kết quả ngang bản đầy đủ.
- **Gói thuê bao không đổi.** Claude Code, ChatGPT, Grok, Antigravity vẫn mang bộ luật đầy đủ. Bật thử cho khoảng 10% việc chạy nền, tắt theo mức Tắt.

## en
### Improved
- **Background jobs on an API-key engine send about 60% fewer fixed tokens.** Kanban jobs, loops and reminders that do work carry a short background rule set instead of the whole chat rule set in every tool call. Every rule about acting stays: do exactly the job within its permission level, never invent numbers, report to whoever assigned it, no empty promises, no jobs created unasked, new plugins always off. Tested with a real model on 7 sample background jobs: results on par with the full rules.
- **Subscription engines are unchanged.** Claude Code, ChatGPT, Grok and Antigravity keep the full rules. It starts on about 10% of background jobs and follows the Off level.
