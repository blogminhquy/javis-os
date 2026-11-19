---
bump: minor
title: Tool search finds the right tool from everyday Vietnamese and English requests
---
## vi
### Cải thiện
- **Javis tìm đúng tool hơn hẳn khi có nhiều nguồn.** Câu hỏi đời thường như "doanh thu hôm nay trên POS", "lịch sử tin nhắn Zalo", "chi phí Google Ads" giờ ra đúng tool, kể cả khi mô tả tool viết tiếng Anh. Trên bộ 55 câu thử thật, tỉ lệ tìm trúng từ 20 lên 55.
- **Nêu tên nguồn là ra danh sách tool của nguồn đó**, và nhiều tài khoản cùng loại (ba shop POS, hai Zalo) được gộp một dòng, không còn chiếm chỗ của tool khác.
- **Gọi tool thiếu tiền tố hay gõ sai tên vẫn chạy** nếu chỉ có một tool khớp, nhiều tool khớp thì Javis nêu tên để chọn. Kết quả tìm cũng ngắn hơn để vẫn tiết kiệm token.

## en
### Improved
- **Javis finds the right tool far more often when many sources are connected.** Everyday requests such as "today's POS revenue", "Zalo message history" or "Google Ads cost" now reach the right tool, even when tool descriptions are in English. On 55 real test requests, hits rose from 20 to 55.
- **Naming a source lists its tools**, and several accounts of one kind (three POS shops, two Zalo accounts) share one line instead of crowding out other tools.
- **Calling a tool without its source prefix or with a typo still works** when only one tool matches; with several matches Javis names them to pick from. Search results are also shorter, so tokens stay low.
