---
bump: minor
title: The chat shows the engine's task plan as a checklist
---
## vi
### Thêm mới
- **Khung trò chuyện hiện kế hoạch của bộ não như một danh sách việc.** Khi Claude Code, ChatGPT (Codex) hay Grok Build tự lập kế hoạch cho một việc nhiều bước, thẻ "Kế hoạch 2/5" hiện ngay trên câu trả lời: việc xong có dấu tích và gạch ngang, việc đang làm in đậm, việc còn lại để trống. Dòng trạng thái dưới khung chat cũng ghi đang ở bước nào. Thẻ được giữ lại khi tải lại trang.
- Không tốn thêm token: Javis chỉ vẽ danh sách mà bộ não vốn đã lập, không gọi thêm model.
- **Tab Công việc ở trang Cộng sự hiện việc cộng sự đang làm trong chat.** Trước đây tab chỉ có việc đã xếp hàng, nên lúc cộng sự đang trả lời nhiều bước ngay trong khung chat bên cạnh thì tab vẫn trống. Nay có thẻ "Đang làm trong chat" kèm số bước và kế hoạch, xong lượt là thẻ tự tắt.
- **Tab Công việc hiện các lần chạy Quy trình mà cộng sự có tham gia.** Mỗi lần chạy là một thẻ: đang chạy thì ghi bước nào và của ai, chờ duyệt thì nằm ở Cần bạn, hỏng thì đánh dấu hỏng, bấm Mở là tới đúng quy trình. Bộ lọc nguồn có thêm "Quy trình". Lần chạy bị cắt giữa chừng (máy chủ tắt khi đang chạy) không còn nằm mãi ở Đang làm.

### Sửa lỗi
- **Chấm trạng thái trên thẻ cộng sự khớp với tab Công việc.** Việc anh đã bấm Xong (cất vào lưu trữ) hay đã xoá không còn làm chấm xanh "vừa xong" (hay chấm đỏ khi việc đó hỏng) sáng lên nữa.

## en
### Added
- **The chat shows the engine's task plan as a checklist.** When Claude Code, ChatGPT (Codex) or Grok Build plans a multi-step job, a "Plan 2/5" card appears above the answer: done items ticked and struck through, the running one in bold, the rest open. The activity line under the chat says which step it is on. The card stays after a reload.
- No extra tokens: Javis only draws the list the engine already made, with no extra model call.
- **The Jobs tab on the Partners page shows what the assistant is doing in the chat.** The tab only listed queued jobs, so it looked empty while the assistant worked through several steps in the chat beside it. A "Working in the chat" card now shows the step count and the plan, and goes when the turn ends.
- **The Jobs tab lists the workflow runs the assistant took part in.** One card per run: while it runs it says which step and whose, a run waiting for review sits under Needs you, a failed one is marked failed, and Open goes to that workflow. The source filter gains "Workflows". A run cut off mid-way (the server stopped during it) no longer stays In progress for ever.

### Fixed
- **The status dot on an assistant's card agrees with its Jobs tab.** A finished job you pressed Done on (archived) or deleted no longer lights the green "just finished" dot, or the red one when it failed.
