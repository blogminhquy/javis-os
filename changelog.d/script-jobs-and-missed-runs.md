---
bump: minor
title: Javis sets up script jobs from chat, keeps whole results and counts skipped runs
---
## vi
### Thêm mới
- **Nhờ Javis đặt lịch chạy script ngay trong chat.** Ví dụ "mỗi phút chạy check_shop.py": job chạy thẳng script, không gọi model nên rẻ, và chạy được mỗi phút.

### Cải thiện
- **Kết quả của lịch được lưu đủ, không còn cắt ở 2.000 ký tự.** Lần chạy sau vẫn chỉ đọc phần đầu cho gọn, nhưng giờ biết rõ là đã bị cắt.
- **Lịch lặp bị lỡ lượt thì trang Nhiệm vụ ghi "lỡ N lần".** Trước đây khi một lượt chạy trễ hay chạy lâu, các lượt kế bị bỏ qua mà không ai biết.

## en
### Added
- **Ask Javis in chat to run a script on a schedule.** For example "run check_shop.py every minute": the job runs the script directly with no model, so it is cheap and can run every minute.

### Improved
- **A scheduled job keeps its whole result, no longer cut at 2,000 characters.** The next run still reads only the start, but now knows it was cut.
- **A repeating job that skipped runs shows "N missed" on the Tasks page.** Before, when one run was late or long, the next ones were skipped and nobody knew.
