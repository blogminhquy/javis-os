---
bump: patch
title: A merged PR no longer keeps the chat's "waiting for CI" icon
---
## vi
### Sửa lỗi
- **PR đã merge không còn kẹt biểu tượng "đang chờ CI".** Khi PR được merge lúc Javis mất kết nối GitHub, khung chat từng giữ mãi biểu tượng nhánh đang làm. Giờ nó đổi sang biểu tượng đã merge, và `javis_github` không còn báo "chờ CI" cho PR đã merge.

## en
### Fixed
- **A merged PR no longer sticks on "waiting for CI".** When a PR was merged while Javis had lost its GitHub connection, the chat kept the working-branch icon forever. It now shows as merged, and `javis_github` no longer reports "waiting for CI" for a merged PR.
