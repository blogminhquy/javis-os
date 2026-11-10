---
bump: patch
title: Claude answers again on Windows machines that installed it with npm
---
## vi
### Sửa lỗi
- **Claude trả lời lại trên máy Windows cài bằng npm.** Sau khi cập nhật, mọi lượt chat Claude báo "Refusing to execute batch script ...claude.CMD". Javis giờ tự tìm `claude.exe` thật nằm cạnh file đó (hoặc bản cài native, hoặc bản đi kèm SDK) nên không cần cài lại gì. Codex không dính lỗi này.

## en
### Fixed
- **Claude answers again on Windows machines that installed it with npm.** After an update every Claude chat turn failed with "Refusing to execute batch script ...claude.CMD". Javis now finds the real `claude.exe` next to that file (or the native install, or the one bundled with the SDK), so nothing needs reinstalling. Codex was not affected.
