---
bump: minor
title: Phone notifications learn what is worth a buzz, with a daily limit and a digest
---
## vi
### Thêm mới
- **Thông báo tự học từ cách bạn dùng.** Mỗi thông báo trên điện thoại được ghi lại là bạn bấm mở hay gạt bỏ. Loại nào bạn bỏ qua 5 lần liền, hoặc mở dưới 20%, Javis Core tự thôi cho rung và báo một dòng trong chat của nó. Hoàn tác được ở Bộ lọc của chuông. Tin khẩn không bao giờ bị tắt kiểu này.
- **Giới hạn số lần rung mỗi ngày**, mặc định 8, chỉnh trong Bộ lọc (5, 8, 12, 20 hoặc không giới hạn). Quá mức thì tin không khẩn chờ bản tin, tin khẩn vẫn rung.
- **Bản tin gộp lúc 11:30 và 17:30.** Các tin đáng xem nhưng không gấp được gom thành một lần rung, ví dụ "5 tin đáng xem trong chuông: Kết quả việc 3, Gợi ý của trợ lý 2". Tắt được trong Bộ lọc.
- **Bộ lọc của chuông có số liệu 7 ngày:** rung bao nhiêu lần, bạn mở bao nhiêu phần trăm, loại tin ít được mở nhất.

### Cải thiện
- **Thông báo hai dòng có ích hơn.** Dòng một là kết quả kèm con số, dòng hai là việc bạn cần làm, không có việc thì để trống. Không còn đoạn báo cáo bị cắt ngang ở dòng hai.
- **Câu trả lời chat mang tên cuộc chat thay cho chữ "Javis"**, dòng hai là câu kết luận chứ không phải câu mở đầu. Mỗi cuộc chat chỉ rung một lần trong 10 phút, và có nhóm "Câu trả lời chat" riêng trong Bộ lọc để hạ mức hoặc tắt.
- **Tin khẩn phải có lý do:** lỗi cần sửa, tiền, khách, câu hỏi chờ bạn, hoặc hạn chót. Không có lý do thì hạ xuống mức đáng chú ý. Việc nào khai khẩn quá nửa số lần chạy thì mất quyền khẩn.

## en
### Added
- **Notifications learn from how you use them.** Every phone notification records whether you tapped or swiped it away. A kind you ignored 5 times in a row, or opened less than 20% of the time, stops buzzing, and Javis Core says so in one line in its chat. Undo it in the bell's filter. An urgent notice is never silenced this way.
- **A daily limit on buzzes**, 8 by default, set in the filter (5, 8, 12, 20 or no limit). Past it, what is not urgent waits for the digest; urgent still buzzes.
- **A digest at 11:30 and 17:30.** Notices worth a look but not urgent come as one buzz, for example "5 notices worth a look in the bell: Job results 3, Assistant suggestions 2". It can be turned off in the filter.
- **The bell's filter shows the last 7 days:** how many buzzes, the share you opened, the kinds opened least.

### Improved
- **Two notification lines that say something.** The first is the result with its number, the second is what you should do, or nothing. No more report cut off mid-sentence on the second line.
- **A chat answer is titled with its chat instead of "Javis"**, and its second line is the conclusion, not the opening. Each chat buzzes at most once in 10 minutes, and "Chat answers" has its own group in the filter to lower or turn off.
- **Urgent needs a reason:** an error to fix, money, a customer, a question waiting for you, or a deadline. Without one it is lowered to important. A job that claims urgent on more than half its runs loses it.
