---
bump: patch
title: Plan usage ring follows the real quota state
---
## vi
### Sửa lỗi
- **Vòng hạn mức hết đỏ ngay khi gói dùng lại được.** Trước đây anh chị đặt lại gói trên trang nhà cung cấp rồi mà vòng vẫn đỏ 100% và việc Javis tự làm vẫn nghỉ, cho tới giờ làm mới cũ.
- **Đọc được giờ mở lại có ghi cả năm.** Câu báo kiểu "try again at Nov 13th, 2026 3:32 PM" trước đây bị coi là không rõ lúc nào mở lại, nay hiện đúng giờ.
- **Việc nền bị từ chối vì hết lượt cũng làm vòng hạn mức đỏ.** Trước đây chỉ lượt chat mới ghi nhận, nên việc nền dùng cạn gói mà vòng vẫn xanh.

## en
### Fixed
- **The usage ring stops being red as soon as the plan works again.** Before, after you reset the plan on the provider's site the ring stayed red at 100% and Javis's own work stayed paused until the old reset time.
- **A reset time that includes the year is read.** A notice like "try again at Nov 13th, 2026 3:32 PM" used to count as "no reset time given"; the real time now shows.
- **Background work refused for quota turns the usage ring red too.** Only chat turns recorded it before, so background work could use up the plan while the ring stayed green.
