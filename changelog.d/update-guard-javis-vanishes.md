---
bump: patch
title: Javis no longer vanishes when an update stops halfway
---
## vi
### Sửa lỗi
- **Javis không còn biến mất (lỗi 404) sau khi cập nhật.** Trên VPS ổ đĩa chậm, Watchtower hết giờ đúng lúc đang xoá container cũ, bỏ dở mà không dựng bản mới, nên Javis mất hẳn khỏi Docker cho tới khi Redeploy.
- Thêm container canh gác `javis-guard`: thấy Javis biến mất hay bị dừng giữa chừng quá 2 phút là tự dựng lại (lên đúng bản mới) hoặc bật lại. Javis anh tự bấm dừng thì nó để yên.
- Mỗi lần cập nhật bằng nút bấm có 30 phút thay vì 10. Cần Redeploy một lần để nhận file compose mới.

## en
### Fixed
- **Javis no longer vanishes (404) after an update.** On a VPS with a slow disk, Watchtower ran out of time while deleting the old container and gave up without creating the new one, so Javis was gone from Docker until a Redeploy.
- New `javis-guard` container: when Javis has been gone or stopped halfway for 2 minutes, it creates it again (on the new version) or starts it again. A Javis you stop yourself is left alone.
- An update from the button now gets 30 minutes instead of 10. Redeploy once to get the new compose file.
