---
bump: patch
title: The Profile page reaches the model on shortcut answers too
---
## vi
### Sửa lỗi
- **Quy ước ở trang Hồ sơ giờ có tác dụng cả với câu trả lời đi đường tắt.** Bản 0.546.2 đã đưa hồ sơ vào các mức tiết kiệm, nhưng còn sót: lời chào, lời cảm ơn (ở mọi mức) và câu hỏi đơn giản ở mức Siêu tiết kiệm vẫn được trả lời mà không có hồ sơ, nên Javis có thể xưng hô sai ngay ở câu chào đầu tiên.
- Câu trả lời tổng hợp từ dữ liệu vừa đọc (trên bộ não dùng API key) cũng theo hồ sơ.
- Hồ sơ trống thì không có gì thay đổi. Hồ sơ dài nhất (4.000 ký tự) làm một lượt đi đường tắt nặng thêm khoảng 1.400 token.

## en
### Fixed
- **Rules on the Profile page now apply to shortcut answers too.** 0.546.2 brought the profile to the saving levels, but one gap was left: a greeting or a thank-you (at every level) and a simple question at the Max saving level were still answered without it, so Javis could get your form of address wrong on the very first hello.
- Answers written from data Javis has just read (on API-key brains) follow the profile as well.
- An empty profile changes nothing. The longest profile (4,000 characters) adds about 1,400 tokens to a shortcut turn.
