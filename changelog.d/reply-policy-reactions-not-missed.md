---
bump: patch
title: Group bots stop learning to answer reactions and stickers
---
## vi
### Sửa lỗi
- **Bot nhóm không còn tự học sai rằng phải trả lời lượt thả cảm xúc.** Chủ thả tim vào tin của khách, hay một người thả hai cảm xúc liền nhau, từng bị tính là bot "bỏ lỡ" tin trước đó, khiến bot nói nhiều dần lên ở đúng những nhóm nó im là đúng.
- Chữ "up" trong câu thường như "up ảnh giúp em" và "hỏi lại" trong một câu dặn dài không còn bị hiểu là khách hỏi lại vì không ai trả lời.
- Nhãn bot tự suy ra từ tin của chủ không còn được tính nặng như lời chủ dạy trực tiếp.

## en
### Fixed
- **A group bot no longer teaches itself to answer reactions.** An owner's heart on a customer's message, or two reactions in a row from one person, used to count as the bot having missed the earlier message, which made it talk more in exactly the groups where staying quiet was right.
- "up" inside an ordinary sentence and "hỏi lại" inside a long instruction are no longer read as a customer asking again.
- A label the bot inferred from an owner's message no longer weighs as much as something the owner taught it directly.
