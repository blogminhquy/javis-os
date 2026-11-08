---
bump: minor
title: Zalo OA connects with Zalo's OAuth v4 grant instead of a pasted refresh token
---
## vi
### Thêm mới
- **Zalo OA cấp quyền theo OAuth v4.** Ở form Thêm kênh Zalo OA, dán App ID, App secret key, OA secret key rồi bấm Cấp quyền bằng Zalo: chọn OA, bấm Cho phép là Javis tự lưu kênh. Không cần lấy refresh token tay ở API Explorer nữa. Form hiện sẵn Callback URL để dán vào app Zalo một lần.
- **Cấp quyền lại một nút.** Refresh token chết thì mở Sửa kênh, bấm Cấp quyền lại bằng Zalo, Javis dùng khoá đã lưu và bot đang trực tự chạy lại.

## en
### Added
- **Zalo OA grants access with OAuth v4.** On Add channel, Zalo OA, paste the App ID, App secret key and OA secret key and click Grant access with Zalo: pick the OA, click Allow and Javis saves the channel by itself. No more copying a refresh token from API Explorer. The form shows the Callback URL to paste into the Zalo app once.
- **Grant again in one click.** When the refresh token dies, open Edit on the channel and click Grant access again with Zalo; Javis uses the saved keys and the bot on duty restarts.
