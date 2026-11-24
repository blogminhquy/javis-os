---
bump: patch
title: Zalo bots stop going quiet after long answers, Javis's own messages count as A.I., Codex reaches Javis tools
---
## vi
### Sửa lỗi
- **Bot Zalo cá nhân không còn im 10 phút sau một câu trả lời dài.** Đoạn sau của câu bot gửi từng bị ghi nhầm là chủ nhắn tay, nên bot nhường và bỏ tin khách. Bot chăm khách cũng tìm thấy tài liệu của Agent khi đường dẫn được lưu từ ổ đĩa (máy không đăng nhập).
- **Thống kê Chatbot không còn tính tin Javis tự gửi là "Trả lời tay".** Tin gửi qua công cụ Hộp thư hay công cụ Zalo được tính là A.I., và bot đang trực không còn tưởng chủ vừa nhắn mà nhường.
- **Codex gọi được công cụ của Javis trở lại.** Từ Codex 0.163, việc nền chạy Codex bị từ chối mọi công cụ hub; giờ đã thông. Việc nền Codex cũng chạy được khi tắt hub.
- **Ghi chép từ claude.ai vào đúng brain đang dùng.** Javis Gate không còn mở hội thoại ghi chép trong brain của một cuộc chat đã ghim từ lâu.

## en
### Fixed
- **Personal Zalo bots no longer go quiet for 10 minutes after a long answer.** Later parts of the bot's own message were filed as the owner typing, so the bot stepped aside and skipped customers. Customer bots also find an Agent's documents when the path was saved from the drive (computers without sign-in).
- **Chatbot stats no longer count Javis's own messages as manual replies.** Messages sent with the inbox tool or a Zalo tool count as A.I., and the bot on duty no longer steps aside for them.
- **Codex can call Javis tools again.** Since Codex 0.163, background jobs on Codex had every hub tool refused; that works now. Background Codex jobs also start when the hub is off.
- **Notes from claude.ai land in the brain you are using.** Javis Gate no longer opens its notes conversation in the brain of a chat pinned long ago.
