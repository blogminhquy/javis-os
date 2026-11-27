---
bump: minor
title: Windows watchdog restarts Javis when the server dies or hangs
---
## vi
### Thêm mới
- **Javis trên Windows tự bật lại khi server chết hoặc treo.** Một tác vụ nền kiểm Javis mỗi phút, ba lần không trả lời liên tiếp thì khởi động lại, khoảng 3 phút là chạy lại.
- **Tắt chủ động thì watchdog đứng yên.** Sau `stop-javis.bat` nó chờ tới khi bạn bật lại, và cũng không chen ngang lúc đang cập nhật.
- **Không phải gõ lệnh:** máy đang bật "Tự bật Javis khi mở máy" tự có watchdog sau khi cập nhật, tắt mục đó thì watchdog cũng tắt theo. Gỡ hẳn bằng `javis-watchdog.bat uninstall`.

## en
### Added
- **Javis on Windows restarts itself when the server dies or hangs.** A background task checks Javis every minute and restarts it after three missed answers in a row, so it is back within about 3 minutes.
- **A deliberate stop is respected.** After `stop-javis.bat` the watchdog waits until you start Javis again, and it never interrupts an update.
- **No command to run:** a machine with "Launch Javis at startup" on gets the watchdog after updating, and turning it off removes the watchdog too. Remove it for good with `javis-watchdog.bat uninstall`.
