---
bump: minor
title: Javis can click and fill forms with a stored sign-in
---
## vi
### Thêm mới
- **Javis bấm nút và điền form được bằng cookie đã cất.** Trước đây trang Cookies chỉ cho Javis đọc trang. Giờ Javis nạp phiên đăng nhập vào trình duyệt (kết nối Playwright) rồi thao tác như bạn. Cần có kết nối Playwright ở trang Kết nối.
- **Cảnh báo rủi ro khi thêm cookie.** Form thêm cookie nói rõ Javis làm việc thật bằng tài khoản của bạn và rủi ro do bạn tự chịu, chi tiết nằm trong nút (i).
- **Mỗi thẻ có công tắc "Cho bấm và điền form".** Cookie cất từ trước mặc định vẫn chỉ đọc, bạn tự bật khi muốn. Tắt hoặc xoá thì Javis gỡ luôn phiên khỏi trình duyệt.

### Bảo mật
- **Chatbot trả lời khách không dùng được trình duyệt đã đăng nhập.** Từ lúc trình duyệt giữ một đăng nhập của bạn, chatbot khách mất kết nối trình duyệt đó.

## en
### Added
- **Javis can click and fill forms with a stored cookie.** The Cookies page used to let Javis read pages only. Now Javis puts the sign-in into the browser (the Playwright connection) and works on the page like you would. The Playwright connection must be added on the Connections page.
- **A risk warning when you add a cookie.** The add form says plainly that Javis acts for real with your account and that the risk is yours, with the detail behind the (i) button.
- **Each card has a "Let Javis click and fill forms" switch.** Cookies stored earlier stay read-only until you turn it on. Switching it off or deleting the cookie also removes the session from the browser.

### Security
- **Customer chatbots cannot use the signed-in browser.** Once the browser holds one of your sign-ins, customer chatbots lose that browser connection.
