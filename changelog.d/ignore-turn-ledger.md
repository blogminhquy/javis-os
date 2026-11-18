---
bump: patch
title: A full local test run no longer leaves the turn ledger untracked
---
## vi
### Sửa lỗi
- **Chạy đủ bộ test trên máy không còn tự báo đỏ ở lần sau.** Tệp sổ lượt chat (`turn_ledger.sqlite3`) mà test tạo ra trong `server/` nay được git bỏ qua như các kho dữ liệu chạy khác.

## en
### Fixed
- **A full local test run no longer turns itself red the next time.** The turn ledger file (`turn_ledger.sqlite3`) that tests create in `server/` is now ignored by git like the other runtime stores.
