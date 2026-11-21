---
bump: patch
title: Hostinger compose stays under hPanel's size limit however it is counted
---
## vi
### Sửa lỗi
- **Link cài Hostinger gọn hơn để hPanel không từ chối vì quá dài.** File `docker-compose.hostinger.yml` từng được rút xuống dưới trần 32.768 ký tự của hPanel, nhưng nếu hPanel đếm sau khi mã hoá nội dung thì file vẫn vượt trần (35.485), vì mỗi chữ tiếng Việt có dấu trong phần chú thích tốn sáu ký tự. Chú thích trong file nay viết ngắn, bằng tiếng Anh không dấu: file còn 23.917 ký tự, và khoảng 25.000 sau khi mã hoá. Mọi cài đặt giữ nguyên, phần giải thích chuyển sang `docs/dev/hostinger-compose.md`.

## en
### Fixed
- **The Hostinger install link is smaller, so hPanel does not refuse it for its length.** `docker-compose.hostinger.yml` had been cut below hPanel's limit of 32,768 characters, but if hPanel counts the text after encoding it, the file was still over (35,485), because every accented Vietnamese letter in the comments costs six characters. The comments are now short, in English and ASCII only: the file is 23,917 characters, and about 25,000 once encoded. Every setting is unchanged, and the explanations moved to `docs/dev/hostinger-compose.md`.
