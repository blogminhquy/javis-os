---
bump: patch
title: A reply language you ask for stays for the whole chat
---
## vi
### Sửa lỗi
- **Bảo Javis "English pls" một lần là cả cuộc chat trả lời tiếng Anh.** Trước đây câu đó không được nhận, còn "reply in English" chỉ giữ đúng một lượt. Nay cuộc chat nhớ ngôn ngữ đã chọn tới khi bạn đổi hoặc than phiền về nó; "viết caption bằng tiếng Anh" vẫn chỉ là việc của lượt đó.
- **Claude Code và ChatGPT không còn quên ngôn ngữ giữa cuộc chat.** Ngôn ngữ đã ghim (trong chat hoặc ở Cài đặt) đi kèm từng tin nhắn, vì hai engine này giữ nguyên lời dặn của lượt đầu khi nối phiên.
- **Tin nhắn tiếng Anh kèm file đang mở hay file đính kèm không còn bị hiểu là tiếng Việt.** Luật ngôn ngữ viết lại bằng tiếng Anh, nói rõ ngôn ngữ bạn đã dặn (hồ sơ, bộ nhớ, trong chat) thắng, và đứng cuối lời dặn như thiết kế ban đầu.
- **Chế độ tiết kiệm token của engine API tôn trọng ngôn ngữ ghim ở Cài đặt**, và câu quá ngắn ("ok do 2") không còn bị ép theo ngôn ngữ giao diện.

## en
### Fixed
- **Tell Javis "English pls" once and the whole chat answers in English.** That phrase used to match nothing, and "reply in English" held for one turn only. The chat now keeps the language until you ask for another or complain about it; "write the caption in English" still only steers that turn.
- **Claude Code and ChatGPT no longer forget the language mid-chat.** A pinned language (from the chat or Settings) rides with each message, since both engines keep the first turn's instructions when they resume a thread.
- **An English message with an open or attached file is no longer read as Vietnamese.** The language rule is now written in English, says a language you stated (profile, memory, the chat) wins, and sits last in the prompt again.
- **Token saving on API engines honours the language pinned in Settings**, and a message too short to tell ("ok do 2") no longer follows the interface language.
