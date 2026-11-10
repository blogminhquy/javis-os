---
bump: patch
title: New Claude models show even when Claude Code is outdated
---
## vi
### Sửa lỗi
- **Claude Fable 5.2 đã có trong ô chọn model.** Trước đây danh sách model Claude chỉ lấy từ bản Claude Code đang cài, nên máy nào Claude Code chưa lên bản mới thì không thấy model mới dù đã cập nhật Javis. Nay danh sách gộp cả model mà bản Javis biết, bản mới nhất đứng trên.
- **Thêm Claude Haiku 5.5 vào danh sách dự phòng và sửa giá quy đổi** của Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5 trên trang Mức dùng.

## en
### Fixed
- **Claude Fable 5.2 is in the model picker.** The Claude model list used to come only from the installed Claude Code, so a machine whose Claude Code had not updated yet missed new models even after updating Javis. The list now also includes the models this Javis release knows, newest first.
- **Claude Haiku 5.5 joins the fallback list and the cost estimates are corrected** for Fable 5.2, Opus 5.5, Sonnet 5.5 and Haiku 5.5 on the Usage page.
