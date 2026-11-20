---
bump: patch
title: Signing in a second Zalo account no longer cuts the first one off
---
## vi
### Sửa lỗi
- **Kết nối nick Zalo thứ hai không còn làm nick thứ nhất mất kết nối.** Hai người báo ngày 19 và 20/11/2026: mỗi nick một bot ở hai brain, vừa quét QR nick thứ hai thì thẻ bot của nick thứ nhất báo "Một phiên khác của cùng nick đang giành kết nối Zalo" và bot lỡ phần lớn tin, dù không ai mở Zalo Web.
  - Nguyên nhân: lúc lưu kết nối mới, Javis đóng phiên Zalo đang chạy của nick cũ nhưng không tắt hẳn nó, rồi mở thêm một phiên nữa. Hai phiên cùng nick giành nhau mãi. Trên máy chủ Linux Javis tự dọn sau vài phút, trên Windows và Mac thì kéo dài tới khi khởi động lại.
  - Nay phiên cũ được tắt hẳn, và thêm hay sửa một kết nối khác không còn khởi động lại nick Zalo đang chạy.
  - Ai đang bị: cập nhật bản này rồi khởi động lại máy chạy Javis một lần, để tắt phiên Zalo cũ còn chạy ngầm.
- **Quét QR bằng nick đã kết nối thì Javis báo ngay, không tạo kết nối thứ hai.** Câu báo nêu tên kết nối đang giữ nick đó. Muốn nối nick khác, mở app Zalo bằng nick đó rồi quét lại.

## en
### Fixed
- **Connecting a second Zalo account no longer cuts the first one off.** Two reports on 19 and 20/11/2026: one bot per account in two brains, and right after the second account's QR was scanned the first bot's card read "Another session of this account keeps taking the Zalo connection" and the bot missed most messages, with no Zalo Web open anywhere.
  - Cause: when the new connection was saved, Javis dropped the first account's running Zalo session without stopping it, then started another. Two sessions of one account kept taking the connection from each other. A Linux server cleaned it up after a few minutes; on Windows and Mac it lasted until a restart.
  - The old session is now stopped for good, and adding or editing another connection no longer restarts a Zalo account that is running.
  - Anyone affected now: update, then restart the machine that runs Javis once, which stops the leftover Zalo session.
- **Scanning the QR with an account that is already connected is refused right away**, instead of adding a second connection. The message names the connection that holds that account. To connect another account, open the Zalo app signed in as it and scan again.
