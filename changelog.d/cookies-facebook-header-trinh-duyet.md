---
bump: patch
title: Signed-in pages like Facebook load with saved cookies again
---
## vi
### Sửa lỗi
- **Thẻ cookie Facebook đọc được trang trở lại.** Khi mở trang bằng cookie trên trang Cookies, Javis giờ gửi kèm các header điều hướng như trình duyệt thật (`Sec-Fetch-*`, `Accept`, `Upgrade-Insecure-Requests`). Trước đó Facebook trả lỗi 400 trước cả khi xét tới cookie, nên thẻ còn sống vẫn báo "lần gần nhất không tải được".

## en
### Fixed
- **Facebook cookie cards load pages again.** When a page is opened with a card from the Cookies page, Javis now sends the navigation headers a real browser sends (`Sec-Fetch-*`, `Accept`, `Upgrade-Insecure-Requests`). Before, Facebook answered 400 before it even read the cookies, so a live sign-in still showed "last load failed".
