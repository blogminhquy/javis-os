---
bump: patch
title: GitHub cross review no longer picks a plan that can never run it
---
## vi
### Sửa lỗi
- **Review chéo khi Javis làm việc trên GitHub không còn báo "không chạy được" mỗi lần.** Javis từng chọn gói ChatGPT để review code do Claude viết, nhưng bước review chỉ cho chạy engine không có công cụ đọc ghi file, nên gói ChatGPT (cũng như Grok Build, Antigravity) luôn bị chặn. Giờ Javis chỉ chọn Claude hoặc một nhà dùng API key khác họ, bỏ qua thẻ đang hết lượt, và một reviewer hỏng thì thử reviewer kế tiếp.
- **Bỏ qua review thì nói rõ vì sao**, kèm lý do lỗi, và khi không có engine nào review được thì chat chỉ cách bật: thêm API key của một nhà khác họ (OpenAI, Gemini, DeepSeek, OpenRouter...).

## en
### Fixed
- **GitHub cross review no longer says "did not run" on every job.** Javis used to pick the ChatGPT plan to review code Claude wrote, but the review only runs engines without file tools, so the ChatGPT plan (like Grok Build and Antigravity) was always refused. Javis now picks Claude or an API-key provider of another family, skips cards out of quota, and tries the next reviewer when one fails.
- **A skipped review says why**, with the error, and when no engine can review the chat says how to enable it: add an API key of another family (OpenAI, Gemini, DeepSeek, OpenRouter...).
