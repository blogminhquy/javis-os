---
bump: patch
title: Chat no longer stuck on "Lost the connection" after one failed message or an expired sign-in
---
## vi
### Sửa lỗi
- **Khung chat không còn kẹt ở "Mất kết nối tới máy chủ" hàng giờ.** Trước đây một tin máy chủ xử lý lỗi làm đứt kết nối, trang nối lại rồi gửi lại đúng tin đó, lại đứt, lặp mãi, khởi động lại máy chủ cũng không hết. Nay máy chủ báo lỗi ngay dưới tin đó và kết nối vẫn chạy.
- **Một tin gửi 3 lần không được nhận thì trả về ô nhập**, không gửi lại vô hạn nữa.
- **Phiên đăng nhập hết hạn thì hiện màn đăng nhập**, thay vì báo mất kết nối mãi và mọi danh sách về 0.
- **Brain đặt trên Google Drive, OneDrive đỡ làm đứng máy chủ:** phần quét thư mục đầu và cuối mỗi lượt chat chạy riêng, không chặn kết nối nữa.

## en
### Fixed
- **The chat no longer sits on "Lost the connection to the server" for hours.** A message the server failed on used to drop the connection, the page reconnected and sent the same message again, which dropped it again, forever, even across server restarts. Now the server shows the error under that message and the connection stays up.
- **A message sent 3 times without being taken goes back to the input box** instead of being resent forever.
- **An expired sign-in shows the sign-in screen** instead of "reconnecting" forever with every list at 0.
- **A brain on Google Drive or OneDrive freezes the server less:** the folder scans at the start and end of each chat turn run on their own and no longer block the connection.
