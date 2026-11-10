---
bump: patch
title: Scheduled Codex jobs retry once when the tool hub answers late
---
## vi
### Sửa lỗi
- **Việc nền chạy bằng Codex không còn bị bỏ cả lượt vì cổng công cụ lên chậm.** Trước đây cổng trả lời chậm hơn 20 giây là lượt nhắc hẹn hay lịch định kỳ đó hỏng luôn, phải chờ tới lần chạy kế tiếp. Giờ Javis chờ cổng tới 45 giây và tự thử lại một lần sau 30 giây. Lỗi này xảy ra trước khi gọi model nên thử lại không tốn lượt và không lặp hành động nào.

## en
### Fixed
- **A scheduled Codex job is no longer dropped because the tool hub came up late.** A hub that took over 20 seconds used to cost the whole reminder or recurring run until its next slot. Javis now waits up to 45 seconds and tries once more after 30 seconds. The failure happens before the model is called, so the retry costs no turn and repeats no action.
