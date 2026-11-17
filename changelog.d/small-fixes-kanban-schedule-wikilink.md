---
bump: minor
title: Quiet background jobs, fixed done-criteria, honest schedule edits and short wikilinks that open
---
## vi
### Thêm mới
- **Giao việc nền kèm điều kiện hoàn thành cố định.** Việc do script hay quy trình giao mỗi ngày giữ nguyên lời giao và được chấm đúng theo các điều kiện đó, không còn hôm đạt hôm kẹt.

### Sửa lỗi
- **Việc nền trả lời `[SILENT]` thì xong lặng lẽ**, như nhắc hẹn: không còn tin "không có gì" mỗi lần chạy, cũng không bị máy tự kiểm chấm trượt.
- **Sửa lịch đổi được mức quyền, nơi nhận kết quả và giọng đọc.** Trước đây Javis báo "Đã sửa" mà lịch vẫn giữ mức cũ.
- **Wikilink tên ngắn như `[[log]]` mở được** cả khi brain có nhiều file nhắc tới chữ đó. Team cần duyệt chạy ChatGPT trên Docker bị từ chối thì câu báo chỉ luôn cách bật sandbox.

## en
### Added
- **Background jobs can carry fixed done-criteria.** A job a script or workflow hands out every day keeps its wording and is checked against exactly those criteria, so it no longer passes one day and sticks the next.

### Fixed
- **A background job that answers `[SILENT]` finishes quietly**, like reminders: no more "nothing to report" messages on every run, and the automatic check no longer fails it.
- **Editing a schedule changes its permission level, who gets the result and the spoken note.** Javis used to say "updated" while the old level stayed.
- **Short wikilinks like `[[log]]` open** even when many files mention the word. When an approval team refuses ChatGPT on Docker, the message now says how to turn the sandbox back on.
