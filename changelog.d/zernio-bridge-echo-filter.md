---
bump: patch
title: Filter explicit Zernio echo messages before forwarding
---
## vi
### Sửa lỗi
- Bridge Zernio bỏ qua tin có cờ echo ngay cả khi hướng tin vẫn ghi là đến, tránh bot trả lời tin vọng lại.

## en
### Fixed
- The Zernio bridge ignores explicit echo flags even when the message direction says incoming, preventing replies to echoed messages.
