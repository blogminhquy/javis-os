---
bump: minor
title: Add an opt-in rendered login vault adapter foundation
---
## vi
### Thêm mới
- Thêm cầu nối thử nghiệm để render hai trang kho AMIS bằng phiên Cookies phía server. Mặc định tắt; cần duyệt endpoint đọc và kiểm thử trên môi trường staging trước khi dùng dữ liệu thật.
### Bảo mật
- Cầu nối chặn request chưa được duyệt, mạng nội bộ, chuyển hướng và thao tác ghi; phiên trình duyệt riêng được đóng sau mỗi lượt.

## en
### Added
- Add an experimental server-side Cookies adapter for rendering two AMIS inventory pages. Disabled by default; read endpoints require review and staging validation before live use.
### Security
- Block unreviewed requests, private networks, redirects and writes; close the isolated browser session after each use.
