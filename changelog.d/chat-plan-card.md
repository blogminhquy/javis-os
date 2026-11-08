---
bump: minor
title: The chat shows the engine's task plan as a checklist
---
## vi
### Thêm mới
- **Khung trò chuyện hiện kế hoạch của bộ não như một danh sách việc.** Khi Claude Code, ChatGPT (Codex) hay Grok Build tự lập kế hoạch cho một việc nhiều bước, thẻ "Kế hoạch 2/5" hiện ngay trên câu trả lời: việc xong có dấu tích và gạch ngang, việc đang làm in đậm, việc còn lại để trống. Dòng trạng thái dưới khung chat cũng ghi đang ở bước nào. Thẻ được giữ lại khi tải lại trang.
- Không tốn thêm token: Javis chỉ vẽ danh sách mà bộ não vốn đã lập, không gọi thêm model.

## en
### Added
- **The chat shows the engine's task plan as a checklist.** When Claude Code, ChatGPT (Codex) or Grok Build plans a multi-step job, a "Plan 2/5" card appears above the answer: done items ticked and struck through, the running one in bold, the rest open. The activity line under the chat says which step it is on. The card stays after a reload.
- No extra tokens: Javis only draws the list the engine already made, with no extra model call.
