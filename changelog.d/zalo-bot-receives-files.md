---
bump: minor
title: Zalo Bot reads the files people send, or says the file did not arrive
---
## vi
### Thêm mới
- **Bot Zalo chính thức nhận được file.** Khi Zalo chuyển file cho bot, Javis tải về và đọc luôn PDF, Word, Excel và file chữ, gửi kèm câu hỏi là trả lời theo file.
- **Không còn im lặng.** Zalo chưa có loại tin file riêng cho bot, nên khi Zalo không kèm nội dung thì bot nói thẳng là chưa nhận được và nhờ gửi ảnh chụp hoặc dán chữ. Trước đây bot im.

### Bảo mật
- **Bot của chủ không tải gì của người lạ.** Ảnh, tin thoại và file chỉ được tải về khi chat đã được bấm Cho phép.

## en
### Added
- **The official Zalo bot receives files.** When Zalo passes a file to the bot, Javis downloads it and reads PDF, Word, Excel and plain-text files, so a question sent with it is answered from the file.
- **No more silence.** Zalo has no file message type for bots yet, so when Zalo includes no content the bot says plainly that it did not arrive and asks for a screenshot or pasted text. Before, the bot stayed silent.

### Security
- **The owner's bot fetches nothing from strangers.** Photos, voice messages and files are downloaded only for a chat that has been allowed.
