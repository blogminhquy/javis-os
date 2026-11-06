---
bump: minor
title: A failed GitHub push is retried on its own, right after GitHub is connected again
---
## vi
### Sửa lỗi
- **Đẩy code lên GitHub hỏng một lần không còn kẹt luôn.** Trước đây sau một lần đẩy lỗi, các lượt chat sau coi như "không có gì đổi" nên không bao giờ đẩy lại, kể cả khi đã đăng nhập GitHub lại. Giờ Javis tự đẩy lại ở lượt chat kế tiếp, định kỳ vài phút một lần, và ngay khi GitHub được kết nối lại, rồi mở PR, chờ CI và tự merge như thường.
- **Lỗi đẩy nói bằng lời dễ hiểu.** Thay cho câu git `could not read Username`, Javis nói rõ là thiếu đăng nhập hay thiếu quyền ghi vào repo, và cần làm gì ở trang Kết nối.

### Thêm mới
- **Nút Đẩy lại** trong bảng GitHub của cuộc chat, cho lần đẩy đang chờ thử lại.

### Cải thiện
- **Model biết trạng thái thật của repo** (đã lên GitHub chưa, PR, CI, lý do kẹt), nên không còn trả lời "em không được đẩy" hay đề nghị sửa code chỉ để kích hoạt việc đẩy.

## en
### Fixed
- **One failed GitHub push no longer stalls for good.** After a failed push, later turns counted as "nothing changed" and never pushed again, even after signing in to GitHub again. Javis now retries on the next turn, every few minutes, and right when GitHub is connected again, then opens the PR, waits for CI and auto-merges as usual.
- **Push errors in plain words.** Instead of git's `could not read Username`, Javis says whether the sign-in or the write permission is missing, and what to do on the Connections page.

### Added
- **Push again button** in the chat's GitHub panel, for a push waiting to be retried.

### Improved
- **The model knows the repo's real state** (on GitHub or not, PR, CI, why it is stuck), so it no longer answers "I am not allowed to push" or offers code edits just to trigger a push.
