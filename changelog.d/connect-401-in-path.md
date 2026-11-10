---
bump: patch
title: A connector that cannot start is no longer reported as an expired sign-in
---
## vi
### Sửa lỗi
- **Trình kết nối không khởi động được không còn bị báo nhầm là "hết phiên đăng nhập".** Javis nhận lỗi đăng nhập bằng cách tìm số 401 trong câu lỗi, nên khi đường dẫn cài đặt tình cờ có chứa 401, lỗi "không tìm thấy file" hiện thành lời mời bấm Kết nối lại. Giờ 401 (và 502, 503, 504) chỉ được tính khi đứng riêng như một mã lỗi.

## en
### Fixed
- **A connector that cannot start is no longer reported as "sign-in expired".** Javis recognised a sign-in error by looking for 401 in the error text, so when the install path happened to contain 401, a "file not found" error was shown as a prompt to Reconnect. 401 (and 502, 503, 504) now count only when they stand alone as a status code.
