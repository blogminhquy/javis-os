---
bump: patch
title: A root install on Linux runs Javis as a regular account
---
## vi
### Sửa lỗi
- **Cài bằng root trên Linux không còn làm Claude lỗi "exit code 1".** Bản cài mới tự tạo tài khoản thường `javis` và chạy Javis dưới tài khoản đó, vì Claude Code từ chối mức Toàn quyền dưới root.
- **Bản clone nằm trong `/root` được chuyển sang `/opt`**, vì tài khoản khác không vào được `/root`. Trình cài báo rõ nơi mới.
- **Máy đã cài từ trước giữ nguyên tài khoản cũ.** `./update.sh` chạy bằng root vẫn dùng như thường.

## en
### Fixed
- **A root install on Linux no longer breaks Claude with "exit code 1".** A fresh install creates a regular account `javis` and runs Javis under it, because Claude Code refuses Full access under root.
- **A clone inside `/root` is moved to `/opt`**, since no other account can enter `/root`. The installer says where it went.
- **A machine installed earlier keeps the account it has.** `./update.sh` run as root works as before.
