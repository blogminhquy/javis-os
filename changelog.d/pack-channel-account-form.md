---
bump: minor
title: Pack channels get a logo, an account form and a duplicate warning
---
## vi
### Thêm mới
- **Kênh của gói có logo riêng.** Gói khai `logo_svg` là kênh hiện đúng logo ở trang Chatbot và Hội thoại. Logo được lọc sạch, chỉ giữ hình vẽ, bỏ script và liên kết ngoài.
- **Form thêm tài khoản theo khai báo của gói.** Gói khai `TOKEN_FORM` (ô chữ, mật khẩu, danh sách chọn tải từ gói) thay cho một ô token trơn, có nút Tạo và Sao chép cho mã bí mật. Form hiện ở cả lúc thêm lẫn lúc sửa tài khoản.
- **Cảnh báo trả lời trùng.** Messenger đã trả lời Facebook và Instagram. Kênh của gói nối lại hai mạng đó thì các lựa chọn này để trống sẵn, chọn vào sẽ hiện cảnh báo rõ, và phải tích xác nhận mới lưu được. Máy chủ cũng chặn nếu chưa xác nhận. Tài khoản cũ vẫn sửa được bình thường.

## en
### Added
- **Pack channels show their own logo.** A pack declaring `logo_svg` gets its logo on the Chatbot and Conversations pages. The SVG is sanitized: shapes only, no scripts or outside links.
- **Account form declared by the pack.** A pack declaring `TOKEN_FORM` (text, password, and select fields loaded from the pack) replaces the plain token box, with Generate and Copy for secrets. The form appears when adding and when editing an account.
- **Duplicate reply warning.** Messenger already answers Facebook and Instagram. When a pack channel reaches either network again, those options start unselected, picking one shows a clear warning, and saving needs a ticked acknowledgement. The server refuses it too without the acknowledgement. Existing accounts stay editable.
