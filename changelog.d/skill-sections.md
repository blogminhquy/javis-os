---
bump: minor
title: Long menu-style skills load only the parts a request needs
---
## vi
### Cải thiện
- **Skill dài nạp có chọn lọc, Javis chọn trước khi nạp.** Với skill kiểu thực đơn như trình tạo agent/loop/plugin, Javis chỉ nạp phần yêu cầu cần cùng mọi mục luật (và phần nó dặn tạo trước, như workflow kéo theo mẫu agent), nhẹ hơn khoảng 47-63%. Đo bằng model thật trên 7 loại yêu cầu, câu trả lời đủ ý như khi nạp cả skill.
- **Mọi ngôn ngữ như nhau.** Cách chọn không dựa vào tiếng Việt hay tiếng Anh: tách chữ được mọi hệ chữ (kể cả Trung, Nhật, Hàn, Thái), nhận cả từ có đuôi biến đổi (tiếng Nga, Đức, Thổ, Hàn), và tự tìm từ thừa ngay trong skill. Người hỏi bằng ngôn ngữ khác skill thì model tóm việc bằng ngôn ngữ của skill để Javis chọn đúng phần. Không chắc là nạp cả skill như cũ, và skill dạng quy trình liền mạch luôn nạp đủ.
- **Học từ cách dùng.** Phần nào model hay phải lấy thêm thì lần sau Javis nạp sẵn. Bật thử cho khoảng 10% phiên chat trước, tắt theo mức Tắt.

## en
### Improved
- **Long skills load selectively, chosen by Javis before loading.** For a menu-style skill such as the agent/loop/plugin builder, Javis loads only the part a request needs plus every rules section (and any part it says to create first, such as the agent template for a workflow), about 47-63% lighter. Measured with a real model on 7 kinds of request, answers as complete as with the whole skill.
- **Every language alike.** The choice does not lean on Vietnamese or English: it reads every script (Chinese, Japanese, Korean and Thai included), matches words with inflected endings (Russian, German, Turkish, Korean), and finds filler words from the skill itself. When someone asks in another language than the skill, the model sums up the task in the skill's language so Javis picks the right part. When unsure it loads the whole skill as before, and a skill that is one procedure always loads whole.
- **Learns from use.** A part the model keeps fetching is loaded up front next time. It starts on about 10% of chat sessions and follows the Off level.
