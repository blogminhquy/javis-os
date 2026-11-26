---
bump: minor
title: Messenger warns when only role holders' messages arrive, and calls let you pick the mic and speaker
---
## vi
### Thêm mới
- **Chọn mic và loa cho cuộc gọi.** Trong Cài đặt, mục Giọng nói, chọn mic và loa ngay cạnh nút Thử mic, Thử loa. Rút thiết bị đã chọn ra thì Javis tự dùng cái mặc định của máy. iPhone và Safari tự chọn loa nên chỉ có ô chọn mic.

### Cải thiện
- **Messenger báo khi tin của khách không về.** Page nhắn cho nhiều người mà Javis không nhận được tin nào của họ thì thẻ bot hiện cảnh báo: có thể Meta chỉ chuyển tin của người có vai trò trong app, cần xin quyền nâng cao cho pages_messaging. Cảnh báo tự tắt khi tin của một khách thường về tới.

## en
### Added
- **Pick the mic and speaker for calls.** In Settings, Voice, pick the mic and speaker right beside Test mic and Test speaker. If the picked device is unplugged, Javis falls back to the system default. iPhone and Safari choose the speaker themselves, so only the mic list shows there.

### Improved
- **Messenger tells you when customers' messages do not arrive.** When the Page writes to several people and none of their messages reach Javis, the bot card shows a warning: Meta may only be delivering messages from people with a role on the app, so request Advanced Access for pages_messaging. It clears itself once an ordinary customer's message arrives.
