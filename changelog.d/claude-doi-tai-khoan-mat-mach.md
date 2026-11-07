---
bump: patch
title: A chat that moves to a second Claude account no longer dies with "ProcessError exit code 1"
---
## vi
### Sửa lỗi
- **Tự chuyển sang tài khoản Claude thứ hai giờ chạy được thật.** Trước đây tài khoản 1 hết lượt thì Javis có chọn tài khoản 2, nhưng vẫn cố mở lại mạch hội thoại cũ vốn nằm trong thư mục của tài khoản 1. Claude Code không tìm thấy mạch đó nên thoát ngay, và mọi tin nhắn sau đều báo "SDK engine: ProcessError: Command failed with exit code 1". Nay Javis nhận ra mạch thuộc tài khoản khác, mở mạch mới trên tài khoản đang chạy và mồi lại ngữ cảnh từ lịch sử đã lưu, nên hội thoại chạy tiếp như bình thường.
- **Mạch cũ bị mất cũng được khôi phục dù Claude Code báo bằng lỗi thoát.** Bản Claude Code mới báo "No conversation found" bằng cách thoát mã 1 thay vì trả kết quả lỗi, nên đường khôi phục ngữ cảnh trước đây không chạy. Nay cả hai cách báo đều được nhận ra.

## en
### Fixed
- **Moving to a second Claude account now really works.** Before, when account 1 ran out, Javis picked account 2 but still tried to resume the old conversation thread, which lives in account 1's folder. Claude Code could not find it and exited at once, so every later message failed with "SDK engine: ProcessError: Command failed with exit code 1". Javis now sees the thread belongs to another account, opens a new one on the running account and primes it from the saved history, so the chat carries on.
- **A lost thread is restored even when Claude Code reports it by exiting.** Newer Claude Code releases report "No conversation found" by exiting with code 1 instead of returning an error result, so the old restore path never ran. Both ways are recognised now.
