---
bump: patch
title: Conflicting PRs on private GitHub repos get fixed again
---
## vi
### Sửa lỗi
- **PR của repo riêng tư bị xung đột giờ được Javis tự gộp lại.** Trước đây vòng sửa xung đột dừng ngay ở bước tải nhánh chính, vì phần chạy lệnh của AI không có quyền vào GitHub. Giờ Javis tự tải nhánh chính về trước, AI chỉ còn việc gộp và giải quyết xung đột.
- **Mất mạng lúc đó thì Javis chờ rồi thử lại.** Vòng sửa không còn bị tiêu mất vào một lần gộp chắc chắn hỏng; thẻ repo ghi rõ lý do đang chờ.

## en
### Fixed
- **A conflicting PR on a private repo is merged back by Javis again.** The conflict fix round used to stop at downloading the main branch, because the AI's shell has no access to GitHub. Javis now downloads the main branch first, and the AI only merges and resolves the conflict.
- **If GitHub is unreachable at that moment, Javis waits and tries again.** A fix round is no longer spent on a merge that cannot work; the repo card says why it is waiting.
