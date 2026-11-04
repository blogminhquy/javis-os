---
bump: minor
title: Long background commands report back when they finish, on every engine
---
## vi
### Thêm mới
- **Lượt chat chạy lâu xong thì rung chuông và báo lên điện thoại.** Lượt từ 3 phút trở lên, hoặc lượt Javis tự làm tiếp sau việc nền, để câu trả lời vào hòm thư và đẩy thông báo. Máy đang mở Javis ngay trước mặt thì không hiện thông báo. Đổi mốc bằng `JAVIS_LONG_TURN_NOTIFY_S` (0 là tắt).

### Sửa lỗi
- **Lệnh dài chạy ngầm (render, dựng video) giờ tự báo về khi xong, với mọi bộ não.** Trước đây Javis không thấy lệnh ngầm của Claude Code, và có thể sót lệnh ngầm của Codex, Grok, Antigravity, nên không báo gì và lời dặn "xong thì làm tiếp" bị bỏ. Giờ mọi lệnh ngầm của khung chat đều được theo dõi: xong là báo vào đúng khung chat, kèm file mới, rồi tự làm tiếp phần đã hẹn.
- **Việc nền chạy quá 30 phút không còn bị dừng giữa chừng.** Hết giờ chờ thì lượt chat nhả ra, còn việc vẫn chạy tiếp và được theo dõi tới khi xong.

## en
### Added
- **A long chat turn rings the bell and your phone when it ends.** A turn of 3 minutes or more, or one Javis opens itself after background work, leaves its answer in the inbox and sends a push notification. A device showing Javis right now shows no notification. Change the mark with `JAVIS_LONG_TURN_NOTIFY_S` (0 turns it off).

### Fixed
- **Long background commands (renders, video edits) now report back when done, on every engine.** Javis could not see Claude Code's, and could miss those of Codex, Grok and Antigravity, so nothing was reported and "carry on when it is done" was dropped. Now every background command of a chat is tracked: when one ends, the chat gets the news with the new files, and Javis carries on with what was promised.
- **Background work running past 30 minutes is no longer killed.** When the wait runs out the chat is freed, while the work keeps running and is watched until it ends.
