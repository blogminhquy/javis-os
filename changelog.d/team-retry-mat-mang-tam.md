---
bump: patch
title: Team steps retry on their own after a brief network drop on the machine
---
## vi
### Sửa lỗi
- **Bước của Team và việc Kanban tự chạy lại khi máy mất mạng chốc lát.** Lỗi kiểu "can't assign requested address" hay lỗi tra tên miền (getaddrinfo) lúc đổi Wi-Fi, máy ngủ dậy, bật VPN giờ được coi là lỗi tạm thời, không còn chặn cả việc chờ bấm Thử lại.

## en
### Fixed
- **Team steps and Kanban jobs retry on their own after a brief network drop.** Errors like "can't assign requested address" or a failed DNS lookup (getaddrinfo) after a Wi-Fi switch, waking from sleep or turning on a VPN now count as temporary, instead of blocking the whole job until someone presses Retry.
