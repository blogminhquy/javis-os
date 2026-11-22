---
bump: minor
title: Extra Claude accounts sign in with a long-lived token too
---
## vi
### Thêm mới
- **Tài khoản Claude phụ cũng dùng token dài hạn.** Nút **Thêm tài khoản** và **Đăng nhập lại** trên thẻ Claude Code nay lấy token 1 năm cho riêng tài khoản đó (link rồi dán mã, như tài khoản 1), nên tài khoản phụ không còn bị đăng xuất giữa chừng. Token lưu mã hoá trong thư mục của tài khoản, Gỡ tài khoản là xoá luôn. Mỗi lượt chạy trên tài khoản nào thì dùng đúng token của tài khoản đó.
- **Dòng tài khoản hiện ngày hết hạn token,** và trước một tuần chuông nhắc mỗi ngày một lần, kèm tên tài khoản.

### Cải thiện
- **Số ngày còn lại của token làm tròn lên:** token vừa lấy hiện "còn 365 ngày" thay vì 364.

## en
### Added
- **Extra Claude accounts use a long-lived token too.** **Add an account** and **Sign in again** on the Claude Code card now get a one-year token for that account alone (a link, then the code, as for account 1), so an extra account is no longer signed out midway. The token is kept encrypted in the account's folder and removing the account removes it. A turn on an account runs on that account's own token.
- **An account's row shows when its token ends,** and a week before, the bell reminds you once a day, naming the account.

### Improved
- **A token's days left are rounded up:** a fresh token reads "365 days left", not 364.
