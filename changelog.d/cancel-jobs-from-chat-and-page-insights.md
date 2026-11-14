---
bump: minor
title: Cancel background jobs from chat, optional Page insights, Messenger names
---
## vi
### Thêm mới
- **Huỷ việc nền ngay trong chat.** Bảo Javis huỷ một việc là việc rời hàng đợi, việc đang chạy dừng luôn, lý do được ghi vào nhật ký. Khi trả một việc chưa đạt về làm lại, có thể dặn thêm cách sửa và lần làm lại sẽ theo lời dặn đó.
- **Nối Fanpage có thêm ô "Đọc số liệu bài viết".** Ô tuỳ chọn này xin quyền đọc lượt tiếp cận, lượt lưu của bài. Bảng kiểm tra Messenger báo Trang đã có quyền này chưa.

### Sửa lỗi
- **Hội thoại Messenger hiện tên khách thay vì một dãy số.** Khi Meta không cho đọc hồ sơ, Javis lấy tên từ cuộc trò chuyện của Trang, và tự thử lại sau 10 phút nếu lần trước không lấy được.

## en
### Added
- **Cancel background jobs right in chat.** Ask Javis to cancel a job and it leaves the queue, a running job stops at once, and the reason goes into the job's log. When sending a job back to be redone, an extra note on how to fix it now reaches the redo.
- **Connecting a Facebook Page has a "Read post insights" tick.** This optional tick asks for reach and saves of posts. The Messenger checklist shows whether the Page has that permission.

### Fixed
- **Messenger conversations show the customer's name instead of a bare ID.** When Meta refuses the profile, Javis takes the name from the Page conversation, and tries again after 10 minutes if it could not get it.
