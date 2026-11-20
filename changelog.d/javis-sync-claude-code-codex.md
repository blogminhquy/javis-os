---
bump: minor
title: Claude Code and Codex sessions saved into Javis automatically
---
## vi
### Thêm mới
- **Hội thoại Claude Code và Codex tự lưu vào Javis.** Mỗi lượt xong, câu anh gõ và câu trả lời cuối hiện trong Lịch sử dưới tên "Từ Claude Code: ..." hay "Từ Codex: ...", và vào vòng tự học.
- **Cài chỉ bằng một câu "ok".** Nối Claude Code hay Codex vào Javis Gate là nó hỏi có bật Javis Sync không; đồng ý là nó tự cài trên máy, không phải gõ lệnh hay chép token.
- **Không tốn hạn mức, không lo mất.** Javis không chạy model cho việc này, API key được che trước khi lưu, Javis tắt thì lượt chờ gửi bù sau. Token của nó chỉ lưu được hội thoại, không làm được gì khác.

## en
### Added
- **Claude Code and Codex sessions are saved into Javis automatically.** Each finished turn, your prompt and the agent's final answer, appears in History as "From Claude Code: ..." or "From Codex: ...", and feeds self-learning.
- **Setup is one "yes".** Connect Claude Code or Codex to Javis Gate and it asks whether to turn on Javis Sync; say yes and it installs itself on that machine, no command to type and no token to copy.
- **No quota spent, nothing lost.** Javis runs no model for it, API keys are masked before saving, and turns wait and resend when Javis is off. Its token can only save chats, nothing else.
