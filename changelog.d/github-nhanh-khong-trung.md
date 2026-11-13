---
bump: patch
title: GitHub jobs no longer get stuck pushing to a branch name already taken
---
## vi
### Sửa lỗi
- **Việc GitHub thứ hai trong một khung chat không còn kẹt ở bước đẩy lên.** Tên PR và tên nhánh giờ lấy từ chính câu yêu cầu, bỏ qua các dòng ngữ cảnh như "[NGỮ CẢNH GIAO DIỆN: ...]", nên mỗi việc có tên riêng. Nếu tên đã có người dùng ở máy hay trên GitHub, Javis tự thêm -2, -3 rồi đẩy lên, không còn dừng với câu "có commit mà máy này không có, Javis không ghi đè".

## en
### Fixed
- **The second GitHub job in a chat no longer gets stuck at the push.** The PR title and branch name now come from the request itself, skipping the dashboard's bracketed context lines, so every job gets its own name. When the name is already used on this machine or on GitHub, Javis adds -2, -3 and pushes, instead of stopping with "has commits this machine lacks, Javis does not overwrite them".
