---
bump: patch
title: Gemini 4 takes the Effort level, and its cost estimate is right
---
## vi
### Sửa lỗi
- **Mức nghĩ (Effort) giờ có tác dụng với Gemini 4.** Chạy Gemini 4 Hydrogen, Argon hay Carbon bằng API key Gemini thì trước đây chọn mức nghĩ nào cũng như không, model luôn chạy theo mức mặc định của nó. Giờ mức bạn chọn được gửi đi, và mọi đời Gemini sau này cũng tự được nhận.
- **Trang Mức dùng tính đúng tiền Gemini mới.** Gemini 4 trước đây bị tính theo giá Gemini cũ nên hiện rẻ hơn thực tế nhiều lần, còn Gemini 3.5 Flash-Lite lại bị tính theo giá bản Pro. Giờ mỗi model có giá riêng.

## en
### Fixed
- **The Effort level now works on Gemini 4.** On a Gemini API key, Gemini 4 Hydrogen, Argon and Carbon ignored the Effort you picked and always ran at their own default. Your level is now sent, and later Gemini generations are recognised on their own.
- **The Usage page prices the new Gemini models correctly.** Gemini 4 used the old Gemini price and showed several times cheaper than it is, while Gemini 3.5 Flash-Lite was priced as Pro. Each model now has its own price.
