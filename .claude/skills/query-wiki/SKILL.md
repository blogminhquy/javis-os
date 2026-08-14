---
name: Query Wiki
description: "Khai thác tri thức trong Second Brain: tổng hợp, so sánh, giả thuyết. Trả lời có trích dẫn."
description_en: "Mine the knowledge held in the Second Brain: synthesis, comparison, hypotheses. Every answer carries citations."
group: AI
---

# QUERY - trả lời từ wiki (có citation, compounding)

## Khi nào dùng

Kích hoạt khi người dùng hỏi/khai thác tri thức trong Second Brain, vd "tổng hợp các
framework về X", "so sánh A vs B vs C", "wiki có gì về Y".

Năm kiểu khai thác: tổng hợp, so sánh, giả thuyết, liệt kê, trực quan hoá. Luôn trả lời
có trích dẫn và lưu lại kết quả giá trị.

1. Đọc `wiki/index.md` TRƯỚC để biết có trang nào.
2. Đọc các trang wiki liên quan (theo nhóm/tên); đọc trang được `[[link]]` tới nếu cần đủ context.
3. Thiếu -> đọc `sources/` tương ứng. Vẫn thiếu -> append 1 dòng vào `wiki/_open-questions.md`.
4. Trả lời có `[[citation]]` cho mọi khẳng định cụ thể. Nói rõ chỗ nào wiki chưa cover thay vì bịa.
5. Nếu câu trả lời có GIÁ TRỊ TÁI DÙNG (so sánh, phân tích, mapping mới) -> đề xuất lưu thành 1 trang wiki mới (compounding: khám phá cũng tích luỹ vào bộ não, không tan vào lịch sử chat).

7 dạng câu hỏi chất lượng cao: Tổng hợp (bảng so sánh) · So sánh 3+ (ma trận) · Giả thuyết (phân tích ảnh hưởng) · Gán nhãn/liệt kê · Trực quan hoá (canvas/sơ đồ) · Dịch/chuyển ngữ · Tự kiểm gap (append open-questions).
