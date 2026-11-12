---
bump: patch
title: Dictation keeps the language you spoke instead of translating it into Vietnamese
---
## vi
### Sửa lỗi
- **Đọc tiếng Anh vào mic không còn bị tự dịch sang tiếng Việt.** Sau khi bấm dừng, Javis nhờ mô hình viết lại câu cho đúng chính tả, và mô hình đôi khi trả về bản dịch tiếng Việt thay vì câu tiếng Anh đã nói (hay gặp ở câu dài, lần đọc thứ hai). Giờ câu nói bằng tiếng nào thì giữ đúng tiếng đó. Nếu mô hình vẫn dịch, Javis bỏ bản dịch và giữ nguyên lời đã nghe. Áp dụng cho mic ở chat chính, Nhóm, Hội thoại và trình sửa ghi chú.

## en
### Fixed
- **Dictating in English no longer comes back translated into Vietnamese.** After you press stop, Javis asks a model to tidy the sentence, and the model sometimes returned a Vietnamese translation instead of the English you spoke (mostly on longer sentences, such as a second recording). A sentence now stays in the language it was spoken in. If the model still translates, Javis drops the translation and keeps the words as heard. This covers the mic in the main chat, Teams, Conversations and the note editor.
