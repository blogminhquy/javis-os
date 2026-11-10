---
bump: minor
title: Click a file outside the brain in chat to open it
---
## vi
### Thêm mới
- **Bấm tên file Javis tạo ngoài brain để mở ngay.** Ví dụ một bài giảng nằm trong ~/Documents. Trước đây khung chat chỉ hiện tên file như chữ thường. Giờ đường dẫn đầy đủ thành link, bấm vào là file mở bằng ứng dụng mặc định trên máy, như khi nhấp đúp trong Finder.
- Link chỉ hiện khi bạn dùng Javis ngay trên máy đang chạy nó. Trên VPS, qua tên miền hoặc trong Docker, đường dẫn vẫn là chữ như cũ để bạn sao chép. Link chỉ mở file trong thư mục người dùng. Chương trình và script không được chạy, Javis chỉ mở thư mục chứa chúng. Cảm ơn mminhthu0304-gif đã đóng góp phần này.

## en
### Added
- **Click a file Javis made outside the brain to open it.** For example, a deck in ~/Documents. The chat used to show the file name as plain text. Now the full path is a link that opens the file in its default app on the computer, like a double click in Finder.
- The link appears only when you use Javis on the computer that runs it. On a VPS, through a domain or in Docker, the path stays plain text you can copy, as before. Links only open files inside the home folder. Programs and scripts never run; Javis only shows the folder that holds them. Thanks to mminhthu0304-gif for this contribution.
