---
bump: minor
title: Phone dictation records for the model with a live wave, and stop returns the text fast
---
## vi
### Sửa lỗi
- **Mic chép lời trên điện thoại ghi âm thật ngay từ lần bấm đầu.** Javis nhớ máy đang có mô hình nghe (ChatGPT, Groq, OpenAI, Gemini), nên điện thoại ghi âm rồi để mô hình đó chép, có sóng âm thật, giống app ChatGPT.
- **Sóng âm luôn chạy khi điện thoại đang nghe.** Kể cả lúc chỉ dùng bộ nhận giọng của trình duyệt. Sóng đứng yên nghĩa là máy không nghe được gì, và câu báo chỉ cách sửa.

### Cải thiện
- **Bấm dừng là có chữ gần như ngay.** Chữ do mô hình nghe chép đã có dấu câu, nên Javis không còn chờ Claude Code hay Codex viết lại nữa, chỉ sửa nhanh khi có model trả lời trong khoảng một giây.
- **Khoá Gemini cũng nghe được mic chép lời,** và bộ não Gemini nghe bằng chính model của nó.

## en
### Fixed
- **Phone dictation records for real from the first press.** Javis remembers that the machine has a model that listens (ChatGPT, Groq, OpenAI, Gemini), so the phone records and lets that model transcribe, with a real wave, like the ChatGPT app.
- **The wave always moves while the phone listens.** Even on the browser's own recognizer. A wave that stays still means nothing is heard, and the note says how to fix it.

### Improved
- **Stop gives the text back almost at once.** Text a speech model heard is already punctuated, so Javis no longer waits for Claude Code or Codex to rewrite it, and only polishes it when a model answers in about a second.
- **A Gemini key now hears the dictation mic too,** and a Gemini main brain listens with its own model.
