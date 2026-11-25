---
bump: patch
title: A file a bot sends with a send tool is no longer sent a second time at the end of the turn
---
## vi
### Sửa lỗi
- **Bot không còn gửi trùng ảnh/file.** Bot gửi ảnh bằng `zalo_send_image` (hoặc gửi file) ngay giữa lượt thì cuối lượt không tự đính kèm lại chính file đó nữa.

## en
### Fixed
- **Bots no longer send the same photo or file twice.** A file a bot already sent mid-turn with `zalo_send_image` (or a send-file tool) is not attached again at the end of the turn.
