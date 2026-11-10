---
bump: minor
title: Zalo bots read back bill photos sent to groups while the machine was off
---
## vi
### Thêm mới
- Bot Zalo có thể đọc bù ảnh bill gửi vào nhóm học phí lúc máy tắt: sau lần đọc đầu tiên khi bật lại, các ảnh trong khoảng máy tắt (tối đa `max_hours`) được đưa lần lượt vào quy trình bill như tin trực tiếp. Chỉ ảnh, không bao giờ tin chữ; mỗi ảnh một lần; lượt đọc bù không gửi chữ tự do vào nhóm; tóm tắt chỉ vào chuông. Mặc định tắt, bật bằng trường `catchup_group_images` của bot, tắt khẩn bằng biến môi trường `JAVIS_ZALO_GROUP_CATCHUP=0`.

## en
### Added
- A Zalo bot can read back bill photos sent to tuition groups while the machine was off: after the first read once it is back, photos from the downtime (at most `max_hours`) go through the bill flow one by one like live messages. Photos only, never chat text; each photo once; catch-up turns send no free text to the group; the summary goes to the bell only. Off by default, enabled with the bot's `catchup_group_images` field, emergency stop with the `JAVIS_ZALO_GROUP_CATCHUP=0` env var.
