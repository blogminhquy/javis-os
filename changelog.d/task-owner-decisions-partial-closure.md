---
bump: patch
title: Keep task failures internal and record honest partial closure
---
## vi
### Sửa lỗi
- QA, kiểm thử và recovery chưa đạt không còn tự biến thành câu hỏi cho chủ. Worker chỉ hỏi khi có quyết định riêng của chủ, câu hỏi cụ thể và các lựa chọn rõ ràng.
- Có thể đóng một việc PARTIAL qua thao tác owner hiện có, lưu tham chiếu/hash quyết định và giữ nguyên kết quả, chất lượng, artifact, lịch sử. Dependency dùng trạng thái kết thúc thực thi; không coi PARTIAL là quality PASS.
- Thông báo chờ xử lý giữ khóa chống trùng qua replay/restart; timer cũ không báo lại việc đã đóng hoặc đổi trạng thái. Thao tác gửi chưa rõ kết quả vẫn bị giữ dừng, không tự phát lại.

## en
### Fixed
- QA, test and recovery failures stay internal. A headless worker requests the owner only with an explicit owner-only decision, a concrete question and alternatives.
- The existing owner move action can record partial closure, preserving its decision reference/hash, results, quality, artifacts and history. Execution completion releases dependencies without declaring quality PASS.
- Pending notices retain deduplication keys across replay/restart; stale timers cannot notify a closed or reclassified job. Uncertain external writes remain held without automatic replay.
