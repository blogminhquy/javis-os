---
bump: patch
title: Approving a workflow step on the Tasks page runs it on instead of asking again
---
## vi
### Sửa lỗi
- **Duyệt một mốc của quy trình ở trang Nhiệm vụ thì quy trình chạy tiếp, không hỏi duyệt lại.** Trước đây mỗi lần trả lời, quy trình chạy lại từ bước đầu nên lại dừng đúng mốc cũ. Giờ trả lời "Duyệt", "ok" hay "đồng ý" là chạy tiếp từ mốc đó. Câu yêu cầu sửa vẫn cho quy trình làm lại kèm lời sửa như cũ.

## en
### Fixed
- **Approving a workflow step on the Tasks page runs the workflow on, with no second approval request.** Each answer used to start the workflow again from step one, so it stopped at the same step again. Now "Approve", "ok" or "yes" carries on from that step. A change request still makes the workflow redo the work with it, as before.
