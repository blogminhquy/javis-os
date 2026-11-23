---
bump: minor
title: GitHub in chat can rerun red CI and explains a red job with no log
---
## vi
### Thêm mới
- **Nhắn "chạy lại CI" là Javis chạy lại các job đỏ của PR.** Javis theo dõi kết quả như mọi lần. Token GitHub cần quyền Actions là Read and write.

### Cải thiện
- **Job CI đỏ mà GitHub không có log thì Javis tự chạy lại một lần.** Repo private hết phút Actions hay chạm hạn mức chi tiêu hay gặp cảnh này. Lượt sửa ghi rõ vì sao không có log, model không còn đoán bừa lỗi trong code.

## en
### Added
- **Say "rerun the CI" and Javis reruns the PR's red jobs.** Javis follows the result as usual. The GitHub token needs Actions set to Read and write.

### Improved
- **A red CI job with no log on GitHub is rerun once on its own.** This is what a private repo out of Actions minutes or over its spending limit looks like. The fix round says why there is no log, so the model no longer guesses at a bug in the code.
