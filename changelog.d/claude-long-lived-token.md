---
bump: minor
title: Claude Code connects with a long-lived token, one button on the Models page
---
## vi
### Thêm mới
- **Claude Code kết nối bằng token dài hạn, chỉ một cổng.** Thẻ Claude Code ở trang Models nay chỉ còn nút **Kết nối Claude**: Javis tự chạy `claude setup-token`, hiện link, bạn đăng nhập claude.ai và dán mã, xong là Claude Code chạy bằng token đó. Phiên đăng nhập kiểu cũ có thể hết hạn giữa chừng ("this login reached its time limit") và làm bot, việc nền dừng lại; token thì không bị đăng xuất giữa chừng. Có nút **Dán token** cho token tạo ở máy khác. Token được mã hoá khi lưu và không bao giờ gửi ra trình duyệt.
- **Nhắc trước khi token hết hạn.** Anthropic cho mỗi token dùng 1 năm. Thẻ hiện ngày hết hạn và số ngày còn lại; trước khoảng một tuần, chuông thông báo nhắc mỗi ngày một lần, bấm **Lấy token mới** là xong.

### Cải thiện
- **Bỏ lựa chọn "Chạy bằng" trên thẻ Claude Code.** Muốn trả theo lượt dùng bằng API key thì dùng thẻ **Anthropic (API)** riêng. Máy đang đăng nhập kiểu cũ vẫn chạy bình thường và có nút **Chuyển sang token dài hạn**; nút **Ngắt** xoá luôn token.
- **Mỗi tài khoản Claude phụ chạy đúng tài khoản của nó,** không mượn token của tài khoản 1.

## en
### Added
- **Claude Code connects with a long-lived token, one way in.** The Claude Code card on the Models page now has a single **Connect Claude** button: Javis runs `claude setup-token`, shows the link, you sign in to claude.ai and paste the code, and Claude Code runs on that token. The old sign-in could run out midway ("this login reached its time limit") and stop bots and background work; the token is never signed out midway. **Paste a token** takes one made on another machine. The token is stored encrypted and never sent to the browser.
- **A reminder before the token ends.** Anthropic lets each token run for a year. The card shows the expiry date and the days left; about a week before, the bell reminds you once a day, and **Get a new token** is all it takes.

### Improved
- **The "Runs on" choice is gone from the Claude Code card.** To pay per use with an API key, use the separate **Anthropic (API)** card. A machine still on the old sign-in keeps working and gets a **Switch to a long-lived token** button; **Disconnect** also forgets the token.
- **Each extra Claude account runs on its own account,** never on account 1's token.
