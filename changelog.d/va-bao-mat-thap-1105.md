---
bump: patch
title: Low security fixes from the November 5 audit
---
## vi
### Bảo mật
- **Trang /health/loop giờ cần đăng nhập.** Trang này có thông tin lỗi và đường dẫn trên máy chủ. Riêng /health vẫn mở để kiểm tra máy còn sống.
- **Token API loại "chat" chỉ vào được phần trò chuyện**, không còn tạo, sửa hay xoá chatbot được nữa.
- **Khách gửi hai file trùng tên qua WhatsApp thì cả hai đều được giữ**, file sau không còn ghi đè file trước.
- **Đọc web và theo dõi trang kết nối đúng vào địa chỉ đã kiểm**, nên một tên miền đổi DNS giữa chừng không dẫn được vào mạng nội bộ.

## en
### Security
- **/health/loop now needs the login.** It shows error details and server paths. /health itself stays open as a liveness check.
- **A "chat" API token only reaches the chat routes**, and can no longer create, edit or delete chatbots.
- **Two customer files with the same name on WhatsApp are both kept**, the second no longer overwrites the first.
- **Web reading and page watching connect to the exact address that was checked**, so a domain that changes its DNS midway cannot lead into the private network.
