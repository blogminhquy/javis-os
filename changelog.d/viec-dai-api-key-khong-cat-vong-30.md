---
bump: minor
title: Long background work on an API key runs to the end, with a terminal
---
## vi
### Sửa lỗi
- **Việc nền chạy bằng API key không còn dừng ở vòng 30.** Task, loop, workflow, team dùng OpenRouter, OpenAI, Anthropic API, Gemini, Groq, DeepSeek hay Ollama giờ có 500 vòng công cụ mỗi lượt như khung chat, nên điền cả trăm dòng Google Sheet hay dựng video chạy được tới hết thay vì báo "đã chạy hết 30 vòng" rồi bỏ dở.
### Thêm mới
- **Việc nền Toàn quyền chạy bằng API key có terminal thật.** Task, nhắc hẹn hay workflow ở mức Toàn quyền giờ chạy được lệnh máy trong brain (ffmpeg, python, script dựng video...) và vẫn tìm, đọc được web, đúng như khi chạy bằng Claude Code. Việc chạy lâu thì để chạy nền, xong Javis báo về khung chat đã giao việc hoặc Javis Core. Mức Tự động, Gợi ý và loop bị cô lập vẫn không có lệnh máy.
### Cải thiện
- Trần vòng việc của bạn lên 500 (trước là 150 ở khung chat, 30 ở việc nền), đặt `JAVIS_MAX_TOOL_ROUNDS_CODING=0` là không giới hạn. Bot nói chuyện với khách vẫn giữ 30.
- Phanh chống kẹt thông minh hơn: chờ một việc đang chạy (hỏi tiến độ dựng video) không còn bị cắt ở lần thứ 5 khi kết quả vẫn đổi, còn model xoay vòng A-B-A-B mà không tiến triển thì bị dừng sớm.
- Lượt dài không còn tràn ngữ cảnh của model: kết quả công cụ cũ được rút gọn khi vượt ngân sách, kết quả mới nhất giữ nguyên. Chỉnh bằng `JAVIS_TOOL_LOOP_BUDGET_CHARS`.

## en
### Fixed
- **Background work on an API key no longer stops at round 30.** Tasks, loops, workflows and teams on OpenRouter, OpenAI, Anthropic API, Gemini, Groq, DeepSeek or Ollama now get 500 tool rounds per turn like chats do, so filling a hundred Google Sheet rows or building a video runs to the end instead of reporting "all 30 rounds were used" and giving up.
### Added
- **Full-access background work on an API key gets a real terminal.** Tasks, reminders and workflows at Full access can now run commands in the brain (ffmpeg, python, video-building scripts...) and still search and read the web, the same as on Claude Code. Long commands run in the background and Javis reports back to the chat that asked, or to Javis Core, when they finish. Auto, Suggest and isolated loops still get no shell.
### Improved
- The ceiling for your own work is now 500 rounds (was 150 in chats, 30 in background work); set `JAVIS_MAX_TOOL_ROUNDS_CODING=0` for no limit. Bots talking to customers stay at 30.
- A smarter brake against stuck models: waiting on a running job (polling a video render) is no longer cut on the 5th call while the result keeps changing, and a model cycling A-B-A-B without progress is stopped early.
- Long turns no longer overflow the model's context: older tool results are trimmed past a budget while the newest stay whole. Tune with `JAVIS_TOOL_LOOP_BUDGET_CHARS`.
