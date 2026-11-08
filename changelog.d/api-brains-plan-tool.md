---
bump: minor
title: The API brains keep a task plan too
---
## vi
### Thêm mới
- **Bảy bộ não chạy bằng API key cũng có thẻ "Kế hoạch" trong khung chat.** OpenRouter, OpenAI, Anthropic API, Gemini, Groq, DeepSeek và Ollama giờ có công cụ `javis_plan`: gặp việc từ 3 bước trở lên, model lập danh sách việc và đánh dấu từng mục khi xong, giống Claude Code, Codex và Grok Build. Câu hỏi thường không dùng tới nó.
- Tốn thêm khoảng 200 token mỗi lượt cho phần mô tả công cụ (đa số hãng có cache), cộng một vòng công cụ ngắn mỗi lần cập nhật danh sách. Muốn tắt thì vào menu "+" ở ô nhập, mục "Kế hoạch việc dài (bộ não API)". Chỉ khung chat của chủ có công cụ này, bot trả lời khách và việc nền thì không.

## en
### Added
- **The seven API-key brains show the "Plan" card in the chat too.** OpenRouter, OpenAI, Anthropic API, Gemini, Groq, DeepSeek and Ollama get a `javis_plan` tool: for a job of three steps or more the model lists the steps and ticks each one off, like Claude Code, Codex and Grok Build. Ordinary questions do not use it.
- It costs about 200 tokens a request for the tool description (cached by most providers), plus one short tool round each time the list is updated. Switch it off in the composer "+" menu, "Plan long jobs (API brains)". Only the owner's chat gets it, not customer bots or background jobs.
