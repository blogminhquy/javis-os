---
bump: patch
title: Cross review runs on the background model and the model picked on each card
---
## vi
### Sửa lỗi
- **Review chéo trên GitHub chạy bằng đúng model bạn đã chọn.** Trước đây nó gửi model rỗng, nên thẻ Groq rơi về `llama-3.3-70b-versatile`, model Groq đã tắt từ 16/08/2026, và lần review nào cũng báo 404 rồi bỏ qua. Giờ model việc nền review trước (nếu khác hãng với engine đã viết), các thẻ khác dùng model và mức suy nghĩ chọn trên thẻ. Khung chat ghi rõ tên model đã review.
- **Model mặc định của Groq đổi sang `openai/gpt-oss-120b`**, model Groq khuyên dùng thay cho `llama-3.3-70b-versatile`.

## en
### Fixed
- **GitHub cross review runs on the model you picked.** It used to send an empty model, so a Groq card fell back to `llama-3.3-70b-versatile`, which Groq shut down on 16/08/2026, and every review answered 404 and was skipped. The background model now reviews first (when it is from another vendor than the author), other cards use the model and reasoning level picked on the card, and the chat names the model that reviewed.
- **Groq's default model is now `openai/gpt-oss-120b`**, the replacement Groq names for `llama-3.3-70b-versatile`.
