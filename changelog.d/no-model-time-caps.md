---
bump: minor
title: No more time caps on Grok, Claude Code, ChatGPT, background work and Teams
---
## vi
### Cải thiện
- **Bỏ hết trần thời gian của các model.** Grok không còn tự dừng ở phút 15, một lệnh của Claude Code hay ChatGPT không còn bị cắt ở 1 tiếng, việc nền và Nhóm cũng chạy tới khi xong. Nút Dừng vẫn cắt được bất cứ lúc nào.
- Muốn có trần lại thì đặt biến môi trường tương ứng (giây), ví dụ `JAVIS_GROK_TIMEOUT` hay `JAVIS_BG_MAX_WALL_S`. Bản Grok cũ không tự duyệt được tool vẫn giữ lưới 15 phút để không treo mãi.

## en
### Improved
- **Every model time cap is gone.** Grok no longer stops at minute 15, a single Claude Code or ChatGPT command is no longer cut at one hour, and background work and Teams run until done. The Stop button still ends anything at any moment.
- To bring a cap back, set the matching environment variable (seconds), such as `JAVIS_GROK_TIMEOUT` or `JAVIS_BG_MAX_WALL_S`. Old Grok builds that cannot auto-approve tools keep a 15-minute net so they never hang forever.
