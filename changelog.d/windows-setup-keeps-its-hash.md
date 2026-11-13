---
bump: patch
title: The Windows installer is no longer replaced when nothing inside it changed
---
## vi
### Sửa lỗi
- **Bộ cài Windows không còn bị thay file mới vô cớ.** File `JavisOS-Setup.exe` chưa ký số nên trình duyệt và trình diệt virus chỉ nhận ra nó qua mã băm. Trước đây cứ sửa script cài (kể cả script của Linux) là file bị thay, và mỗi lần thay thì Edge lại báo "isn't commonly downloaded" từ đầu. Giờ file chỉ đổi khi chính bộ cài thay đổi.
- **Hướng dẫn cài nhanh có thêm cách gỡ khi bị chặn.** Thêm bước bấm **Keep anyway** khi Edge hoặc Chrome không chịu lưu file, và một dòng lệnh cài không cần file exe cho máy bị trình diệt virus hoặc Smart App Control chặn.

## en
### Fixed
- **The Windows installer is no longer replaced for no reason.** `JavisOS-Setup.exe` is not code-signed yet, so browsers and antivirus engines know it by its file hash alone. Any change to an install script (even the Linux one) used to replace the file, and each new file made Edge say "isn't commonly downloaded" from scratch. The file now changes only when the installer itself does.
- **The quick start explains what to do when the download is blocked.** It adds the **Keep anyway** step for when Edge or Chrome will not save the file, and a one-line install without the .exe for PCs where an antivirus or Smart App Control blocks it.
