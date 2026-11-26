---
bump: minor
title: Windows watchdog restarts Javis when the server dies or hangs
---
## vi
### Thêm mới
- **Javis trên Windows tự bật lại khi server chết hoặc treo.** Một tác vụ nền kiểm Javis mỗi phút, ba lần không trả lời liên tiếp thì khởi động lại, khoảng 3 phút là chạy lại.
- **Tắt chủ động thì watchdog đứng yên.** Sau `stop-javis.bat` nó chờ tới khi bạn bật lại, và cũng không chen ngang lúc đang cập nhật.
- Máy cài mới tự có watchdog. Máy đang chạy bật bằng `javis-watchdog.bat install`.

## en
### Added
- **Javis on Windows restarts itself when the server dies or hangs.** A background task checks Javis every minute and restarts it after three missed answers in a row, so it is back within about 3 minutes.
- **A deliberate stop is respected.** After `stop-javis.bat` the watchdog waits until you start Javis again, and it never interrupts an update.
- New installs get the watchdog automatically. On an existing machine, run `javis-watchdog.bat install`.
