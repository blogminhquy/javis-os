---
bump: patch
title: Wrong reply labels learned before the reaction fix are cleaned up once
---
## vi
### Sửa lỗi
- **Bot nhóm tự gỡ các nhãn "bỏ lỡ" sai đã học trước bản 0.530.7.** Bản đó chặn nhãn sai mới, còn nhãn cũ vẫn nằm trong kho và tiếp tục đẩy bot nói nhiều. Lần mở kho đầu tiên sau khi cập nhật, Javis gỡ nhãn "bỏ lỡ" gắn trên lượt thả cảm xúc, trả lại ngưỡng cho các nhóm bị kéo lệch, và thôi coi nhãn tự suy ra từ tin của chủ là lời chủ dạy.
- Lời chủ dạy thật (bấm 👍/👎, bảo bot im, dạy trong chat) giữ nguyên.

## en
### Fixed
- **A group bot drops the wrong "missed" labels it learned before 0.530.7.** That version stopped new wrong labels, but the old ones stayed in the store and kept pushing the bot to talk. The first time the store opens after the update, Javis removes "missed" labels put on reactions, gives the affected groups their threshold back, and stops treating labels it inferred from an owner's message as something the owner taught.
- What the owner really taught (a thumb, telling the bot to stop, a lesson in chat) is kept.
