---
bump: patch
title: Startup check lists loaded packages instead of timing them
---
## vi
### Sửa lỗi
- **CI không còn đỏ oan vì phép đo tốc độ khởi động.** Test cũ bấm giờ lúc nạp server và đỏ ngẫu nhiên khi máy chạy chậm. Nay nó liệt kê các thư viện được nạp lúc khởi động: không còn phụ thuộc tốc độ máy, và khi có thư viện nặng lọt vào thì nó gọi đúng tên.

## en
### Fixed
- **CI no longer fails at random on the startup speed check.** The old test timed the server import and went red on slow runners. It now lists the libraries loaded at startup: no clock involved, and a heavy library that slips in is named.
