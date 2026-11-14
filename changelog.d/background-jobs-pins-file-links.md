---
bump: minor
title: Background jobs report on finish, pins survive a fallback, file links with line numbers open
---
## vi
### Thêm mới
- **Link mở thẳng một trang của dashboard.** Link dạng `#p=tasks` (hay tên trang khác) mở đúng trang đó, kể cả khi tab Javis đang mở sẵn.

### Sửa lỗi
- **Việc chạy nền Javis tự bật khi chat bằng API key báo xong đúng lúc.** Trước đây việc kẹt ở trạng thái "đang chạy" tới khi khởi động lại máy chủ.
- **Cuộc chat đã ghim model giữ nguyên model đó.** Khi model ghim tạm hết lượt hoặc mất đăng nhập, lượt chat chạy tạm bằng model chính, rồi tự quay lại model đã ghim khi dùng được lại.
- **Link file kèm số dòng (kiểu `agents/x.md#L66-L75`) mở đúng file.** Câu trả lời không còn bị gắn cảnh báo sai "không tìm thấy file trong brain".

## en
### Added
- **Links that open a dashboard page directly.** A link like `#p=tasks` (or another page name) opens that page, even in a Javis tab that is already open.

### Fixed
- **Background commands Javis starts in an API-key chat report when they finish.** They used to stay "running" until the server restarted.
- **A chat pinned to a model keeps that model.** While the pinned model is out of quota or signed out, turns run on the main model for the moment, then go back to the pinned model once it works again.
- **File links with line numbers (like `agents/x.md#L66-L75`) open the file.** Answers no longer get a false "file not found in the brain" warning.
