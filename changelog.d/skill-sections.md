---
bump: minor
title: Long menu-style skills load only the parts a request needs
---
## vi
### Cải thiện
- **Skill dài nạp có chọn lọc, Javis chọn trước khi nạp.** Với skill kiểu thực đơn như trình tạo agent/loop/plugin, Javis chỉ nạp phần yêu cầu cần cùng mọi mục luật, nhẹ hơn khoảng 53-67%. Không chắc là nạp cả skill như cũ, và skill dạng quy trình liền mạch luôn nạp đủ.
- **Học từ cách dùng.** Phần nào model hay phải lấy thêm thì lần sau Javis nạp sẵn. Bật thử cho khoảng 10% phiên chat trước, tắt theo mức Tắt.

## en
### Improved
- **Long skills load selectively, chosen by Javis before loading.** For a menu-style skill such as the agent/loop/plugin builder, Javis loads only the part a request needs plus every rules section, about 53-67% lighter. When unsure it loads the whole skill as before, and a skill that is one procedure always loads whole.
- **Learns from use.** A part the model keeps fetching is loaded up front next time. It starts on about 10% of chat sessions and follows the Off level.
