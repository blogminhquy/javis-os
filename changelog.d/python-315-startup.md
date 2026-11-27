---
bump: patch
title: Javis starts on Python 3.15 again, and a failed update says why
---
## vi
### Sửa lỗi
- **Javis lại chạy được trên Windows dùng Python 3.15.** Từ bản 0.642.3, máy Windows chạy Python 3.15 chết ngay lúc khởi động, nên nút Cập nhật tự lùi về bản cũ. Bản vá giữ cổng mở trên Windows giờ nhận đúng tham số mới của Python 3.15, và gặp một bản Python lạ hơn nữa thì tự đứng ngoài, server vẫn chạy bình thường.
- **Máy nào đã vá tay theo hướng dẫn cũng cập nhật bình thường.** Nếu trình cập nhật báo xung đột ở `server/accept_guard.py`, bỏ sửa đổi riêng ở file đó rồi bấm Cập nhật lại.

### Cải thiện
- **Cập nhật hỏng thì nói rõ vì sao.** Bản mới không khởi động được thì trình cập nhật đọc log của chính lần khởi động đó trước khi lùi về, ghi các dòng cuối vào update.log và hiện dòng lỗi ngay trên màn hình Cập nhật, thay vì chỉ báo "Bản mới lỗi".

## en
### Fixed
- **Javis runs on Windows with Python 3.15 again.** Since 0.642.3, Windows machines on Python 3.15 died at startup, so the Update button rolled back to the old version. The patch that keeps the port open on Windows now takes Python 3.15's new argument, and on a Python it does not know yet it stands aside so the server still starts.
- **Machines patched by hand update normally.** If the updater reports a conflict in `server/accept_guard.py`, drop the local change to that file and press Update again.

### Improved
- **A failed update says why.** When the new version does not start, the updater reads that start's own log before rolling back, keeps its last lines in update.log and shows the error line on the Update screen, instead of only "the new version failed".
