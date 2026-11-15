---
bump: minor
title: Javis works in any language and stops pulling English chats back to Vietnamese
---
## vi
### Thêm mới
- **Javis làm việc bằng mọi ngôn ngữ, giống Claude hay ChatGPT.** Mặc định Javis trả lời đúng thứ tiếng bạn viết. Ô "Javis trả lời bằng" ở Cài đặt và ngôn ngữ của chatbot nay chọn được 35 thứ tiếng (Nhật, Hàn, Trung, Pháp, Đức, Tây Ban Nha, Thái...), và câu trả lời tiếng Nhật, Hàn, Trung, Thái được đọc bằng giọng bản xứ.

### Sửa lỗi
- **Javis không còn trả lời tiếng Việt khi bạn đang chat tiếng Anh.** Lời dặn ngôn ngữ viết lại bằng tiếng Anh, nói rõ ngôn ngữ bạn đã dặn (hồ sơ, bộ nhớ, trong chat) thắng, và phần tiếng Việt xung quanh không phải gợi ý.
- **Việc chạy nền (Kanban, nhắc hẹn, loop) không còn luôn báo bằng tiếng Việt.** Nó theo ngôn ngữ chọn ở Cài đặt, hoặc ngôn ngữ của chính đầu việc.
- **Tin nhắn tiếng Anh kèm file không còn bị hiểu là tiếng Việt**, và chế độ tiết kiệm token tôn trọng ngôn ngữ chọn ở Cài đặt.

## en
### Added
- **Javis works in any language, like Claude or ChatGPT.** By default it answers in the language you write. The "Javis replies in" picker in Settings and a chatbot's language now offer 35 languages (Japanese, Korean, Chinese, French, German, Spanish, Thai...), and replies in Japanese, Korean, Chinese and Thai are read aloud by a native voice.

### Fixed
- **Javis no longer answers in Vietnamese while you chat in English.** The language rule is now written in English, says a language you stated (profile, memory, the chat) wins, and that the Vietnamese around it is no hint.
- **Background work (Kanban, reminders, loops) no longer always reports in Vietnamese.** It follows the language chosen in Settings, or the task's own language.
- **An English message with an attached file is no longer read as Vietnamese**, and token saving honours the language chosen in Settings.
