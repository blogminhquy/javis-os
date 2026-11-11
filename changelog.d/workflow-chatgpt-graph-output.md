---
bump: patch
title: Honor ChatGPT in restricted workflows and remove Graph credentials from tool output
---
## vi
### Sửa lỗi
- Bước quy trình giới hạn công cụ dùng ChatGPT khi đã chọn ChatGPT, giữ mức quyền và danh sách công cụ của bước.
- Kiểm Messenger phát hiện đường HTTPS không truy cập được và so callback với Link nhanh đang chạy, giữ nguyên đường dẫn nhận tin. Sửa tự động lưu địa chỉ mới sau khi Meta xác minh thành công.
- Tài khoản nhận tin đã chọn kênh dự phòng được kiểm và sửa đăng ký `standby` ở cả ứng dụng và Trang, giữ các trường webhook đang có.
### Bảo mật
- Công cụ Facebook và Meta Ads loại thông tin xác thực khỏi dữ liệu phân trang và thông báo lỗi trả về cho AI.

## en
### Fixed
- Restricted workflow steps use the selected ChatGPT provider while retaining the step's permission level and tool list.
- Messenger checks detect unreachable HTTPS receivers and compare callbacks with the active quick tunnel while preserving the receiver path. Explicit repair saves the new address after successful verification.
- Accounts opted into standby reception check and repair the app and Page standby subscriptions while retaining existing webhook fields.
### Security
- Facebook and Meta Ads tools remove credentials from pagination data and errors returned to the model.
