---
bump: patch
title: Webhook idle wait no longer spins for ever on Python 3.12
---
## vi
### Sửa lỗi
- **CI không còn thỉnh thoảng treo 20 phút ở bài kiểm tra Webhook.** Hàm chờ Webhook rảnh việc có lúc rơi vào vòng lặp vô hạn trên Python 3.12 (bản mà CI và Docker đang dùng), nên một lượt kiểm tra đứng im tới khi bị dừng. Lỗi xảy ra khoảng 6 lần trong 830 lượt gần đây.
- Phần chờ của mục Sự cố có cùng lỗi và được sửa cùng lúc. Người dùng không thấy gì khác trên màn hình.

## en
### Fixed
- **CI no longer hangs for 20 minutes now and then in the Webhook test.** The wait for the Webhook worker to go idle could fall into an endless loop on Python 3.12 (the version CI and the Docker image use), so a test run stood still until it was stopped. It happened about 6 times in the last 830 runs.
- The wait of the Incident desk had the same fault and is fixed with it. Nothing changes on screen.
