---
bump: patch
title: Sign-in stays alive while in use, and an expired one shows the sign-in screen
---
## vi
### Sửa lỗi
- **Ảnh trong chat không còn tự thành ô trống sau 30 ngày.** Trước đây phiên đăng nhập hết hạn đúng 30 ngày sau lần đăng nhập dù ngày nào cũng dùng, chat vẫn chạy nhưng ảnh và danh sách tải không được mà không báo gì. Giờ còn dùng là phiên tự gia hạn.
- **Phiên hết hạn giữa chừng thì hiện ngay màn đăng nhập** thay vì để trang hỏng lặng lẽ.

## en
### Fixed
- **Chat images no longer turn blank after 30 days.** A sign-in used to expire exactly 30 days after login however often it was used; chat kept working while images and lists silently failed. A session in use now renews itself.
- **A sign-in that expires mid-use brings up the sign-in screen** instead of leaving the page quietly broken.
