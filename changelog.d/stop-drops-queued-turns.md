---
bump: patch
title: Stop no longer starts the messages typed meanwhile
---
## vi
### Sửa lỗi
- **Bấm Dừng là dừng hẳn.** Tin gõ thêm trong lúc Javis đang trả lời không còn tự chạy thành lượt mới ngay sau khi bấm Dừng; dòng dưới tin đổi thành "Chưa làm tin này: lượt đã bị dừng", tin vẫn nằm trong khung chat để gửi lại.
- **Lời dặn "xong thì làm tiếp" của lượt bị dừng và lịch tự chạy lại khi hết hạn mức của khung chat đó cũng được bỏ.** Việc chạy nền vẫn chạy và vẫn báo khi xong; việc của các lượt trước và vòng sửa GitHub giữ nguyên.

## en
### Fixed
- **Stop now stops for good.** Messages typed while Javis was answering no longer start a new turn right after Stop; their line reads "Not run: the turn was stopped" and they stay in the chat to send again.
- **The stopped turn's "when done, continue" instruction and the chat's quota auto re-run are dropped too.** Background work keeps running and still reports when it ends; jobs of earlier turns and GitHub fix rounds are left as they were.
