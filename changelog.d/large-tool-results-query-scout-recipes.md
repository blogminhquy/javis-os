---
bump: minor
title: Large tool results are stored whole and queried by code
---
## vi
### Thêm mới
- **Kết quả tool lớn không còn bị cắt mất phần giữa.** Javis cất bản đầy đủ, đưa cho model phần gọn kèm mã tham chiếu, và model đọc lại đúng phần nó cần. Báo cáo hết thiếu đơn, lại tốn ít token hơn trên mọi bộ não.
- **Tính bằng code, không nhẩm.** Tool `javis_query` tự lật hết các trang rồi cộng, đếm, xếp hạng bằng SQL chỉ đọc. Model lớn hay nhỏ đều ra cùng một con số.
- **Trinh sát bằng model nền.** Việc đọc nhiều nguồn có thể giao cho model việc nền (`javis_scout`), chỉ kết luận quay về khung chat. Trinh sát chỉ đọc, không gửi hay tạo gì.
- **Việc định kỳ nhớ cách lấy số.** Sau hai lần chạy giống nhau ở hai ngày khác nhau, Javis tự lấy sẵn dữ liệu cho lần sau. Chưa chắc về ngày tháng thì chạy như cũ.

### Cải thiện
- **Tìm tool gọn hơn**, và mục Đề xuất ở trang Mức dùng cho biết kết quả tool đã giữ được bao nhiêu ngoài hội thoại.

## en
### Added
- **Large tool results no longer lose their middle.** Javis stores the full copy, hands the model a compact view with a reference, and the model reads back exactly what it needs. Reports stop missing orders and cost fewer tokens on every brain.
- **Computed by code, not by eye.** The `javis_query` tool pages through a source by itself, then sums, counts and ranks with read-only SQL. A large or a small model gets the same number.
- **A scout on the background model.** A read across several sources can go to the background model (`javis_scout`); only its findings return to the chat. A scout reads, it never sends or creates.
- **Recurring jobs remember how to get their numbers.** After the same run on two different days, Javis fetches the data itself next time. When the dates are not certain, the job runs as before.

### Improved
- **Tool search answers are smaller**, and Suggestions on the Usage page says how much of the tool results stayed out of the conversation.
