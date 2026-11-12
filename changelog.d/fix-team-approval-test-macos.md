---
bump: patch
title: Team approval native-classification test passes on macOS temp paths
---

## vi

### Sửa lỗi

- **Test phân loại công cụ của nhóm không còn đỏ trên macOS.** Thư mục tạm `/var` là liên kết tới `/private/var`, test truyền thư mục gốc chưa phân giải nên mọi lệnh ghi bị xếp nhầm là "ngoài". Code sản xuất không đổi.

## en

### Fixed

- **The team native-classification test no longer fails on macOS.** The temp folder `/var` is a symlink to `/private/var`. The test passed an unresolved root, so every write was misclassified as outside. Production code is unchanged.
