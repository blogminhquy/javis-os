---
bump: patch
title: Partners chat no longer cries "too long to open" while reconnecting; clearer background job errors
---
## vi
### Sửa lỗi
- **Mở hội thoại ở trang Cộng sự hết báo nhầm "mở quá lâu".** Lúc trang đang tự kết nối lại thì không báo lỗi nữa. Mở Javis Core bị treo thì báo lỗi kèm nút Thử lại, và bấm Thử lại là tải lại thật thay vì chờ tiếp lượt đang treo.
- **Việc nền chạy bằng ChatGPT (Codex) bị chặn ghi file giờ báo đúng là lỗi môi trường**, kèm cách sửa, thay vì nằm ở "chờ bạn trả lời".
- **Ký ức do việc nền ghi không còn bị gắn nhầm nguồn** là cuộc chat đang mở cùng lúc.

## en
### Fixed
- **Opening a chat on the Partners page no longer says "taking too long" by mistake.** No error while the page is reconnecting. A Javis Core open that hangs shows the error with Retry, and Retry really loads again instead of waiting on the stuck load.
- **Background work on ChatGPT (Codex) that was refused file writes now says it is an environment problem**, with what to change, instead of sitting in "waiting for your answer".
- **Memories written by background work no longer get the source of a chat** that happened to be open at the same time.
