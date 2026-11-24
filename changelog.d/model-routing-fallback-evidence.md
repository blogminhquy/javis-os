---
bump: patch
title: Record actual model execution and fallback evidence on background jobs
---
## vi
### Sửa lỗi
- **Ghi nhận chính xác model thực chạy và lý do dự phòng ở việc nền.** Khi một việc nền chuyển sang model dự phòng do hết lượt hoặc lỗi, bản ghi việc và dữ liệu trả về lưu đúng nhà cung cấp, mã model thực tế đã chạy, nhà cung cấp ban đầu và lý do chuyển dự phòng, đồng thời xóa các trường dự phòng cũ khi chạy lại thành công trực tiếp bằng model chính.

## en
### Fixed
- **Record actual model execution and fallback evidence for background jobs.** Background job records and card payloads now retain the actual provider, model, original provider, and fallback reason across execution, failure, and input-wait paths, and clear stale fallback fields on clean retries.
