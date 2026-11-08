---
bump: patch
title: Zalo voice messages are heard again by Groq and OpenAI
---
## vi
### Sửa lỗi
- **Bot nghe được tin thoại Zalo.** Tin thoại Zalo là AAC thô, Groq và OpenAI từ chối nên bot báo "chưa nghe được". Giờ Javis nhận dạng định dạng theo nội dung file và tự đổi sang mp3 trước khi gửi, áp dụng cho mọi kênh.

## en
### Fixed
- **Bots hear Zalo voice messages.** A Zalo voice message is bare AAC, which Groq and OpenAI refuse, so the bot said it could not hear it. Javis now detects the format from the file's bytes and converts it to mp3 before sending, on every channel.
