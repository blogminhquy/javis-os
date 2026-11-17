---
bump: minor
title: Per-bot tool allowlists enforced by the host
---
## vi
### Bảo mật
- **Mỗi bot có thể bị giới hạn chỉ dùng đúng những công cụ chủ cho phép.** Bot có trường `tool_allowlist` chỉ thấy và chỉ gọi được các công cụ trong danh sách, kể cả khi model tự gọi tên công cụ khác hay gọi qua plugin. Danh sách lấy từ cấu hình bot đã lưu và tài khoản thật mà tin nhắn đến, không lấy từ lời model hay metadata tin nhắn. Bot không có trường này chạy như cũ.
- Lượt của bot bị giới hạn công cụ được gắn đúng ID tài khoản và ID bot, để công cụ biết chắc tin đến từ đâu. Engine CLI tạm bị chặn với các bot này vì công cụ sẵn có của CLI đi vòng qua hub.
- Bot bị giới hạn không được giữ các công cụ tạo việc chạy về sau hay chạy lệnh trên máy (`javis_schedule`, `javis_task`, `javis_job`, `javis_terminal`...), vì việc đó sẽ chạy ngoài giới hạn của bot. Lưu danh sách có các công cụ này sẽ bị từ chối và báo rõ tên công cụ.
- Khi bot bị giới hạn chạy với 0 công cụ vì tin đến không gắn được với tài khoản của bot (vd bot Telegram dùng token) hoặc vì danh sách đã lưu không hợp lệ, chủ nhận một thông báo trong hòm thư nói rõ lý do, mỗi bot và mỗi lý do một lần.

## en
### Security
- **A bot can be limited to exactly the tools its owner allows.** A bot with a `tool_allowlist` field only sees and calls the listed tools, even when the model names another tool or calls a plugin directly. The list comes from the stored bot and the account the message really arrived on, never from the model or message metadata. Bots without the field behave as before.
- Scoped bot turns now carry the real account ID and bot ID, so a tool can tell where a message came from. CLI engines are denied for these bots for now, because their native tools bypass the hub.
- A scoped bot cannot hold tools that create later work or open a shell (`javis_schedule`, `javis_task`, `javis_job`, `javis_terminal`...), because that work would run outside the bot's scope. Saving a list with them is refused with the tool names spelled out.
- When a scoped bot runs with zero tools because the message cannot be tied to one of its accounts (for example a Telegram token bot) or because its saved list is invalid, the owner gets one inbox notice with the reason, once per bot and reason.
