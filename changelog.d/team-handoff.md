---
bump: minor
title: Team hands a job to another team after owner approval
---

## vi

### Thêm mới

- Một bước việc trong nhóm có thể xin chủ duyệt việc chuyển sang nhóm khác bằng khối `handoff` (nhóm đích và việc cần làm). Chủ bấm Duyệt thì bước đó chạy xong trước, rồi Javis giao đúng một việc cho nhóm kia, kèm kết quả đã sửa, qua đường giao việc của Javis Core. Chủ bấm Từ chối thì không giao gì.
- Lỗi khi giao (nhóm đích đã lưu trữ, sai tên, hoặc trùng tên với nhóm khác) được ghi ngay trong chat nhóm nguồn, việc của nhóm nguồn vẫn đi tiếp.
- Gửi lại cùng một yêu cầu duyệt không tạo việc thứ hai.
- Nếu việc nguồn bị dừng hoặc huỷ trước khi chuyển kịp, chat nhóm nguồn báo rõ việc chuyển đang chờ hay đã bỏ, không im lặng mất.

## en

### Added

- A team step can ask the owner to approve handing work to another team with a `handoff` block (destination team and objective). When the owner approves, the step runs first, then Javis gives exactly one job to that team, with the revised result, through the Javis Core dispatch path. When the owner rejects, nothing is sent.
- A failed hop (destination archived, wrong name, or name shared with another team) is written in the source team's chat, and the source job keeps going.
- Approving the same request again does not create a second job.
- If the source job is stopped or cancelled before the hop fires, the source team's chat says the hop is waiting or was dropped, instead of vanishing silently.
