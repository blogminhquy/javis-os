---
bump: patch
title: Private GitHub repos attach again after their main branch moves
---
## vi
### Sửa lỗi
- **Gắn repo riêng tư vào chat không còn hỏng khi nhánh chính có file mới.** Trước đây repo riêng tư chỉ gắn được lần đầu; hễ nhánh chính có thêm hoặc đổi file là chat mới báo `could not fetch ... from promisor remote`.
- **Đổi nhánh gốc của chat cũng chạy với repo riêng tư.** Cùng lỗi đó làm nút Đổi nhánh và việc tạo lại nhánh sau khi merge thất bại; cả hai đã được sửa.

## en
### Fixed
- **Attaching a private repo to a chat no longer fails once its main branch has new files.** A private repo used to attach only the first time; as soon as the main branch gained or changed a file, a new chat stopped with `could not fetch ... from promisor remote`.
- **Changing a chat's base branch works on private repos too.** The same fault broke Change branch and the fresh branch Javis starts after a merge; both are fixed.
