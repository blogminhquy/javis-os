---
bump: minor
title: The dictation bubble fixes misheard words as you speak, AI names come out right, Android stops losing words
---
## vi
### Thêm mới
- **Bong bóng chép lời sửa chữ ngay khi bạn đang nói (máy tính).** Bong bóng mờ hiện chữ nghe được, rồi đổi sang bản đã sửa vài khoảnh khắc sau: Javis dùng Groq nếu bạn đã gắn khoá, không thì dùng model nền. Dừng ghi là ô chat nhận đúng bản đã sửa. Server không trả lời thì chữ giữ nguyên như nghe được.

### Sửa lỗi
- **Javis nghe đúng tên các sản phẩm AI hơn.** "Groq", "Grok", "Claude", "ChatGPT", "Gemini", "OpenRouter"... ra đúng chính tả, và nói "Groq" không còn bị đổi thành "Grok".
- **"Jarvis OS" giờ ra đúng "Javis OS".**
- **Chép lời trên Android không còn mất chữ.** Bản trước bỏ mất câu ngắn nói sau một câu dài (nói "tôi về rồi" rồi "tôi" thì mất chữ "tôi"). Giờ chữ được dựng lại từ toàn bộ những gì máy nghe, mà vẫn không lặp kiểu "tôi tôi bị".

## en
### Added
- **The dictation bubble fixes words as you speak (computer).** The faded bubble shows what was heard, then the fixed text a moment later: Javis uses Groq when you have added its key, otherwise the background model. Stop recording and the box gets the fixed text. If the server does not answer, the words stay as heard.

### Fixed
- **Javis hears AI product names more accurately.** "Groq", "Grok", "Claude", "ChatGPT", "Gemini", "OpenRouter"... come out spelled right, and "Groq" is no longer changed into "Grok".
- **"Jarvis OS" now comes out as "Javis OS".**
- **Dictation on Android no longer loses words.** The previous version dropped a short sentence said right after a longer one that began with the same word. The text is now rebuilt from everything the phone heard, still without repeats like "I I am".
