---
bump: patch
title: Hanging up keeps the work running, system lines drop the fixed pronoun
---
## vi
### Sửa lỗi
- **Cúp máy khi Javis còn đang làm việc được giao trong cuộc gọi thì việc không bị bỏ.** Javis làm nốt rồi gửi kết quả vào khung chat của cuộc gọi, kèm thông báo.
- **Đường gọi Tự động không tự chuyển sang ChatGPT Live chỉ vì máy có sẵn phiên Codex.** ChatGPT Live chỉ được chọn khi ChatGPT là model chính hoặc đã kết nối ở trang Models.

### Cải thiện
- **Các dòng hệ thống Javis gắn dưới câu trả lời không còn xưng cứng "mình".** Dòng theo dõi việc chạy nền, đính chính lời hẹn, nhắc trí nhớ, link không thấy file viết không đại từ, nên không lệch với cách xưng hô đã chọn.

## en
### Fixed
- **Hanging up while Javis is still working on something asked for in the call no longer drops it.** Javis finishes and posts the result to the call's chat, with a notification.
- **The Automatic call path no longer switches to ChatGPT Live just because the machine has a Codex sign-in.** ChatGPT Live is picked only when ChatGPT is the main model or connected on the Models page.

### Improved
- **System lines Javis adds under answers no longer hardcode a Vietnamese first-person pronoun.** Background job tracking, empty-promise and memory notes and missing-file links are written without a pronoun, so they match the chosen form of address.
