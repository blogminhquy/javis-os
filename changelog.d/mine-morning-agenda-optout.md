---
bump: patch
title: Allow disabling the separate morning My Tasks agenda
---
## vi
### Sửa lỗi
- **Tắt riêng bản tổng hợp Việc của tôi lúc 07:30 khi đã có Morning Brief.** Đặt `agenda_enabled: false` trong `Javis/my-tasks.json` của brain cần tắt. Không thay đổi task, nhắc deadline, lịch hẹn hay thông báo thói quen của brain đó. Mặc định các brain khác vẫn có bản tổng hợp như cũ.

## en
### Fixed
- **Opt out of the standalone 07:30 My Tasks agenda per brain.** Set `agenda_enabled: false` in the brain's `Javis/my-tasks.json`. Timed tasks, appointment reminders and habit nudges remain active; all other brains retain the previous default.
