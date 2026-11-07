---
bump: minor
title: Async chat turns over the API (POST /chat/jobs)
---
## vi
### Thêm mới
- **Gọi Javis qua API không cần giữ kết nối chờ.** Gửi `POST /chat/jobs` là nhận ngay mã job, lượt chat chạy nền, lát sau hỏi `GET /chat/jobs/{mã}` để lấy câu trả lời. Hợp cho backend chạy trên serverless, và rớt mạng giữa chừng cũng không mất kết quả.
- **Job nào của token nấy.** Token khác không đọc được, mỗi token chạy tối đa 4 job cùng lúc, mỗi phiên một job. Kết quả giữ 24 giờ.

## en
### Added
- **Call Javis over the API without holding a connection open.** `POST /chat/jobs` answers at once with a job id, the turn runs in the background, and `GET /chat/jobs/{id}` returns the answer later. Good for serverless backends, and a dropped connection no longer loses the result.
- **Each job belongs to the token that started it.** Other tokens cannot read it, each token runs at most 4 jobs at once, one per session. Results are kept for 24 hours.
