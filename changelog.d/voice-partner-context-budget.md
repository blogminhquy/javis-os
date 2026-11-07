---
bump: minor
title: Partner voice calls keep long instructions and pinned rules
---
## vi
### Cải thiện
- **Gọi thoại với cộng sự giữ được hướng dẫn dài hơn.** Phần hướng dẫn trong file cộng sự đưa vào cuộc gọi tăng từ 4.000 lên 12.000 ký tự, bộ nhớ từ 2.000 lên 6.000, chỉnh được qua `JAVIS_VOICE_AGENT_BODY_CHARS` và `JAVIS_VOICE_AGENT_MEMORY_CHARS`. Đặt luật quan trọng giữa `<!-- JAVIS_VOICE_RULES_START -->` và `<!-- JAVIS_VOICE_RULES_END -->` trong file cộng sự thì luật đó luôn được đưa lên đầu, không bị cắt.
- **Cộng sự không bịa số liệu khi gọi thoại.** Mọi cuộc gọi với cộng sự luôn kèm một luật không bị cắt: thông tin hay thay đổi phải lấy từ công cụ, và chỉ báo việc đã xong khi công cụ trả kết quả thành công.

## en
### Improved
- **Partner voice calls keep longer instructions.** The partner file text sent into a call grows from 4,000 to 12,000 characters and memory from 2,000 to 6,000, adjustable with `JAVIS_VOICE_AGENT_BODY_CHARS` and `JAVIS_VOICE_AGENT_MEMORY_CHARS`. Rules placed between `<!-- JAVIS_VOICE_RULES_START -->` and `<!-- JAVIS_VOICE_RULES_END -->` in the partner file always move to the top and are never cut.
- **Partners do not make up figures on a call.** Every partner call carries a rule that is never cut: changing facts come from tools, and a task is reported done only when a tool returned success.
