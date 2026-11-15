---
bump: patch
title: Add guarded upstream synchronization for the Zernio fork
---
## vi
### Cải thiện
- Thêm quy trình nhận cập nhật upstream trên nhánh ứng viên và kiểm thử trước khi cập nhật nhánh tùy chỉnh.
- Chấp nhận URL GitHub có xác thực khi đồng bộ fork, vẫn kiểm tra đúng chủ sở hữu và repository.

## en
### Improved
- Add candidate-branch upstream synchronization with tests before advancing the custom branch.
- Accept authenticated GitHub remote URLs while still validating the expected owner and repository.
