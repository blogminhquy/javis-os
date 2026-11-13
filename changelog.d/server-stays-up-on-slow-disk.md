---
bump: patch
title: Javis stays responsive when the server's disk is slow, and right after an update
---
## vi
### Sửa lỗi
- **Javis không còn đứng hình khi đĩa của máy chủ trả lời chậm.** Trên VPS, mỗi lần đĩa chậm vài giây là mọi trang, bot và kết nối cùng đứng theo, có lúc máy chủ bị coi là sập. Nặng nhất ngay sau khi cập nhật. Giờ các việc chạy liên tục (kiểm tra đăng nhập, hub MCP, bot, link chia sẻ) không còn phải chờ đĩa.
- **Cập nhật bản Docker xong, các nguồn MCP không phải tải và cài lại từ đầu.** Phần đã cài được giữ trên ổ dữ liệu, nên máy chủ không bị dồn việc lúc vừa khởi động lại. Riêng lần cập nhật lên bản này vẫn cài lại một lần cuối.
- **Lúc khởi động, Javis mở các nguồn MCP theo từng nhóm nhỏ** thay vì tất cả cùng lúc, để máy chủ nhỏ không bị quá tải.

## en
### Fixed
- **Javis no longer freezes when the server's disk answers slowly.** On a VPS, every few seconds of slow disk froze all pages, bots and connections together, and the server could be reported as down. It was worst right after an update. The work that runs all the time (the sign-in check, the MCP hub, bots, shared links) no longer waits for the disk.
- **After a Docker update, MCP sources no longer download and install themselves again.** What they installed is kept on the data volume, so the server is not flooded while it starts. The update to this version still reinstalls them one last time.
- **At start-up, Javis opens MCP sources a few at a time** instead of all at once, so a small server is not overloaded.
