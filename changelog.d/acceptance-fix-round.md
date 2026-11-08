---
bump: patch
title: A failed acceptance check goes back to the worker instead of asking you an empty question
---
## vi
### Sửa lỗi
- **Việc nền trượt lượt tự kiểm không còn hiện ô "Gõ câu trả lời" trống.** Trước đây việc chạy xong mà máy tự kiểm thấy chưa đạt thì chuyển sang "cần bạn trả lời" dù chẳng có câu hỏi nào.
- **Trượt lần đầu, việc tự quay lại cho người làm sửa** theo đúng lý do máy chấm, bạn không bị làm phiền.
- **Trượt lần hai mới tới bạn**, thẻ ghi rõ "Máy tự kiểm chưa qua" kèm hai nút: **Sửa rồi chạy lại** hoặc **Chấp nhận như vậy**. Bấm kiểm lại một việc đã xong mà trượt thì cũng hiện hai nút này.

## en
### Fixed
- **A background job that fails its automatic check no longer shows an empty "Type your answer" box.** Before, a finished job that failed the check moved to "needs your answer" even though there was no question.
- **On the first miss the job goes back to its worker to fix**, using the checker's reason, without bothering you.
- **Only a second miss reaches you**, as a card saying "Automatic check did not pass" with two buttons: **Fix and run again** or **Accept as is**. Checking a finished job again and failing shows the same two buttons.
