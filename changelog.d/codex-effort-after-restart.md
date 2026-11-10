---
bump: patch
title: Codex keeps the chosen reasoning level right after a restart
---
## vi
### Sửa lỗi
- **Codex chạy đúng mức suy luận đã chọn ngay sau khi Javis khởi động lại.** Trước đây, cho tới khi có người mở trang Models, bot và việc nền chạy bằng Codex rơi về mức mặc định của Codex (thường là cao) dù đã chọn thấp hay trung bình, nên chậm và tốn lượt hơn.

## en
### Fixed
- **Codex runs at the chosen reasoning level right after Javis restarts.** Until someone opened the Models page, bots and background jobs on Codex fell back to Codex's own default (usually high) even when low or medium was set, which was slower and used more of the plan.
