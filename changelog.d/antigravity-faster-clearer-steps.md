---
bump: patch
title: Antigravity answers sooner and shows what each step does
---
## vi
### Cải thiện
- **Antigravity trả lời sớm hơn vài giây mỗi lượt.** Câu trả lời chốt ngay khi model nói xong, không còn đợi Antigravity tự tắt thêm 2 đến 3 giây; với model đã ghi sẵn mức nghĩ trong tên (như `-high`), Javis không chèn thêm câu ép nghĩ, chữ đầu về nhanh gần gấp đôi.
- **Khối tiến trình của Antigravity ghi rõ từng bước:** "Chạy lệnh: git status", "Đọc file: wiki/a.md", tên công cụ thật thay cho `call_mcp_tool`, và bước nào xong thì thôi quay.
- **Chữ hiện dần ở Telegram và bot chuyên trách** khi dùng Antigravity hoặc Grok, thay vì đợi hết lượt mới hiện một lần.

## en
### Improved
- **Antigravity answers a few seconds sooner every turn.** The answer is final as soon as the model is done, without waiting 2 to 3 more seconds for Antigravity to shut down; a model with its depth in its name (such as `-high`) no longer gets Javis's extra "think it through" line, so the first word comes nearly twice as fast.
- **Antigravity's progress block says what each step does:** "Run command: git status", "Read file: wiki/a.md", the real tool name instead of `call_mcp_tool`, and a finished step stops spinning.
- **Text streams in on Telegram and dedicated bots** with Antigravity or Grok, instead of appearing all at once at the end of the turn.
