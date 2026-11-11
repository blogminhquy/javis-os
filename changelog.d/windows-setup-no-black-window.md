---
bump: minor
title: Windows setup shows its progress inside the wizard and can no longer hang
---
## vi
### Cải thiện
- **Cài trên Windows không còn cửa sổ đen riêng.** Tiến trình cài hiện ngay trong cửa sổ Setup: dòng "Bước 2/5", thanh chạy liên tục và một khung ghi từng việc đang làm.
- **Lỗi hiện ngay trong Setup.** Bước nào hỏng thì Setup nói rõ thiếu gì kèm đường dẫn nhật ký, trang cuối không còn báo "đã cài xong" khi chưa xong.

### Sửa lỗi
- **Bộ cài Windows hết đứng im.** Trước đây lỗi nằm chờ bấm Enter trong cửa sổ đen bị che, hoặc một trình cài phụ (winget, npm, Grok, Antigravity) không chịu kết thúc là cả bộ cài treo. Giờ mỗi bước có giới hạn thời gian, quá giờ thì bỏ qua và đi tiếp.
- **Tải Git, Python, Node nhanh hơn nhiều** trên máy không có winget.

## en
### Improved
- **No separate black window when installing on Windows.** The progress shows inside the Setup window: a "Step 2 of 5" line, a bar that keeps moving and a box listing what is being done.
- **Errors show inside Setup.** A failed step says what is missing and where the log is, and the last page no longer claims the install finished when it did not.

### Fixed
- **The Windows installer no longer freezes.** An error used to wait for Enter in a black window hidden behind the wizard, and one helper installer (winget, npm, Grok, Antigravity) that never ended hung everything. Each step now has a time limit, then Setup moves on.
- **Git, Python and Node download much faster** on PCs without winget.
