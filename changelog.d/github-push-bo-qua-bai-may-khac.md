---
bump: patch
title: GitHub push from chat no longer stalls on another OS's CI job
---
## vi
### Sửa lỗi
- **Javis đẩy nhánh lên GitHub được ngay cả khi repo có bài kiểm tra dành cho máy Mac hay Windows.** Trước đây máy Linux cũng chạy thử bài cài đặt của Mac, bài đó treo rồi báo đỏ nên Javis dừng đẩy, dù thay đổi chẳng liên quan. Giờ bài của hệ điều hành khác để CI trên GitHub chạy, rồi CI xanh là Javis tự merge như thường.

## en
### Fixed
- **Javis pushes to GitHub even when the repo has CI jobs for macOS or Windows.** A Linux machine used to run the Mac install test too, which hung, turned red and stopped the push of an unrelated change. Jobs for another OS are now left to GitHub CI, and Javis still merges on its own once CI is green.
