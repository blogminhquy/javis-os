---
bump: patch
title: Retry incomplete acceptance work without asking the owner
---
## vi
### Sửa lỗi
- Việc chưa đạt nghiệm thu được thử khắc phục với lý do và tiến độ đã lưu. Khi hết lượt thử hoặc không tiến triển, việc dừng với lỗi nội bộ thay vì tạo câu hỏi cho chủ.

## en
### Fixed
- Incomplete acceptance work retries with saved reasons and progress. Exhausted or stalled retries stop with an internal failure instead of creating an owner question.
