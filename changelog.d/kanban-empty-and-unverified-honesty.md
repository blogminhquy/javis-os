---
bump: patch
title: Reject empty Kanban outputs and warn on unverified acceptance
---
## vi
### Sửa lỗi
- **Lượt chạy nền trả kết quả trống không còn được báo hoàn thành.** Nếu kết quả trả về rỗng (ngoài trường hợp đánh dấu im lặng có chủ đích), việc sẽ được gửi lại để tự sửa tối đa một vòng rồi tạm dừng chờ bạn kiểm tra thay vì báo xong.
- **Cảnh báo rõ khi kết quả chưa được kiểm chứng tự động.** Khi bộ kiểm tra gặp lỗi hoặc trả về dữ liệu không hợp lệ, thông báo kết quả và thẻ việc sẽ gắn biểu tượng cảnh báo cùng giải thích rõ để bạn tự rà lại.
- **Vẫn kiểm tra tiêu chí cố định khi bỏ qua bước chuẩn bị.** Các việc có sẵn điều kiện hoàn thành cố định luôn được đối chiếu đủ thay vì bị bỏ qua.

## en
### Fixed
- **Empty background run outputs no longer count as done.** When a non-silent run returns blank output, the job gets one bounded retry and then blocks for review instead of reporting completion.
- **Unverified acceptance results surface an explicit warning.** When the automatic checker fails or returns invalid output, the completion notice and task card switch to a warning and explain that the result was not verified.
- **Preset completion criteria still run without preparation.** Jobs created with fixed acceptance criteria are checked against them even when the preparation step did not run.
