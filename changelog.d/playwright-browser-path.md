---
bump: patch
title: The Playwright connection runs the browser Javis downloaded, whatever its version
---
## vi
### Sửa lỗi
- **Playwright không còn báo "chưa cài trình duyệt" sau khi Javis vừa tải xong.** Javis giờ chỉ thẳng cho Playwright file trình duyệt nó đã tải, nên hai bên lệch phiên bản cũng chạy được. Ai đã tự chọn trình duyệt riêng thì Javis giữ nguyên.

## en
### Fixed
- **Playwright no longer says "browser not installed" right after Javis downloaded one.** Javis now hands Playwright the exact browser file it downloaded, so the two can run on different versions. A browser you chose yourself is left alone.
